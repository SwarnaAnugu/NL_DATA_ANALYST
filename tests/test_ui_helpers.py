import usage_limits
from charting.render import build_figure
from feedback import record_feedback


def test_figure_types():
    bar = build_figure({"chart_type": "bar", "x": "state", "y": "n"}, ["state", "n"], [("SP", 3), ("RJ", 2)])
    assert bar.data[0].type == "bar" and bar.data[0].orientation != "h"
    many = [(f"c{i}", i) for i in range(12)]
    assert build_figure({"chart_type": "bar", "x": "c", "y": "n"}, ["c", "n"], many).data[0].orientation == "h"
    line = build_figure({"chart_type": "line", "x": "m", "y": "n"}, ["m", "n"], [("2017-02", 2), ("2017-01", 1)])
    assert line.data[0].type == "scatter" and list(line.data[0].x) == ["2017-01", "2017-02"]


def test_no_figure_for_none_or_empty():
    assert build_figure({"chart_type": "none"}, ["a"], [(1,)]) is None
    assert build_figure({"chart_type": "bar", "x": "a", "y": "b"}, ["a", "b"], []) is None


def test_daily_limit(monkeypatch):
    usage_limits.reset_for_tests()
    monkeypatch.setattr(usage_limits, "DAILY_LIMIT", 2)
    assert [usage_limits.try_consume_daily() for _ in range(3)] == [True, True, False]
    usage_limits.reset_for_tests()


def test_feedback_written_and_never_raises(tmp_path):
    p = tmp_path / "sub" / "fb.jsonl"
    record_feedback("q", "SELECT 1", "up", path=p)
    assert '"rating": "up"' in p.read_text()
    record_feedback("q", None, "down", path=tmp_path)   # path is a directory -> OSError swallowed


def test_many_bars_are_trimmed_to_top_n_with_note():
    rows = [(f"c{i}", i) for i in range(74)] + [(None, 500)]
    fig = build_figure({"chart_type": "bar", "x": "c", "y": "n"}, ["c", "n"], rows)
    assert len(fig.data[0].x) == 20 and max(fig.data[0].x) == 500
    assert "Top 20 of 75" in fig.layout.title.text
    assert "(none)" in list(fig.data[0].y)          # NULL label shown as (none), not dropped or crashing


def test_currency_dollar_signs_are_escaped_for_streamlit_markdown():
    import ast, pathlib
    src = (pathlib.Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py").read_text()
    ns = {}
    exec(src[src.index("def safe_md"):src.index("def render_assistant_result")], ns)
    assert ns["safe_md"]("R$1,258,681 and R$1,205,006") == "R\\$1,258,681 and R\\$1,205,006"
    assert ns["safe_md"](None) == ""
