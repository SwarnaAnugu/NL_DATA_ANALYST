import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent / "src"))

import streamlit as st
import pandas as pd
from orchestrator import answer_question
from sql_generation.schema_context import build_schema_context

st.title("NL Data Analyst")
st.caption("Ask a question about the Olist Brazilian e-commerce dataset")

st.markdown(
    "This dataset covers real Brazilian e-commerce orders from 2016–2018 — "
    "customers, products, sellers, payments, and reviews. Ask about revenue, "
    "order volume, delivery times, product categories, customer locations, and more."
)

with st.expander("For the technically curious: database schema"):
    st.code(build_schema_context(), language="text")

# The chat history: a list of dicts, each either a user turn or an
# assistant turn. This is what replaces the single overwriting text box —
# every past question and answer stays visible.
if "messages" not in st.session_state:
    st.session_state.messages = []

# Tracks the accumulated original question + any clarification replies
# so far, so multi-round clarification doesn't lose earlier context.
if "pending_original_question" not in st.session_state:
    st.session_state.pending_original_question = None


def render_assistant_result(result: dict):
    """Renders one assistant turn's content based on its status."""
    if result["status"] == "clarify":
        st.info(result["question"])

    elif result["status"] == "out_of_scope":
        st.warning(result["reason"])

    elif result["status"] == "failed":
        st.error(result["reason"])

    elif result["status"] == "success":
        st.write(result["explanation"])

        if result["attempts"] == 1:
            st.caption("✓ Generated correctly on the first try")
        else:
            st.caption("⚠ Required one self-correction before this was valid")

        chart = result["chart"]
        if chart["chart_type"] != "none":
            df = pd.DataFrame(result["rows"], columns=result["columns"])
            if chart["chart_type"] == "bar":
                st.bar_chart(df, x=chart["x"], y=chart["y"])
            elif chart["chart_type"] == "line":
                st.line_chart(df, x=chart["x"], y=chart["y"])

        with st.expander("View generated SQL"):
            st.code(result["sql"], language="sql")

        with st.expander("View raw data"):
            st.dataframe(pd.DataFrame(result["rows"], columns=result["columns"]))


# Replay the full chat history on every rerun, so nothing disappears.
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        if msg["role"] == "user":
            st.write(msg["content"])
        else:
            render_assistant_result(msg["content"])

# Example question buttons feed straight into the same pipeline as typed
# input, using a small trick: set a flag, then handle it below.
st.write("Try one of these, or ask your own below:")
example_questions = [
    "What is the total revenue by customer state?",
    "Which product category has the highest total revenue?",
    "What is the average delivery time by region?",
]
cols = st.columns(len(example_questions))
example_clicked = None
for col, q in zip(cols, example_questions):
    if col.button(q):
        example_clicked = q
        st.session_state.pending_original_question = None

user_input = st.chat_input("Ask a question, or answer the clarifying question above")

# Whichever happened this run — a typed message or an example click —
# becomes the new user turn.
new_user_message = user_input or example_clicked

if new_user_message:
    st.session_state.messages.append({"role": "user", "content": new_user_message})

    if st.session_state.pending_original_question:
        # This message is answering a previous clarifying question —
        # stitch it onto the accumulated thread so far, not just the
        # most recent fragment.
        enriched_question = (
            f"{st.session_state.pending_original_question}\n\n"
            f"Clarification: {new_user_message}"
        )
        with st.spinner("Thinking..."):
            result = answer_question(enriched_question)
    else:
        enriched_question = new_user_message
        with st.spinner("Thinking..."):
            result = answer_question(new_user_message)

    if result["status"] == "clarify":
        # Keep accumulating: the next reply should build on everything
        # asked and answered so far, not just this latest message.
        st.session_state.pending_original_question = enriched_question
    else:
        st.session_state.pending_original_question = None

    st.session_state.messages.append({"role": "assistant", "content": result})
    st.rerun()