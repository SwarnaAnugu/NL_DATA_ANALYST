from charting.chart_selector import select_chart as sel
from charting.render import build_figure


def test_classic_two_column_cases():
    assert sel(["v"], [(5,)])["chart_type"] == "none"
    assert sel(["c", "n"], [("a", 1), ("b", 2)]) == {"chart_type": "bar", "x": "c", "y": "n"}
    assert sel(["m", "n"], [("2017-01", 1), ("2017-02", 2)]) == {"chart_type": "line", "x": "m", "y": "n"}
    assert sel(["n", "c"], [(1, "a"), (2, "b")]) == {"chart_type": "bar", "x": "c", "y": "n"}   # column order doesn't matter


def test_two_numeric_columns_no_label_is_table():
    assert sel(["a", "b"], [(1, 2), (3, 4)])["chart_type"] == "none"


def test_empty_and_single_row():
    assert sel(["a"], [])["chart_type"] == "none"
    assert "single row" in sel(["a", "b"], [("x", 1)])["reason"]


def test_multiple_measures_over_time():
    c = sel(["m", "orders", "revenue"], [("2017-01", 1, 10.0), ("2017-02", 2, 20.0)])
    assert c == {"chart_type": "line", "x": "m", "y": ["orders", "revenue"]}
    fig = build_figure(c, ["m", "orders", "revenue"], [("2017-01", 1, 10.0), ("2017-02", 2, 20.0)])
    assert {t.name for t in fig.data} == {"Orders", "Revenue"}


def test_grouped_series_month_by_state():
    rows = [("2017-01", "SP", 5), ("2017-01", "RJ", 3), ("2017-02", "SP", 6), ("2017-02", "RJ", 4)]
    c = sel(["month", "state", "n"], rows)
    assert c == {"chart_type": "line", "x": "month", "y": "n", "color": "state"}
    assert {t.name for t in build_figure(c, ["month", "state", "n"], rows).data} == {"SP", "RJ"}


def test_grouped_bars_for_categorical_pairs():
    rows = [("SP", "credit_card", 5), ("SP", "boleto", 3), ("RJ", "credit_card", 6), ("RJ", "boleto", 4)]
    c = sel(["state", "pay", "n"], rows)
    assert c["chart_type"] == "bar" and c["color"] in ("pay", "state")
    assert build_figure(c, ["state", "pay", "n"], rows) is not None


def test_too_many_groups_falls_back_to_table():
    rows = [("2017-01", f"g{i}", i) for i in range(30)]
    assert sel(["m", "g", "n"], rows)["chart_type"] == "none"


def test_nulls_and_odd_types_dont_crash():
    assert sel(["c", "n"], [(None, 1), ("a", 2)])["chart_type"] == "bar"
    assert sel(["c", "n"], [("a", None), ("b", None)])["chart_type"] == "none"     # nothing numeric to plot
    fig = build_figure({"chart_type": "bar", "x": "c", "y": "n"}, ["c", "n"], [(None, 1), ("a", 2)])
    assert "(none)" in list(fig.data[0].x)
    assert sel(["flag", "n"], [(True, 1), (False, 2)])["chart_type"] == "bar"      # booleans are labels
