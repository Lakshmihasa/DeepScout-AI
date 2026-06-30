"""
LLM-as-judge for DeepScout reports. Supports Gemini or OpenRouter as the judge.

Set via env:
  JUDGE_PROVIDER         "gemini" (default) or "openrouter"
  JUDGE_MODEL            defaults to gemini-2.5-flash / openai/gpt-oss-20b:free
  EVAL_JUDGE_TEMPERATURE default 0.0 (deterministic scoring)
  EVAL_JUDGE_SAMPLES     default 1 (set 3 to average out judge noise)

NOTE: gemini-2.0-flash was shut down 2026-06-01 — its free-tier limit is 0, which
is what produced the "limit: 0 ... RESOURCE_EXHAUSTED" errors. Default is now 2.5
Flash. Keep the judge a DIFFERENT model from your generator to avoid self-bias.
"""

import os
import json
import statistics

from dotenv import load_dotenv
from google import genai
from openai import OpenAI

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
JUDGE_PROVIDER = os.getenv("JUDGE_PROVIDER", "gemini").lower()

JUDGE_MODEL = os.getenv(
    "JUDGE_MODEL",
    "gemini-2.5-flash" if JUDGE_PROVIDER == "gemini" else "openai/gpt-oss-20b:free",
)
JUDGE_TEMPERATURE = float(os.getenv("EVAL_JUDGE_TEMPERATURE", "0.0"))
JUDGE_SAMPLES = max(1, int(os.getenv("EVAL_JUDGE_SAMPLES", "1")))

# Gemini client
gemini_client = genai.Client(api_key=GEMINI_API_KEY)

# OpenRouter client (OpenAI-compatible)
openrouter_client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
)

DIMENSIONS = ["faithfulness", "coverage", "coherence"]


RUBRIC = """
Score each dimension on an integer scale of 1-5 using these anchors:

FAITHFULNESS (are the report's claims supported by the EVIDENCE?)
  5 = every substantive claim is directly supported by the evidence
  4 = mostly supported; at most one minor unsupported claim
  3 = several claims not found in the evidence
  2 = many unsupported claims, or a claim that contradicts the evidence
  1 = largely fabricated; ignores or contradicts the evidence

COVERAGE (does the report actually answer the QUERY?)
  5 = fully addresses every aspect of the query
  4 = addresses the query with a minor gap
  3 = partial; misses an important aspect
  2 = only tangentially answers the query
  1 = does not answer the query

COHERENCE (structure & clarity for the given MODE)
  5 = clear, well-organized, follows the mode's expected structure
  4 = clear with minor structural issues
  3 = understandable but disorganized
  2 = hard to follow
  1 = incoherent
"""


# ----------------------------------------------------------------------------
# Shared internals
# ----------------------------------------------------------------------------
def _parse_json(text):
    """Defensive parse: strip code fences, grab the outermost JSON object."""
    if not text:
        raise ValueError("empty judge response")
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"no JSON object in judge response: {text[:200]}")
    return json.loads(text[start : end + 1])


def _call_judge(prompt):
    """Dispatch to the configured provider. if/elif/else must share indentation."""
    if JUDGE_PROVIDER == "gemini":
        resp = gemini_client.models.generate_content(
            model=JUDGE_MODEL,
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "temperature": JUDGE_TEMPERATURE,
            },
        )
        return _parse_json(resp.text)

    elif JUDGE_PROVIDER == "openrouter":
        response = openrouter_client.chat.completions.create(
            model=JUDGE_MODEL,
            temperature=JUDGE_TEMPERATURE,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a strict evaluation judge. "
                        "Respond ONLY with valid JSON. "
                        "Do not use markdown or code fences."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
        )
        return _parse_json(response.choices[0].message.content)

    else:
        raise ValueError(f"Unknown JUDGE_PROVIDER: {JUDGE_PROVIDER}")


# ----------------------------------------------------------------------------
# POINTWISE
# ----------------------------------------------------------------------------
def _pointwise_prompt(query, mode, report, evidence):
    return f"""You are a strict evaluator of AI-generated research reports.

QUERY:
{query}

MODE: {mode}

EVIDENCE (the source text the report was supposed to be grounded in):
{evidence if evidence.strip() else "[NO EVIDENCE PROVIDED]"}

REPORT TO EVALUATE:
{report}

{RUBRIC}

Also list every claim in the report that is NOT supported by the evidence.
If no evidence was provided, set faithfulness to 1 and say so in the reason.

Return ONLY valid JSON, no markdown, in exactly this shape:
{{
  "faithfulness": {{"score": <1-5>, "reason": "<one sentence>"}},
  "coverage":     {{"score": <1-5>, "reason": "<one sentence>"}},
  "coherence":    {{"score": <1-5>, "reason": "<one sentence>"}},
  "unsupported_claims": ["<claim>", "..."]
}}"""


def judge_report(query, mode, report, evidence):
    """Pointwise scoring. Averages EVAL_JUDGE_SAMPLES judge calls to cut noise.

    Returns averaged (float) dimension scores. unsupported_claims and reasons are
    taken from the first successful sample (representative, not aggregated)."""
    prompt = _pointwise_prompt(query, mode, report, evidence)
    samples, last_err = [], None
    for _ in range(JUDGE_SAMPLES):
        try:
            samples.append(_call_judge(prompt))
        except Exception as e:
            last_err = e
            print(f"  judge sample error: {e}")

    if not samples:
        return {**{d: 0 for d in DIMENSIONS}, "reasons": {},
                "unsupported_claims": [], "error": str(last_err)}

    averaged = {
        d: round(statistics.mean(int(s[d]["score"]) for s in samples), 2)
        for d in DIMENSIONS
    }
    first = samples[0]
    return {
        **averaged,
        "reasons": {d: first[d].get("reason", "") for d in DIMENSIONS},
        "unsupported_claims": first.get("unsupported_claims", []),
        "samples": len(samples),
        "error": None,
    }


# ----------------------------------------------------------------------------
# PAIRWISE
# ----------------------------------------------------------------------------
def _pairwise_prompt(query, mode, report_first, report_second, evidence):
    return f"""You are comparing two AI-generated research reports answering the same query.

QUERY:
{query}

MODE: {mode}

EVIDENCE available to both:
{evidence if evidence.strip() else "[NO EVIDENCE PROVIDED]"}

REPORT FIRST:
{report_first}

REPORT SECOND:
{report_second}

Decide which report better answers the query AND is better grounded in the
evidence (penalize unsupported claims). Judge substance, not length or tone.

Return ONLY valid JSON:
{{"winner": "first" | "second" | "tie", "reason": "<one sentence>"}}"""


def _pairwise_once(query, mode, r_first, r_second, evidence):
    try:
        return _call_judge(_pairwise_prompt(query, mode, r_first, r_second, evidence))
    except Exception as e:
        print(f"  pairwise error: {e}")
        return {"winner": "tie", "reason": f"error: {e}"}


def judge_pairwise(query, mode, report_a, report_b, evidence):
    """Runs both orders to cancel position bias. A win counts only if it holds
    regardless of which report was shown first; disagreement -> tie."""
    v1 = _pairwise_once(query, mode, report_a, report_b, evidence)  # A is "first"
    v2 = _pairwise_once(query, mode, report_b, report_a, evidence)  # B is "first"

    w1 = {"first": "A", "second": "B"}.get(v1.get("winner"), "tie")
    w2 = {"first": "B", "second": "A"}.get(v2.get("winner"), "tie")

    winner = w1 if w1 == w2 else "tie"
    return {
        "winner": winner,
        "order1": w1,
        "order2": w2,
        "reasons": [v1.get("reason", ""), v2.get("reason", "")],
    }