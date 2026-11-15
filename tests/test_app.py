"""Drives the real Streamlit script with Streamlit's AppTest and a stub LLM."""
import os
import sys
from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py")
OK = {"is_valid": True, "issue": None, "corrected_sql": None}


def _app(monkeypatch, fake_llm, **kw):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    fake_llm(**kw)
    sys.modules.pop("usage_limits", None)
    import usage_limits
    usage_limits.reset_for_tests()
    return AppTest.from_file(APP, default_timeout=30)


def test_success_with_caveat_and_chart(monkeypatch, fake_llm):
    at = _app(monkeypatch, fake_llm,
              sql_queue=["SELECT customer_state, COUNT(*) AS n FROM customers GROUP BY 1 ORDER BY n DESC LIMIT 5"],
              critiques=[OK], caveat="Right-censored warning.")
    at.run()
    assert not at.exception
    at.chat_input[0].set_value("orders by state").run()
    assert not at.exception, at.exception
    assert any("Right-censored warning." in w.value for w in at.warning)
    # one chart for the answer, one on the Benchmark tab
    assert len(at.get("plotly_chart")) == 2
    at.run()   # AppTest keeps pre-st.rerun() elements until the next run; a browser replaces them
    assert [m.name for m in at.chat_message] == ["user", "assistant"]


def test_clarify_then_answer_keeps_context(monkeypatch, fake_llm):
    at = _app(monkeypatch, fake_llm, ambiguous=True)
    at.run()
    at.chat_input[0].set_value("best products?").run()
    assert any("Best by what?" in i.value for i in at.info)
    assert at.session_state.pending_original_question == "best products?"


def test_session_limit_blocks_with_friendly_message(monkeypatch, fake_llm):
    at = _app(monkeypatch, fake_llm, scope=False)
    at.run()
    at.session_state["questions_used"] = 15
    at.chat_input[0].set_value("anything").run()
    assert any("per session" in e.value for e in at.error)


def test_missing_api_key_stops_with_message(monkeypatch, fake_llm):
    at = _app(monkeypatch, fake_llm)
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    at.run()
    assert any("ANTHROPIC_API_KEY" in e.value for e in at.error)


def test_tabs_header_and_benchmark_render_without_a_question(monkeypatch, fake_llm):
    at = _app(monkeypatch, fake_llm)
    at.run()
    assert not at.exception
    assert [t.label for t in at.tabs] == ["💬 Ask", "📊 Benchmark", "🛡️ How it works"]
    assert any(m.label == "Orders" and m.value == "99,441" for m in at.metric)
    assert any(m.label == "Silent wrong answers" for m in at.metric)


def test_pipeline_trace_is_stored_and_shown(monkeypatch, fake_llm):
    at = _app(monkeypatch, fake_llm, sql_queue=["SELECT COUNT(*) FROM orders"], critiques=[OK])
    at.run()
    at.chat_input[0].set_value("How many orders?").run()
    assert not at.exception
    trace = at.session_state.messages[-1]["content"]["trace"]
    assert any("Writing SQL" in t for t in trace) and any("read-only" in t for t in trace)
    assert any("Pipeline trace" in e.label for e in at.expander)


def test_example_button_runs_a_question(monkeypatch, fake_llm):
    at = _app(monkeypatch, fake_llm, scope=False)
    at.run()
    at.button[0].click().run()
    assert not at.exception
    assert at.session_state.messages[0]["role"] == "user"
    assert any("only answer questions" in w.value for w in at.warning)


def test_follow_up_uses_history_and_shows_interpretation(monkeypatch, fake_llm):
    at = _app(monkeypatch, fake_llm,
              rewrite="How many orders per customer state?",
              sql_queue=["SELECT COUNT(*) FROM orders", "SELECT customer_state, COUNT(*) AS n FROM customers GROUP BY 1 ORDER BY n DESC LIMIT 5"],
              critiques=[OK, OK])
    at.run()
    at.chat_input[0].set_value("How many orders are there?").run()
    at.chat_input[0].set_value("and by state?").run()
    assert not at.exception, at.exception
    last = at.session_state.messages[-1]["content"]
    assert last["status"] == "success" and last["was_rewritten"] is True
    at.run()
    assert any("Interpreted as" in c.value for c in at.caption)


def test_example_groups_include_follow_ups_and_break_it():
    from examples import EXAMPLES, WARMABLE
    assert any(g.startswith("Follow-ups") for g in EXAMPLES) and "Try to break it" in EXAMPLES
    assert all(q in sum(EXAMPLES.values(), []) for q in WARMABLE)


def test_cached_example_is_instant_and_free_of_budget(monkeypatch, fake_llm):
    import answer_cache
    import orchestrator
    q = "How many customers are there?"
    fake = fake_llm(sql_queue=["SELECT COUNT(*) AS n FROM customers"], critiques=[OK])
    orchestrator.answer_question(q)                       # warm the cache
    n_calls = len(fake.calls)
    at = _app(monkeypatch, lambda **kw: fake)
    at.run()
    at.chat_input[0].set_value(q).run()
    assert not at.exception, at.exception
    assert at.session_state["questions_used"] == 0         # cache hit is free
    assert len(fake.calls) == n_calls                      # and made no API call
    at.run()
    assert any("Instant (cached)" in c.value for c in at.caption)
