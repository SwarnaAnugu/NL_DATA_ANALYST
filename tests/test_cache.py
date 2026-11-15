import answer_cache
import orchestrator

SQL = "SELECT customer_state, COUNT(*) AS n FROM customers GROUP BY 1 ORDER BY n DESC LIMIT 5"
OK = {"is_valid": True, "issue": None, "corrected_sql": None}


def test_normalize_ignores_case_space_and_trailing_punctuation():
    assert answer_cache.normalize("  Orders   by STATE?? ") == answer_cache.normalize("orders by state")


def test_second_identical_question_is_a_free_cache_hit(fake_llm):
    fake = fake_llm(sql_queue=[SQL], critiques=[OK])
    first = orchestrator.answer_question("orders by state")
    calls_after_first = len(fake.calls)
    second = orchestrator.answer_question("Orders by state?")
    assert first["status"] == second["status"] == "success"
    assert second["cached_hit"] is True and not first.get("cached_hit")
    assert len(fake.calls) == calls_after_first            # zero new API calls
    assert second["usage"]["cost_usd"] == 0.0 and second["usage"]["calls"] == 0
    assert second["rows"] == first["rows"]


def test_only_successes_are_cached(fake_llm):
    fake_llm(scope=False)
    assert orchestrator.answer_question("weather today")["status"] == "out_of_scope"
    assert not answer_cache.contains("weather today")


def test_disable_bypasses_cache(fake_llm):
    fake_llm(sql_queue=[SQL, SQL], critiques=[OK, OK])
    orchestrator.answer_question("orders by state")
    answer_cache.disable()
    again = orchestrator.answer_question("orders by state")
    assert not again.get("cached_hit")


def test_cached_result_is_a_copy(fake_llm):
    fake_llm(sql_queue=[SQL], critiques=[OK])
    orchestrator.answer_question("orders by state")
    a = orchestrator.answer_question("orders by state")
    a["rows"].clear()
    assert orchestrator.answer_question("orders by state")["rows"]


def test_is_cached_peeks_without_side_effects(fake_llm):
    fake_llm(sql_queue=[SQL], critiques=[OK])
    assert not orchestrator.is_cached("orders by state")
    orchestrator.answer_question("orders by state")
    assert orchestrator.is_cached("ORDERS BY STATE")
    assert not orchestrator.is_cached("")


def test_lru_evicts_oldest(monkeypatch):
    monkeypatch.setattr(answer_cache, "MAX_ENTRIES", 2)
    for q in ("a", "b", "c"):
        answer_cache.put(q, {"status": "success", "rows": []})
    assert not answer_cache.contains("a") and answer_cache.contains("b") and answer_cache.contains("c")


def test_file_roundtrip_and_corrupt_file_is_harmless(tmp_path):
    answer_cache.put("q1", {"status": "success", "rows": [(1, "x")], "columns": ["a", "b"]})
    f = tmp_path / "c.json"
    assert answer_cache.save_file(f) == 1
    answer_cache.clear()
    assert answer_cache.load_file(f) == 1
    assert answer_cache.get("q1")["rows"] == [(1, "x")]
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    assert answer_cache.load_file(bad) == 0
    assert answer_cache.load_file(tmp_path / "missing.json") == 0
