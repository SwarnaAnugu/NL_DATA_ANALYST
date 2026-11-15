import pytest
from config import MAX_QUESTION_CHARS
from orchestrator import answer_question, clean_question

OK = {"is_valid": True, "issue": None, "corrected_sql": None}


@pytest.mark.parametrize("text", ["", "   ", "\n\t ", None, 42, "\x00\x01\x02"])
def test_empty_or_garbage_input_rejected_without_any_api_call(fake_llm, text):
    fake = fake_llm()
    r = answer_question(text)
    assert r["status"] == "failed" and r["reason"] and fake.calls == []


def test_overlong_input_rejected_without_api_call(fake_llm):
    fake = fake_llm()
    r = answer_question("a" * (MAX_QUESTION_CHARS + 1))
    assert r["status"] == "failed" and str(MAX_QUESTION_CHARS) in r["reason"] and fake.calls == []


def test_clean_question_strips_control_chars_and_whitespace():
    assert clean_question("  How   many\x00 orders?\t") == ("How many orders?", None)


def test_unicode_and_quotes_pass_through(fake_llm):
    fake_llm(sql_queue=["SELECT COUNT(*) FROM orders"], critiques=[OK])
    r = answer_question("Quantos pedidos vieram de São Paulo? ' OR 1=1 --")
    assert r["status"] == "success"


def test_follow_up_is_rewritten_and_reported(fake_llm):
    fake_llm(rewrite="How many orders per customer state?", sql_queue=["SELECT COUNT(*) FROM orders"], critiques=[OK])
    r = answer_question("and by state?", history=["How many orders are there?"])
    assert r["standalone_question"] == "How many orders per customer state?" and r["was_rewritten"] is True


def test_first_question_makes_no_rewrite_call(fake_llm):
    fake = fake_llm(sql_queue=["SELECT COUNT(*) FROM orders"], critiques=[OK])
    r = answer_question("How many orders?")
    assert r["was_rewritten"] is False and not any("rewrite follow-up" in c for c in fake.calls)


def test_rewrite_failure_falls_back_to_original_question(fake_llm):
    fake_llm(rewrite="BOOM", sql_queue=["SELECT COUNT(*) FROM orders"], critiques=[OK])
    r = answer_question("How many orders?", history=["earlier"])
    assert r["status"] == "success" and r["standalone_question"] == "How many orders?"


def test_result_always_carries_standalone_question_even_on_failure(fake_llm):
    fake = fake_llm()
    def boom(**kw): raise RuntimeError("down")
    fake.messages.create = boom
    r = answer_question("q")
    assert r["status"] == "failed" and r["standalone_question"] == "q"
