"""Benchmark: does each layer of the pipeline reduce wrong answers?

Three variants are run on the same questions:

  naive   one Sonnet call, schema only (no dataset notes), no checks. This is
          what most people would build first, and the baseline for the claim
          "my pipeline hallucinates less than naive prompting".
  notes   same single call, but the schema includes the verified dataset
          notes. Isolates how much the notes alone help.
  full    the real pipeline: scope -> ambiguity -> generate -> critique ->
          repair -> execute -> explain -> caveat.

Every variant executes SQL through the same read-only executor and is scored
by comparing its result set with hand-written gold SQL (eval/compare.py).

Usage (needs a valid ANTHROPIC_API_KEY in .env):
    python eval/run_benchmark.py                       # all variants, 1 run each
    python eval/run_benchmark.py --repeats 3           # LLMs are random: average 3 runs
    python eval/run_benchmark.py --variants naive full --group trap landmine
    python eval/run_benchmark.py --limit 5             # quick smoke test
"""
import argparse
import json
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

from config import get_client, SMART_MODEL  # noqa: E402
from db.execute_query import execute_query  # noqa: E402
from eval.compare import results_match  # noqa: E402
from eval.infra import is_infra_error, refuse_if_contaminated  # noqa: E402
from eval.questions import Q  # noqa: E402
import answer_cache  # noqa: E402
from usage_tracking import track  # noqa: E402
from orchestrator import answer_question  # noqa: E402

answer_cache.disable()   # measure the real pipeline, never cache hits
from sql_generation.schema_context import build_schema_context  # noqa: E402

NAIVE_SYSTEM = (
    "You are a SQL expert. Write a single SQLite query that answers the user's question "
    "using the schema provided. Return ONLY the raw SQL, no explanation, no code fences."
)


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("\n", 1)[0].strip()
    return text


def run_single_call(question: str, include_notes: bool) -> dict:
    """One LLM call, no checks. Returns the same shape as answer_question."""
    started = time.monotonic()
    schema = build_schema_context(include_notes=include_notes)
    with track() as ledger:
        try:
            resp = get_client().messages.create(
                model=SMART_MODEL, max_tokens=1200, system=NAIVE_SYSTEM,
                messages=[{"role": "user", "content": f"Schema:\n{schema}\n\nQuestion: {question}"}],
            )
            sql = _strip_fences(resp.content[0].text)
            res = execute_query(sql)
        except Exception as exc:  # noqa: BLE001
            return {"status": "failed", "detail": repr(exc), "latency_s": round(time.monotonic() - started, 2),
                    "usage": ledger.summary()}
    out = {"sql": sql, "attempts": 1, "caveat": None, "latency_s": round(time.monotonic() - started, 2),
           "usage": ledger.summary()}
    if res["status"] == "success":
        out.update(status="success", columns=res["columns"], rows=res["rows"])
    else:
        out.update(status="failed", detail=res["reason"])
    return out


VARIANTS = {
    "naive": lambda q: run_single_call(q, include_notes=False),
    "notes": lambda q: run_single_call(q, include_notes=True),
    "full": answer_question,
}

_gold_cache: dict = {}


def gold_result(q: dict) -> dict:
    if q["id"] not in _gold_cache:
        _gold_cache[q["id"]] = execute_query(q["gold_sql"])
    return _gold_cache[q["id"]]


def score(q: dict, out: dict) -> dict:
    """Classify one outcome.

    verdict:
      correct        answered and matched gold / behaved as required
      wrong_answer   returned a result that does NOT match gold (a silent error)
      abstained      should have answered but asked to clarify / declined / failed
      wrong_behavior non-answer question handled the wrong way
    """
    status = out.get("status")
    behavior = q["behavior"]

    if behavior == "answer":
        if status != "success":
            verdict = "abstained"
        else:
            g = gold_result(q)
            ok = results_match(out["columns"], out["rows"], g["columns"], g["rows"])
            verdict = "correct" if ok else "wrong_answer"
    elif behavior == "refuse":
        verdict = "correct" if status != "success" else "wrong_behavior"
    else:  # clarify / out_of_scope
        verdict = "correct" if status == behavior else "wrong_behavior"

    caveat_ok = None
    if behavior == "answer" and status == "success" and q["caveat"] is not None:
        has = bool(out.get("caveat"))
        caveat_ok = has == q["caveat"]
    return {"verdict": verdict, "caveat_ok": caveat_ok}


def run_one(args):
    variant, q, rep = args
    out = VARIANTS[variant](q["question"])
    s = score(q, out)
    rows = out.get("rows") or []
    return {
        "variant": variant, "rep": rep, "id": q["id"], "group": q["group"], "behavior": q["behavior"],
        "question": q["question"], "status": out.get("status"), "sql": out.get("sql"),
        "attempts": out.get("attempts"), "caveat": out.get("caveat"), "latency_s": out.get("latency_s"),
        "cost_usd": (out.get("usage") or {}).get("cost_usd"), "api_calls": (out.get("usage") or {}).get("calls"),
        "detail": out.get("detail"), "rows_preview": [list(r) for r in rows[:5]],
        "n_rows": len(rows), **s,
    }


def pct(n, d):
    return f"{100 * n / d:.0f}%" if d else "–"


def summarize(results: list, variants: list) -> str:
    lines = []
    ans = [r for r in results if r["behavior"] == "answer"]
    non = [r for r in results if r["behavior"] != "answer"]

    lines.append("## Answerable questions (execution accuracy vs gold SQL)\n")
    lines.append("| Variant | Correct | **Silent wrong answers** | Abstained | Caveat correct | Median latency | Median cost / question |")
    lines.append("|---|---|---|---|---|---|---|")
    for v in variants:
        rs = [r for r in ans if r["variant"] == v]
        if not rs:
            continue
        n = len(rs)
        c = sum(r["verdict"] == "correct" for r in rs)
        w = sum(r["verdict"] == "wrong_answer" for r in rs)
        a = sum(r["verdict"] == "abstained" for r in rs)
        cav = [r for r in rs if r["caveat_ok"] is not None]
        cav_ok = sum(r["caveat_ok"] for r in cav)
        lat = statistics.median(r["latency_s"] for r in rs if r["latency_s"] is not None)
        costs = [r["cost_usd"] for r in rs if r.get("cost_usd") is not None]
        cost = f"≈ ${statistics.median(costs):.3f}" if costs else "–"
        lines.append(f"| {v} | {c}/{n} ({pct(c, n)}) | {w}/{n} ({pct(w, n)}) | {a}/{n} ({pct(a, n)}) | "
                     f"{cav_ok}/{len(cav)} ({pct(cav_ok, len(cav))}) | {lat:.1f}s | {cost} |")

    lines.append("\n'Silent wrong answers' is the hallucination metric: the system returned a confident "
                 "number that does not match the gold answer. 'Abstained' means it asked a question or "
                 "failed visibly instead.\n")

    lines.append("## Accuracy by question group\n")
    groups = sorted({r["group"] for r in ans})
    lines.append("| Group | " + " | ".join(variants) + " |")
    lines.append("|---|" + "---|" * len(variants))
    for g in groups:
        cells = []
        for v in variants:
            rs = [r for r in ans if r["variant"] == v and r["group"] == g]
            cells.append(f"{sum(r['verdict'] == 'correct' for r in rs)}/{len(rs)}" if rs else "–")
        lines.append(f"| {g} | " + " | ".join(cells) + " |")

    lines.append("\n## Non-answer behaviour (clarify / out of scope / refuse writes)\n")
    lines.append("| Variant | Handled correctly |")
    lines.append("|---|---|")
    for v in variants:
        rs = [r for r in non if r["variant"] == v]
        if rs:
            c = sum(r["verdict"] == "correct" for r in rs)
            lines.append(f"| {v} | {c}/{len(rs)} ({pct(c, len(rs))}) |")

    full = [r for r in ans if r["variant"] == "full" and r["status"] == "success"]
    if full:
        lines.append(f"\nFull pipeline: first-try rate {pct(sum(r['attempts'] == 1 for r in full), len(full))}, "
                     f"needed one repair {pct(sum(r['attempts'] == 2 for r in full), len(full))}.")

    bad = [r for r in results if r["verdict"] in ("wrong_answer", "wrong_behavior") and r["variant"] == "full"]
    if bad:
        lines.append("\n## Full-pipeline failures to investigate\n")
        for r in bad:
            lines.append(f"- **{r['id']}** ({r['verdict']}): {r['question']}\n  - status: {r['status']}; SQL: `{(r['sql'] or '').strip()[:300]}`")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--variants", nargs="+", default=list(VARIANTS), choices=list(VARIANTS))
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--group", nargs="*", help="only these question groups")
    ap.add_argument("--limit", type=int, help="only the first N questions")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--set", choices=["main", "heldout"], default="main",
                    help="heldout = questions never used for tuning; results go to heldout-* files")
    args = ap.parse_args()

    if args.set == "heldout":
        from eval.questions_heldout import Q as questions
    else:
        questions = Q
    prefix = "heldout-" if args.set == "heldout" else ""
    qs = [q for q in questions if not args.group or q["group"] in args.group]
    if args.limit:
        qs = qs[: args.limit]
    jobs = [(v, q, r) for v in args.variants for q in qs for r in range(args.repeats)]
    print(f"Running {len(jobs)} jobs ({len(qs)} questions x {len(args.variants)} variants x {args.repeats} repeats)...")

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(run_one, jobs))
    refuse_if_contaminated(sum(is_infra_error(r["detail"]) for r in results), len(results))

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = ROOT / "eval" / "results"
    out_dir.mkdir(exist_ok=True)
    raw = json.dumps(results, indent=2, default=str)
    (out_dir / f"{prefix}{stamp}.json").write_text(raw)
    (out_dir / f"{prefix}latest.json").write_text(raw)   # main set is read by the app's Benchmark tab
    report = summarize(results, args.variants)
    (out_dir / f"{prefix}{stamp}.md").write_text(report)
    (out_dir / f"{prefix}latest.md").write_text(report)
    print("\n" + report)
    print(f"\nRaw results: eval/results/{prefix}{stamp}.json")


if __name__ == "__main__":
    main()
