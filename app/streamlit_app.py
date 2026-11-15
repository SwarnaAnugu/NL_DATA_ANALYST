import os
import sys
import time
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent / "src"))

import pandas as pd
import streamlit as st

from benchmark_view import (VARIANT_LABELS, build_figure as benchmark_figure, load_results, load_scenarios,
                            summarize, summarize_scenarios)
from charting.render import build_figure
import answer_cache
from config import MAX_QUESTION_CHARS, REPO_ROOT, ensure_db
from examples import EXAMPLES, WARM_CACHE_PATH
from feedback import record_feedback
from orchestrator import answer_question, is_cached
from overview import dataset_overview
from sql_generation.schema_context import build_schema_context
from usage_limits import SESSION_LIMIT, try_consume_daily

REPO_URL = "https://github.com/SwarnaAnugu/NL_DATA_ANALYST"

st.set_page_config(page_title="NL Data Analyst", page_icon="📊", layout="centered")

st.markdown("""
<style>
.hero-title {font-size: 2.6rem; font-weight: 800; line-height: 1.1; margin: 0 0 .25rem 0;
  background: linear-gradient(90deg, #2563eb, #7c3aed); -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;}
.hero-sub {font-size: 1.1rem; opacity: .8; margin-bottom: 1rem;}
.pill {display: inline-block; padding: .15rem .6rem; margin: 0 .25rem .35rem 0; border-radius: 999px;
  font-size: .78rem; background: rgba(37,99,235,.12); color: #2563eb; border: 1px solid rgba(37,99,235,.25);}
div[data-testid="stMetric"] {background: rgba(124,58,237,.06); border: 1px solid rgba(124,58,237,.18);
  padding: .6rem .9rem; border-radius: .75rem;}
.stButton > button {border-radius: .65rem; text-align: left;}
footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

if not os.environ.get("ANTHROPIC_API_KEY"):
    st.error("No ANTHROPIC_API_KEY found. Add it to .env (local) or the app's Secrets (Streamlit Cloud).")
    st.stop()


@st.cache_resource(show_spinner="Unpacking the demo database (first start only)...")
def _prepare_database():
    return str(ensure_db())


@st.cache_data(show_spinner=False)
def _overview():
    return dataset_overview()


_prepare_database()

# ------------------------------------------------------------------ header
st.markdown('<div class="hero-title">NL Data Analyst</div>', unsafe_allow_html=True)
st.markdown('<div class="hero-sub">Ask a database a question in plain English. Get an answer you can trust, '
            'with the SQL, a chart, and a warning when the number would mislead.</div>', unsafe_allow_html=True)
st.markdown("".join(f'<span class="pill">{t}</span>' for t in
                    ["Claude · Haiku + Sonnet", "Schema-aware text-to-SQL", "Self-critique + repair",
                     "Read-only by construction", "Benchmarked vs naive prompting"]), unsafe_allow_html=True)

ov = _overview()
if ov.get("orders"):
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Orders", f"{ov['orders']:,}")
    c2.metric("Customers", f"{ov['customers']:,}")
    c3.metric("Item revenue", f"R${ov['revenue'] / 1e6:,.1f}M")
    c4.metric("Orders from", f"{ov['first'][:4]}–{ov['last'][2:4]}")

with st.sidebar:
    st.header("About")
    st.markdown(
        "Real Brazilian e-commerce data ([Olist](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce), "
        "CC BY-NC-SA 4.0): 9 related tables, ~100k orders.\n\n"
        f"[Source code & write-up on GitHub]({REPO_URL})"
    )
    st.caption(f"Demo limit: {SESSION_LIMIT} questions per session, to keep API costs bounded.")
    if st.button("Clear conversation", width="stretch"):
        st.session_state.messages = []
        st.session_state.pending_original_question = None
        st.rerun()

@st.cache_resource
def _load_warm_cache() -> int:
    """Load the pre-computed example answers once per server process."""
    return answer_cache.load_file(REPO_ROOT / WARM_CACHE_PATH)


_load_warm_cache()

if "messages" not in st.session_state:
    st.session_state.messages = []
if "pending_original_question" not in st.session_state:
    st.session_state.pending_original_question = None
if "questions_used" not in st.session_state:
    st.session_state.questions_used = 0

def safe_md(text: str) -> str:
    """LLM text goes through Streamlit markdown, where a pair of dollar signs
    (R$1,258,681 ... R$1,205,006) is parsed as LaTeX and turns the text red.
    Escape them so currency renders as currency."""
    return (text or "").replace("$", "\\$")


def render_assistant_result(result: dict, index: int, question: str):
    """Renders one assistant turn based on its status."""
    status = result["status"]

    if status == "clarify":
        st.info(f"**I need one detail before I run this.** {safe_md(result['question'])}", icon="❓")
    elif status == "out_of_scope":
        st.warning(safe_md(result["reason"]), icon="🚧")
    elif status == "failed":
        st.error(safe_md(result["reason"]))
    elif status == "success":
        answer = safe_md(result["explanation"])
        st.markdown(f"#### {answer}" if len(answer) <= 140 else f"##### {answer}")

        if result.get("caveat"):
            st.warning(f"**Heads up:** {safe_md(result['caveat'])}", icon="⚠️")

        fig = build_figure(result["chart"], result["columns"], result["rows"])
        if fig is not None:
            st.plotly_chart(fig, width="stretch", key=f"chart-{index}", config={"displayModeBar": False})

        if result.get("was_rewritten"):
            st.caption(f"↪ Interpreted as: *{safe_md(result['standalone_question'])}*")
        retry = "needed 1 self-correction" if result["attempts"] > 1 else "passed review first try"
        if result.get("cached_hit"):
            st.caption(f"⚡ Instant (cached) · {len(result['rows']):,} row(s) · {result.get('latency_s', '?')}s · no API cost")
        else:
            cost = (result.get("usage") or {}).get("cost_usd")
            cost_txt = f" · ≈ \\${cost:.3f}" if cost else ""
            st.caption(f"✓ {retry} · {len(result['rows']):,} row(s) · {result.get('latency_s', '?')}s{cost_txt}")

        with st.expander("View generated SQL"):
            st.code(result["sql"], language="sql")
        with st.expander("View raw data"):
            df = pd.DataFrame(result["rows"], columns=result["columns"])
            st.dataframe(df, width="stretch")
            st.download_button("Download CSV", df.to_csv(index=False), "result.csv", "text/csv", key=f"dl-{index}")

    if result.get("trace"):
        with st.expander("Pipeline trace"):
            for line in result["trace"]:
                st.markdown(f"- {line}")

    if status == "success":
        rating = st.feedback("thumbs", key=f"fb-{index}")
        if rating is not None and not st.session_state.get(f"fb-saved-{index}"):
            record_feedback(question, result.get("sql"), "up" if rating == 1 else "down")
            st.session_state[f"fb-saved-{index}"] = True


tab_ask, tab_bench, tab_how = st.tabs(["💬 Ask", "📊 Benchmark", "🛡️ How it works"])

# ================================================================== ASK
example_clicked = None
with tab_ask:
    for i, msg in enumerate(st.session_state.messages):
        with st.chat_message(msg["role"]):
            if msg["role"] == "user":
                st.write(msg["content"])
            else:
                render_assistant_result(msg["content"], i, msg.get("question", ""))

    def example_picker():
        # Follow-up examples only make sense after an answer exists.
        has_answer = any(m["role"] == "assistant" and m["content"].get("status") == "success"
                         for m in st.session_state.messages)
        groups = [g for g in EXAMPLES if has_answer or not g.startswith("Follow-ups")]
        group = st.segmented_control("Examples", groups, default=groups[0],
                                     label_visibility="collapsed", key="example_group") or groups[0]
        cols = st.columns(2)
        for n, q in enumerate(EXAMPLES[group]):
            if cols[n % 2].button(q, key=f"ex-{group}-{n}", width="stretch"):
                return q
        return None

    if not st.session_state.messages:
        st.markdown("**Try one, or type your own question below:**")
        example_clicked = example_picker()
    else:
        with st.expander("More example questions"):
            example_clicked = example_picker()

    with st.expander("Database schema and dataset notes"):
        st.code(build_schema_context(), language="text")

# ================================================================== BENCHMARK
with tab_bench:
    results = load_results()
    if not results:
        st.info("No benchmark results yet. Run `python eval/run_benchmark.py`.")
    else:
        s = summarize(results)
        v = s["variants"]
        st.markdown(f"**Does the pipeline really hallucinate less than a plain prompt?** "
                    f"{s['n_questions']} questions with hand-written gold SQL, {s['repeats']} runs each. "
                    f"A result counts as correct only if it matches the gold result set.")
        m1, m2, m3 = st.columns(3)
        m1.metric("Silent wrong answers", f"{v['full']['wrong']:.0f}%", f"{v['full']['wrong'] - v['naive']['wrong']:+.0f} pts vs naive",
                  delta_color="inverse")
        m2.metric("Clarify / decline / refuse handled", f"{v['full']['non_answer_ok']:.0f}%",
                  f"{v['full']['non_answer_ok'] - v['naive']['non_answer_ok']:+.0f} pts vs naive")
        m3.metric("Median latency", f"{v['full']['median_latency']:.1f}s",
                  f"{v['full']['median_latency'] - v['naive']['median_latency']:+.1f}s vs naive", delta_color="off")
        st.plotly_chart(benchmark_figure(s), width="stretch", config={"displayModeBar": False})
        groups = sorted({g for d in v.values() for g in d["by_group"]})
        table = pd.DataFrame({VARIANT_LABELS[k]: {g: f"{d['by_group'].get(g, float('nan')):.0f}%" for g in groups}
                              for k, d in v.items()})
        st.markdown("**Accuracy by question type**")
        st.dataframe(table, width="stretch")
        st.caption(
            "Honest reading: most of the accuracy gain comes from giving the model verified facts about the data "
            "(single prompt + notes). The extra stages buy behaviour a single call can't do: asking when a question is "
            "ambiguous, declining unrelated or destructive requests, and attaching caveats. The cost is latency. "
            "46 questions on one dataset is a small sample: read differences of a few points as noise."
        )

    scenarios = load_scenarios()
    if scenarios:
        ss = summarize_scenarios(scenarios)
        st.divider()
        st.markdown(f"#### Stress test: {ss['total']} messy real-world scenarios")
        st.markdown("Typos, Portuguese and Spanish, multi-part questions, follow-ups, empty and huge results, "
                    "prompt injection, pasted SQL, gibberish. Each is checked automatically against the database.")
        sc1, sc2 = st.columns([1, 2])
        sc1.metric("Passed", f"{ss['passed']}/{ss['total']}")
        sc2.dataframe(pd.DataFrame([{"Group": g, "Passed": f"{ok}/{n}"} for g, (ok, n) in ss["by_group"].items()]),
                      hide_index=True, width="stretch")
        with st.expander("See every scenario"):
            st.dataframe(pd.DataFrame([{"": "✅" if x["passed"] else "❌", "Group": x["group"], "Input": x["question"],
                                        "Outcome": x["status"]} for x in scenarios]), hide_index=True, width="stretch")

# ================================================================== HOW IT WORKS
with tab_how:
    st.markdown("**Every question passes through these stages.** Each exists to stop one specific failure of naive text-to-SQL.")
    st.graphviz_chart("""
    digraph G {
      rankdir=LR; bgcolor="transparent"; node [shape=box, style="rounded,filled", fillcolor="#eef2ff", color="#2563eb", fontname="Helvetica", fontsize=11];
      edge [color="#6b7280"];
      Q [label="Question", fillcolor="#ffffff"];
      S [label="Scope check\\n(Haiku)"]; A [label="Ambiguity check\\n(Haiku)"];
      G [label="SQL generation\\n(Sonnet + schema\\n+ dataset notes)"]; C [label="Self-critique\\n(Sonnet, thinking)"];
      X [label="Validate + run\\nread-only"]; R [label="Answer + chart\\n+ caveat"];
      D [label="Decline", fillcolor="#fef3c7", color="#f59e0b"]; K [label="Ask user", fillcolor="#fef3c7", color="#f59e0b"];
      Q -> S -> A -> G -> C -> X -> R;
      S -> D [label=" off-topic", fontsize=9]; A -> K [label=" ambiguous", fontsize=9];
      C -> G [label=" repair x1", fontsize=9, style=dashed]; X -> G [label=" db error\\nrepair x1", fontsize=9, style=dashed];
    }
    """)
    st.markdown("""
| Failure of a naive prompt | Defence here |
|---|---|
| Guesses when a question has several meanings | Ambiguity check asks instead |
| `customer_id` is per *order*, so customers get over-counted | Verified dataset notes: use `customer_unique_id` |
| JOINs multiply rows and inflate sums | Notes forbid the pattern; the critic reviews the SQL |
| Right number, misleading meaning (repeat rate with a censored window) | Soundness check attaches a specific caveat, shown verbatim |
| LLM writes `DELETE` / `DROP` | Static validator **and** a SQLite connection opened `mode=ro` |
| Runaway or huge queries | 10 s time limit, 1,000-row cap |
| Errors surface as stack traces | One repair attempt, then a friendly message; the pipeline never raises |
""")
    st.markdown(f"**Stack:** Python · SQLite · Anthropic API · Streamlit · Plotly · pytest (60+ tests, LLM stubbed). "
                f"[Read the design decisions on GitHub]({REPO_URL}).")

# ================================================================== HANDLE INPUT
user_input = st.chat_input("Ask a question about the data... (follow-ups work too)", max_chars=MAX_QUESTION_CHARS)
new_user_message = user_input or example_clicked

if new_user_message:
    st.session_state.messages.append({"role": "user", "content": new_user_message})

    with tab_ask:
        with st.chat_message("user"):
            st.write(new_user_message)

        trace = []
        history = [m["content"]["standalone_question"] for m in st.session_state.messages
                   if m["role"] == "assistant" and m["content"].get("status") == "success"
                   and m["content"].get("standalone_question")][-4:]
        # A cached answer costs nothing, so it must not eat the session/daily budget.
        # (With history, the follow-up rewrite runs first, so only fresh questions are checked.)
        free_cached = (not history and not st.session_state.pending_original_question
                       and is_cached(new_user_message))
        if not free_cached and st.session_state.questions_used >= SESSION_LIMIT:
            result = {"status": "failed", "reason": (
                f"This demo allows {SESSION_LIMIT} questions per session to keep API costs bounded. "
                "Refresh the page to start a new session, or run the app locally with your own API key.")}
        elif not free_cached and not try_consume_daily():
            result = {"status": "failed", "reason": (
                "The demo has reached its daily question budget. Please try again tomorrow, "
                "or run it locally with your own API key (see the README).")}
        else:
            if not free_cached:
                st.session_state.questions_used += 1
            if st.session_state.pending_original_question:
                enriched_question = (f"{st.session_state.pending_original_question}\n\n"
                                     f"Clarification: {new_user_message}")
            else:
                enriched_question = new_user_message

            with st.chat_message("assistant"):
                status_box = st.status("Working on it...", expanded=True)
                started = time.monotonic()

                def on_progress(stage, message):
                    trace.append(message)
                    status_box.write(f"▸ {message}")

                result = answer_question(enriched_question, progress=on_progress, history=history)
                status_box.update(label=f"Done in {time.monotonic() - started:.1f}s", state="complete", expanded=False)

            # While the assistant keeps asking for clarification, keep accumulating context.
            st.session_state.pending_original_question = enriched_question if result["status"] == "clarify" else None

        result["trace"] = trace
        st.session_state.messages.append({"role": "assistant", "content": result, "question": new_user_message})
    st.rerun()
