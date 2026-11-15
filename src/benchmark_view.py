"""Turns the benchmark's raw results (eval/results/latest.json) into numbers
and a chart for the app's Benchmark tab. Pure functions, no Streamlit."""
import json
from pathlib import Path

import plotly.graph_objects as go

from config import REPO_ROOT

RESULTS_PATH = REPO_ROOT / "eval" / "results" / "latest.json"
SCENARIOS_PATH = REPO_ROOT / "eval" / "results" / "scenarios-latest.json"
VARIANT_LABELS = {"naive": "Naive single prompt", "notes": "Single prompt + dataset notes", "full": "Full pipeline"}


def load_results(path: Path = RESULTS_PATH):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def summarize(results: list) -> dict:
    """Per-variant percentages on answerable questions, plus non-answer handling."""
    out = {"variants": {}, "n_questions": len({r["id"] for r in results}),
           "repeats": max(r["rep"] for r in results) + 1}
    for v in VARIANT_LABELS:
        ans = [r for r in results if r["variant"] == v and r["behavior"] == "answer"]
        non = [r for r in results if r["variant"] == v and r["behavior"] != "answer"]
        if not ans:
            continue
        pct = lambda n, d: 100.0 * n / d if d else 0.0  # noqa: E731
        by_group = {}
        for g in sorted({r["group"] for r in ans}):
            rs = [r for r in ans if r["group"] == g]
            by_group[g] = pct(sum(r["verdict"] == "correct" for r in rs), len(rs))
        lat = sorted(r["latency_s"] for r in ans if r["latency_s"] is not None)
        out["variants"][v] = {
            "correct": pct(sum(r["verdict"] == "correct" for r in ans), len(ans)),
            "wrong": pct(sum(r["verdict"] == "wrong_answer" for r in ans), len(ans)),
            "abstained": pct(sum(r["verdict"] == "abstained" for r in ans), len(ans)),
            "non_answer_ok": pct(sum(r["verdict"] == "correct" for r in non), len(non)),
            "median_latency": lat[len(lat) // 2] if lat else None,
            "by_group": by_group,
            "n_answerable": len(ans), "n_non_answer": len(non),
        }
    return out


def build_figure(summary: dict) -> go.Figure:
    names = [VARIANT_LABELS[v] for v in summary["variants"]]
    data = summary["variants"].values()
    fig = go.Figure()
    for key, label, color in [("correct", "Correct", "#16a34a"),
                              ("abstained", "Asked / declined instead", "#f59e0b"),
                              ("wrong", "Silent wrong answer", "#dc2626")]:
        vals = [d[key] for d in data]
        fig.add_bar(name=label, y=names, x=vals, orientation="h", marker_color=color,
                    text=[f"{v:.0f}%" if v >= 4 else "" for v in vals], textposition="inside",
                    hovertemplate="%{y}<br>" + label + ": %{x:.1f}%<extra></extra>")
    fig.update_layout(barmode="stack", height=260, margin=dict(l=10, r=10, t=10, b=10),
                      xaxis=dict(range=[0, 100], ticksuffix="%"), yaxis=dict(autorange="reversed"),
                      legend=dict(orientation="h", y=-0.25), plot_bgcolor="rgba(0,0,0,0)")
    return fig


def load_scenarios(path: Path = SCENARIOS_PATH):
    return load_results(path)


def summarize_scenarios(scenarios: list) -> dict:
    """{'passed': n, 'total': n, 'by_group': {group: (passed, total)}}"""
    by_group = {}
    for sc in scenarios:
        ok, total = by_group.get(sc["group"], (0, 0))
        by_group[sc["group"]] = (ok + bool(sc["passed"]), total + 1)
    return {"passed": sum(bool(s["passed"]) for s in scenarios), "total": len(scenarios), "by_group": by_group}
