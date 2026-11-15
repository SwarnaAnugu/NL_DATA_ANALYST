from types import SimpleNamespace

from orchestrator import answer_question
from usage_tracking import Ledger, price_for, track

OK = {"is_valid": True, "issue": None, "corrected_sql": None}


def test_price_lookup_and_ledger_math():
    assert price_for("claude-haiku-4-5") == (1.0, 5.0) and price_for("claude-sonnet-4-6") == (3.0, 15.0)
    assert price_for("mystery-model") == (3.0, 15.0)            # unknown = priced high, never silently free
    led = Ledger()
    led.record("claude-sonnet-4-6", SimpleNamespace(input_tokens=1_000_000, output_tokens=1_000_000))
    led.record("claude-haiku-4-5", SimpleNamespace(input_tokens=1_000_000, output_tokens=0))
    assert led.summary() == {"calls": 2, "input_tokens": 2_000_000, "output_tokens": 1_000_000, "cost_usd": 19.0}


def test_missing_usage_is_ignored(fake_llm):
    fake_llm(sql_queue=["SELECT COUNT(*) FROM orders"], critiques=[OK])     # stub responses carry no usage
    r = answer_question("How many orders?")
    assert r["usage"]["calls"] == 0 and r["usage"]["cost_usd"] == 0


def test_usage_is_recorded_across_worker_threads(fake_llm):
    fake = fake_llm(sql_queue=["SELECT COUNT(*) FROM orders"], critiques=[OK])
    orig = fake._create
    def with_usage(**kw):
        resp = orig(**kw)
        resp.usage = SimpleNamespace(input_tokens=1000, output_tokens=100)
        return resp
    fake.messages.create = with_usage
    r = answer_question("How many orders?")
    # scope + ambiguity (threads), generate, critique (thread), explain + soundness (threads) = 6 calls
    assert r["usage"]["calls"] == 6 and r["usage"]["input_tokens"] == 6000 and r["usage"]["cost_usd"] > 0


def test_ledgers_are_isolated_between_questions():
    with track() as a:
        with track() as b:
            b.record("claude-haiku-4-5", SimpleNamespace(input_tokens=10, output_tokens=0))
        assert a.summary()["calls"] == 0 and b.summary()["calls"] == 1
