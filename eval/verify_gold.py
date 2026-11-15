"""Runs every gold SQL against the database and prints a preview, so a human
can eyeball that the reference answers are right. Run before trusting any
benchmark number:  python eval/verify_gold.py"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

from db.execute_query import execute_query  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", choices=["main", "heldout"], default="main")
    if ap.parse_args().set == "heldout":
        from eval.questions_heldout import Q
    else:
        from eval.questions import Q
    bad = 0
    for q in Q:
        if q["behavior"] != "answer":
            print(f"{q['id']:4} [{q['behavior']}] {q['question']}")
            continue
        r = execute_query(q["gold_sql"])
        if r["status"] != "success" or not r["rows"]:
            bad += 1
            print(f"{q['id']:4} !! {r}")
            continue
        preview = r["rows"][:3]
        print(f"{q['id']:4} {len(r['rows']):>3} rows  {r['columns']}  {preview}")
    print("\nANSWER QUESTIONS:", sum(q['behavior'] == 'answer' for q in Q), "| gold failures:", bad)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
