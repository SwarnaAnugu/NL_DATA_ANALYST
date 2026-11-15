"""Pre-compute the example questions once and save them for the deployed app.

    python eval/warm_cache.py            # needs a working ANTHROPIC_API_KEY
    git add demo_data/example_cache.json

After this, the example buttons answer instantly, cost nothing, and keep working
even if the API is down or the daily budget is used up. Re-run it if you change
the prompts, dataset notes, or example list.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

import answer_cache  # noqa: E402
from eval.infra import is_infra_error  # noqa: E402
from examples import WARM_CACHE_PATH, WARMABLE  # noqa: E402
from orchestrator import answer_question  # noqa: E402


def main() -> int:
    answer_cache.clear()
    answer_cache.disable()          # compute fresh; we save explicitly below
    fresh = {}
    for q in WARMABLE:
        r = answer_question(q)
        if is_infra_error(r.get("detail")):
            print(f"!! API error on '{q}': {r['detail'][:120]}\n!! Nothing saved. Fix the key/credit and re-run.")
            return 2
        status = r["status"]
        print(f"{status:12} {r['latency_s']:>5}s  {q}")
        if status == "success":
            fresh[q] = r
    answer_cache.enable()
    for q, r in fresh.items():
        answer_cache.put(q, r)
    n = answer_cache.save_file(ROOT / WARM_CACHE_PATH)
    print(f"\nSaved {n} answers to {WARM_CACHE_PATH}. Review them in the app, then commit the file.")
    return 0 if n == len(WARMABLE) else 1


if __name__ == "__main__":
    sys.exit(main())
