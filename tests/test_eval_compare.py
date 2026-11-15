from eval.compare import results_match as m


def test_identical():
    assert m(["a"], [(5,)], ["a"], [(5,)])


def test_count_off_by_one_is_wrong():
    assert not m(["n"], [(99440,)], ["n"], [(99441,)])


def test_float_tolerance_accepts_rounding_but_not_fraction_vs_percent():
    assert m(["p"], [(3.1,)], ["p"], [(3.1187,)])
    assert m(["p"], [(3.12,)], ["p"], [(3.1187,)])
    assert not m(["p"], [(0.0312,)], ["p"], [(3.1187,)])


def test_large_revenue_rounding_ok():
    assert m(["r"], [(13591644,)], ["r"], [(13591643.7,)])


def test_extra_columns_allowed_and_order_ignored():
    gold = [("SP", 10), ("RJ", 5)]
    pred = [(5, "RJ", "x"), (10, "SP", "y")]
    assert m(["a", "b", "c"], pred, ["s", "n"], gold)


def test_swapped_values_between_rows_detected():
    assert not m(["s", "n"], [("SP", 5), ("RJ", 10)], ["s", "n"], [("SP", 10), ("RJ", 5)])


def test_row_count_must_match():
    assert not m(["s"], [("SP",)], ["s"], [("SP",), ("RJ",)])


def test_text_case_insensitive_and_none():
    assert m(["s"], [("sp",)], ["s"], [("SP",)])
    assert m(["s"], [(None,)], ["s"], [(None,)])
    assert not m(["s"], [(None,)], ["s"], [("SP",)])


def test_missing_column_fails():
    assert not m(["n"], [(1,)], ["s", "n"], [("SP", 1)])


def test_heldout_set_is_well_formed_and_disjoint_from_main_set():
    from db.execute_query import execute_query
    from eval.questions import Q as main
    from eval.questions_heldout import Q as held
    ids = [q["id"] for q in held]
    assert len(ids) == len(set(ids)) and len(held) >= 35
    assert not {q["question"].lower() for q in held} & {q["question"].lower() for q in main}
    assert {q["behavior"] for q in held} == {"answer", "clarify", "out_of_scope", "refuse"}
    for q in held:
        if q["behavior"] == "answer":
            r = execute_query(q["gold_sql"])
            assert r["status"] == "success" and r["rows"], q["id"]
