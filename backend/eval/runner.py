"""
DeepScout eval runner.

Runs your pipeline over the frozen golden set, scores each report with the judge,
writes timestamped results, and DIFFS this run against the previous one — so when
you swap DDG -> Tavily you can see exactly what moved.

Usage:
    # 1. baseline (current DDG search), with a label:
    python -m eval.runner --label ddg-baseline

    # 2. swap search backend in your pipeline, then:
    python -m eval.runner --label tavily

    # the second run prints a side-by-side diff vs the baseline.

Each run writes:
    eval/results/run_<timestamp>.json   (per-query detail)
    eval/results/eval_history.jsonl     (one summary row per run, for diffing)

REMEMBER: caching must be OFF during eval, or you score cached responses.
Use the direct adapter with use_cache=False once modularized, or disable the
cache in main.py while running this.
"""

import os
import json
import time
import argparse
import datetime
import statistics

from .judge import judge_report, JUDGE_MODEL
from .adapters import http_research_fn

HERE = os.path.dirname(__file__)
GOLDEN_PATH = os.path.join(HERE, "golden_set.json")
RESULTS_DIR = os.path.join(HERE, "results")
HISTORY_PATH = os.path.join(RESULTS_DIR, "eval_history.jsonl")

DIMENSIONS = ["faithfulness", "coverage", "coherence"]


def load_golden():
    with open(GOLDEN_PATH) as f:
        return json.load(f)


def mean_or_zero(values):
    values = [v for v in values if v is not None]
    return round(statistics.mean(values), 2) if values else 0.0


def run(label, research_fn, limit=None):
    os.makedirs(RESULTS_DIR, exist_ok=True)
    golden = load_golden()

    if limit is not None:
        golden = golden[:limit]
    rows = []

    print(f"\nRunning eval '{label}' over {len(golden)} queries "
          f"(judge: {JUDGE_MODEL})\n")

    for item in golden:
        q, mode = item["query"], item["mode"]
        print(f"[{item['id']}] {mode}: {q[:60]}")
        t0 = time.time()
        report, evidence = "", ""
        try:
            out = research_fn(q, mode)
            report, evidence = out["report"], out["evidence"]
            scores = judge_report(q, mode, report, evidence)
        except Exception as e:
            print(f"  pipeline error: {e}")
            scores = {d: 0 for d in DIMENSIONS}
            scores.update({"unsupported_claims": [], "error": str(e), "reasons": {}})

        latency = round(time.time() - t0, 2)
        rows.append({
            **item,
            **{d: scores[d] for d in DIMENSIONS},
            "unsupported_count": len(scores.get("unsupported_claims", [])),
            "latency_s": latency,
            "error": scores.get("error"),
            # persisted so eval/compare.py can run pairwise on stored runs:
            "report": report,
            "evidence": evidence,
        })
        print(f"  faith={scores['faithfulness']} cov={scores['coverage']} "
              f"coh={scores['coherence']}  ({latency}s)\n")

    summary = {
        "label": label,
        "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
        "n": len(rows),
        "judge_model": JUDGE_MODEL,
        **{d: mean_or_zero([r[d] for r in rows]) for d in DIMENSIONS},
        "total_unsupported": sum(r["unsupported_count"] for r in rows),
        "p50_latency_s": mean_or_zero([r["latency_s"] for r in rows]),
        "errors": sum(1 for r in rows if r["error"]),
    }

    # write per-run detail
    ts = summary["timestamp"].replace(":", "-")
    detail_path = os.path.join(RESULTS_DIR, f"run_{ts}.json")
    with open(detail_path, "w") as f:
        json.dump({"summary": summary, "rows": rows}, f, indent=2)

    # append summary to history for diffing
    prev = _last_summary()
    with open(HISTORY_PATH, "a") as f:
        f.write(json.dumps(summary) + "\n")

    _print_summary(summary)
    _print_judge_anchor_check(rows)
    if prev:
        _print_diff(prev, summary)
    print(f"\nDetail written to {detail_path}")
    return summary


def _last_summary():
    if not os.path.exists(HISTORY_PATH):
        return None
    with open(HISTORY_PATH) as f:
        lines = [l for l in f if l.strip()]
    return json.loads(lines[-1]) if lines else None


def _print_summary(s):
    print("=" * 48)
    print(f"RESULTS — {s['label']}  ({s['timestamp']})")
    print("=" * 48)
    for d in DIMENSIONS:
        print(f"  {d:<14} {s[d]:.2f} / 5")
    print(f"  {'unsupported':<14} {s['total_unsupported']} claims total")
    print(f"  {'p50 latency':<14} {s['p50_latency_s']}s")
    if s["errors"]:
        print(f"  {'errors':<14} {s['errors']}")


def _print_judge_anchor_check(rows):
    """Compares judge scores to any human_scores in the golden set.
    Large gaps mean your JUDGE is miscalibrated — fix that before trusting it."""
    anchored = [r for r in rows if isinstance(r.get("human_scores"), dict)]
    if not anchored:
        print("\n  (no human-anchored items — hand-grade a few in golden_set.json "
              "to validate the judge)")
        return
    print("\n  judge vs human (mean abs error, lower is better):")
    for d in DIMENSIONS:
        errs = [abs(r[d] - r["human_scores"][d]) for r in anchored
                if d in r.get("human_scores", {})]
        if errs:
            print(f"    {d:<14} MAE {mean_or_zero(errs)}  (n={len(errs)})")

def _print_diff(prev, cur):
    print("\n" + "-" * 48)
    print(f"DIFF: {cur['label']} vs {prev['label']}")
    print("-" * 48)

    for d in DIMENSIONS:
        delta = round(cur[d] - prev[d], 2)
        arrow = "▲" if delta > 0 else ("▼" if delta < 0 else "=")
        print(f"  {d:<14} {prev[d]:.2f} -> {cur[d]:.2f}  {arrow} {delta:+.2f}")

    ud = cur["total_unsupported"] - prev["total_unsupported"]

    print(
        f"  {'unsupported':<14} "
        f"{prev['total_unsupported']} -> {cur['total_unsupported']}  ({ud:+d})"
    )            


if __name__ == "__main__":
    ap = argparse.ArgumentParser()

    ap.add_argument(
        "--label",
        required=True,
        help="name for this run, e.g. 'ddg-baseline' or 'tavily'",
    )

    ap.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Run only the first N evaluation queries (useful for smoke tests)",
    )

    args = ap.parse_args()

    # swap http_research_fn for direct_research_fn once modularized
    run(args.label, http_research_fn, args.limit)