from orchestrator import answer_question, MAX_ATTEMPTS

OK = {"is_valid": True, "issue": None, "corrected_sql": None}


def test_happy_path(fake_llm):
    fake_llm(sql_queue=["SELECT COUNT(*) FROM orders"], critiques=[OK])
    r = answer_question("How many orders?")
    assert r["status"] == "success" and r["attempts"] == 1
    assert r["rows"] == [(99441,)] and r["caveat"] is None and "latency_s" in r


def test_out_of_scope_stops_early(fake_llm):
    fake = fake_llm(scope=False)
    r = answer_question("What's the weather?")
    assert r["status"] == "out_of_scope" and not any("writing SQLite" in c for c in fake.calls)


def test_ambiguous_asks_for_clarification(fake_llm):
    r = (fake_llm(ambiguous=True), answer_question("best products?"))[1]
    assert r["status"] == "clarify" and r["question"]


def test_caveat_is_passed_through_verbatim(fake_llm):
    fake_llm(sql_queue=["SELECT COUNT(*) FROM orders"], critiques=[OK], caveat="Right-censored!")
    assert answer_question("churn?")["caveat"] == "Right-censored!"


def test_critic_correction_used_once(fake_llm):
    bad = {"is_valid": False, "issue": "double count", "corrected_sql": "SELECT COUNT(*) FROM orders"}
    fake_llm(sql_queue=["SELECT 1"], critiques=[bad, OK])
    r = answer_question("How many orders?")
    assert r["status"] == "success" and r["attempts"] == 2


def test_critic_rejects_twice_fails_gracefully(fake_llm):
    bad = {"is_valid": False, "issue": "nope", "corrected_sql": "SELECT 2"}
    fake_llm(sql_queue=["SELECT 1"], critiques=[bad, bad])
    r = answer_question("q")
    assert r["status"] == "failed" and "rephras" in r["reason"].lower()


def test_execution_error_triggers_one_repair(fake_llm):
    fake_llm(sql_queue=["SELECT nope FROM orders", "SELECT COUNT(*) FROM orders"], critiques=[OK, OK])
    r = answer_question("How many orders?")
    assert r["status"] == "success" and r["attempts"] == 2


def test_execution_error_after_repair_fails_without_leaking_error(fake_llm):
    fake_llm(sql_queue=["SELECT nope FROM orders", "SELECT nope2 FROM orders"], critiques=[OK, OK])
    r = answer_question("q")
    assert r["status"] == "failed" and "nope" not in r["reason"] and "nope" in r["detail"]


def test_attempts_never_exceed_cap(fake_llm):
    fake_llm(sql_queue=["SELECT nope FROM orders", "SELECT nope FROM orders"], critiques=[OK, OK])
    r = answer_question("q")
    assert r.get("attempts", MAX_ATTEMPTS) <= MAX_ATTEMPTS


def test_empty_result_is_handled(fake_llm):
    fake_llm(sql_queue=["SELECT * FROM orders WHERE 1=0"], critiques=[OK])
    r = answer_question("q")
    assert r["status"] == "success" and r["rows"] == [] and "no rows" in r["explanation"]


def test_truncation_adds_note(fake_llm):
    fake_llm(sql_queue=["SELECT order_id FROM orders"], critiques=[OK])
    r = answer_question("list orders")
    assert r["truncated"] and "1,000" in r["caveat"]


def test_api_outage_becomes_friendly_failure(fake_llm):
    fake = fake_llm()
    def boom(**kw): raise RuntimeError("connection reset")
    fake.messages.create = boom
    r = answer_question("q")
    assert r["status"] == "failed" and "connection reset" not in r["reason"]


def test_progress_callback_receives_stages_in_order(fake_llm):
    fake_llm(sql_queue=["SELECT COUNT(*) FROM orders"], critiques=[OK])
    seen = []
    answer_question("How many orders?", progress=lambda stage, msg: seen.append(stage))
    assert seen[0] == "check"
    assert seen.index("generate") < seen.index("critique") < seen.index("execute") < seen.index("explain")


def test_broken_progress_callback_does_not_break_pipeline(fake_llm):
    fake_llm(sql_queue=["SELECT COUNT(*) FROM orders"], critiques=[OK])
    def bad(stage, msg): raise ValueError("ui exploded")
    assert answer_question("How many orders?", progress=bad)["status"] == "success"


def test_explainer_never_gets_more_than_40_rows(fake_llm):
    fake = fake_llm()
    seen = {}
    orig = fake.messages.create
    def spy(**kw):
        if "explaining a database query result" in kw.get("system", ""):
            seen["content"] = kw["messages"][0]["content"]
        return orig(**kw)
    fake.messages.create = spy
    from answering.explain_result import explain_result
    explain_result("q", ["n"], [(i,) for i in range(500)])
    assert "(The result has 500 rows in total" in seen["content"] and "(499,)" not in seen["content"]
