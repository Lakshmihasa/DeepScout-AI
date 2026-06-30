"""
Adapters: how the eval harness gets a report out of your pipeline.

The runner is decoupled from your backend via a `research_fn(query, mode)` callable
that must return:
    {"report": str, "sources": list, "evidence": str}

`evidence` is the source text the report was grounded in (your `retrieved_context`,
or the concatenated scraped content). Faithfulness scoring is meaningless without
it — the sources list (title + url) is NOT enough.

Two adapters are provided:

  1. http_research_fn  — works TODAY against a running server, IF you expose the
     evidence. One-line change in main.py's /research:
         final_response = {"report": report, "sources": sources,
                           "retrieved_context": retrieved_context}
     (Harmless to add; the frontend can ignore it.)

  2. direct_research_fn — the recommended path AFTER you modularize. Import your
     pipeline function and call it with caching DISABLED. Caching must be off for
     eval or you measure cached responses, not your system.
"""

import os
import requests

BACKEND_URL = os.getenv("EVAL_BACKEND_URL", "http://localhost:8000")


def http_research_fn(query, mode):
    """Calls POST /research on a running server."""
    resp = requests.post(
        f"{BACKEND_URL}/research",
        json={"query": query, "history": [], "mode": mode},
        timeout=120,
    )
    resp.raise_for_status()
    data = resp.json()

    evidence = data.get("retrieved_context", "")
    if not evidence:
        # Fall back to any per-source content; warn loudly if there's none.
        evidence = "\n\n".join(
            s.get("content", "") for s in data.get("sources", []) if s.get("content")
        )
        if not evidence:
            print(
                "  WARNING: no evidence in response — faithfulness will be unreliable. "
                "Add 'retrieved_context' to the /research response (see adapters.py)."
            )

    return {
        "report": data.get("report", ""),
        "sources": data.get("sources", []),
        "evidence": evidence,
    }


# --- Recommended after modularization -------------------------------------
# from deepscout.pipeline import run_pipeline   # your refactored entrypoint
#
# def direct_research_fn(query, mode):
#     report, sources, evidence = run_pipeline(query, mode, use_cache=False)
#     return {"report": report, "sources": sources, "evidence": evidence}
# ---------------------------------------------------------------------------