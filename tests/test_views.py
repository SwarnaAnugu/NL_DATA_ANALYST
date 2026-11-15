import json

from benchmark_view import build_figure, load_results, summarize
from overview import dataset_overview


def _r(variant, behavior, verdict, group="simple", lat=1.0, rep=0, id="x"):
    return dict(variant=variant, behavior=behavior, verdict=verdict, group=group,
                latency_s=lat, rep=rep, id=id)


def test_summarize_and_figure():
    res = [_r("naive", "answer", "wrong_answer"), _r("naive", "answer", "correct"),
           _r("naive", "clarify", "wrong_behavior"),
           _r("full", "answer", "correct"), _r("full", "answer", "abstained"),
           _r("full", "clarify", "correct")]
    s = summarize(res)
    assert s["variants"]["naive"]["wrong"] == 50 and s["variants"]["naive"]["non_answer_ok"] == 0
    assert s["variants"]["full"]["abstained"] == 50 and s["variants"]["full"]["non_answer_ok"] == 100
    assert len(build_figure(s).data) == 3


def test_load_results_missing_or_corrupt(tmp_path):
    assert load_results(tmp_path / "nope.json") is None
    bad = tmp_path / "bad.json"; bad.write_text("{not json")
    assert load_results(bad) is None


def test_shipped_results_are_loadable_and_sane():
    res = load_results()
    assert res, "eval/results/latest.json should ship with the repo"
    s = summarize(res)
    assert set(s["variants"]) == {"naive", "notes", "full"}
    for v in s["variants"].values():
        assert abs(v["correct"] + v["wrong"] + v["abstained"] - 100) < 1e-6


def test_dataset_overview():
    o = dataset_overview()
    assert o["orders"] == 99441 and o["customers"] == 96096 and o["first"] == "2016-09" and o["last"] == "2018-10"


def test_shipped_scenarios_load_and_summarize():
    from benchmark_view import load_scenarios, summarize_scenarios
    sc = load_scenarios()
    assert sc, "eval/results/scenarios-latest.json should ship with the repo"
    ss = summarize_scenarios(sc)
    assert ss["total"] == sum(n for _, n in ss["by_group"].values()) and 0 <= ss["passed"] <= ss["total"]
