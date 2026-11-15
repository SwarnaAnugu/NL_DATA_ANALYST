import contextvars
import logging
import time
from concurrent.futures import ThreadPoolExecutor

from sql_generation.ambiguity_check import check_ambiguity
from sql_generation.generate_sql import generate_sql, critique_sql
from sql_generation.schema_context import build_schema_context
from sql_generation.soundness_check import check_soundness
from db.execute_query import execute_query
from charting.chart_selector import select_chart
from answering.explain_result import explain_result
from sql_generation.scope_check import check_scope
from sql_generation.contextualize import contextualize_question
from config import MAX_QUESTION_CHARS
from usage_tracking import track
import answer_cache
import re

log = logging.getLogger(__name__)

# Total SQL attempts per question: the first try plus at most one repair,
# whether the repair is triggered by the critic or by an execution error.
MAX_ATTEMPTS = 2

REPHRASE_MSG = (
    "I wasn't able to turn this into a specific data query. Try rephrasing it as a "
    "more direct question — for example, 'how many orders are in the dataset?' "
    "instead of a broader or more open-ended question."
)
OUT_OF_SCOPE_MSG = (
    "I can only answer questions about this e-commerce dataset — try asking about "
    "revenue, orders, customers, products, or reviews."
)
SERVICE_ERROR_MSG = (
    "Something went wrong while contacting the language model. Please try again in a moment."
)


def _submit(pool, fn, *args):
    """pool.submit that carries the current context (and so the usage ledger) into the worker thread."""
    return pool.submit(contextvars.copy_context().run, fn, *args)


def _emit(progress, stage: str, message: str) -> None:
    """Report pipeline progress to an optional callback (the UI's live trace).
    A broken callback must never break the pipeline."""
    if progress is not None:
        try:
            progress(stage, message)
        except Exception:  # noqa: BLE001
            log.exception("progress callback failed")


def clean_question(text) -> tuple[str | None, str | None]:
    """Normalise user input. Returns (cleaned, None) or (None, friendly_error)."""
    if not isinstance(text, str):
        return None, "Please type a question."
    text = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", " ", text)      # control characters
    text = re.sub(r"[ \t]+", " ", text).strip()
    if not text:
        return None, "Please type a question about the data."
    if len(text) > MAX_QUESTION_CHARS:
        return None, f"That question is {len(text)} characters long. Please keep it under {MAX_QUESTION_CHARS}."
    return text, None


def is_cached(user_question: str) -> bool:
    """True if this exact question would be answered from the cache (no API cost)."""
    cleaned, error = clean_question(user_question)
    return error is None and answer_cache.contains(cleaned)


def answer_question(user_question: str, progress=None, history=None) -> dict:
    """
    Orchestrates the full pipeline:
    scope check -> ambiguity check -> generate -> critique -> (at most 1 repair)
    -> execute -> explain -> chart -> soundness caveat.

    Returns a dict, always one of:
      {"status": "out_of_scope", "reason": "..."}
      {"status": "clarify", "question": "..."}
      {"status": "success", "sql": "...", "attempts": 1 or 2, "columns": [...], "rows": [...],
       "truncated": bool, "explanation": "...", "chart": {...}, "caveat": "..." or None}
      {"status": "failed", "reason": "...", "detail": "..."}

    `history` is the list of earlier standalone questions (oldest first). When
    given, follow-ups like "and by state?" are rewritten into standalone
    questions first; the rewrite is returned as `standalone_question`.

    Never raises: any unexpected error (API outage, rate limit, bug) becomes a
    friendly "failed" result so a live demo can't show a stack trace.
    """
    started = time.monotonic()
    cleaned, error = clean_question(user_question)
    if error:
        return {"status": "failed", "reason": error, "detail": "input rejected", "latency_s": 0.0}
    with track() as ledger:
        try:
            standalone = cleaned
            if history:
                _emit(progress, "context", "Resolving this against the conversation so far")
                ctx = contextualize_question(cleaned, history)
                standalone = ctx["standalone_question"]
                if ctx["was_rewritten"]:
                    _emit(progress, "context", f"Interpreted as: {standalone}")
            cached = answer_cache.get(standalone)
            if cached is not None:
                _emit(progress, "cache", "Answered from the cache (identical question seen before)")
                cached.update(cached_hit=True, standalone_question=standalone, was_rewritten=standalone != cleaned)
                cached["usage"] = {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}
                cached["latency_s"] = round(time.monotonic() - started, 2)
                return cached
            result = _answer(standalone, progress)
            result["standalone_question"] = standalone
            result["was_rewritten"] = standalone != cleaned
            answer_cache.put(standalone, result)
        except Exception as exc:  # noqa: BLE001 - deliberate catch-all at the boundary
            log.exception("answer_question crashed")
            result = {"status": "failed", "reason": SERVICE_ERROR_MSG, "detail": repr(exc),
                      "standalone_question": cleaned, "was_rewritten": False}
        result["usage"] = ledger.summary()
    result["latency_s"] = round(time.monotonic() - started, 2)
    return result


def _answer(user_question: str, progress=None) -> dict:
    schema = build_schema_context()

    # The scope and ambiguity checks are independent, so run them together
    # (saves about a second). If the question is out of scope the ambiguity
    # result is simply discarded.
    _emit(progress, "check", "Checking the question is about this dataset and is unambiguous")
    with ThreadPoolExecutor(max_workers=2) as pool:
        scope_f = _submit(pool, check_scope, user_question)
        amb_f = _submit(pool, check_ambiguity, user_question, schema)
        scope_result, ambiguity_result = scope_f.result(), amb_f.result()

    if not scope_result.get("is_in_scope"):
        _emit(progress, "scope", "Question is outside this dataset")
        return {"status": "out_of_scope", "reason": OUT_OF_SCOPE_MSG}
    _emit(progress, "scope", "In scope")

    if ambiguity_result.get("is_ambiguous"):
        _emit(progress, "ambiguity", "Question has several valid readings: asking instead of guessing")
        return {"status": "clarify", "question": ambiguity_result.get("clarifying_question")}
    _emit(progress, "ambiguity", "Unambiguous")

    _emit(progress, "generate", "Writing SQL against the schema and verified dataset notes")
    sql = generate_sql(user_question, schema)
    # Speculative execution: the reviewer almost always approves the first
    # SQL, so run the query and prepare the explanation and caveat while the
    # review is still running. Latency becomes max(review, run + explain)
    # instead of their sum. If the review rejects the SQL the speculative work
    # is simply discarded (a few wasted cents on the rare rejection).
    _emit(progress, "critique", "Self-review (joins, double counting, question match) while the query runs in parallel")
    with ThreadPoolExecutor(max_workers=4) as pool:
        critique_f = _submit(pool, critique_sql, user_question, schema, sql)
        spec = _speculate(pool, user_question, sql)
        critique = critique_f.result()
        if critique.get("is_valid") and spec is not None:
            _emit(progress, "critique_ok", "SQL passed review on the first try")
            _emit(progress, "execute", "Ran on a read-only connection (validated, 10s limit, 1,000-row cap)")
            return _assemble(spec, sql, attempts=1, progress=progress)

    if critique.get("is_valid"):
        _emit(progress, "critique_ok", "SQL passed review on the first try")
        return _run(user_question, schema, sql, attempts=1, progress=progress)

    _emit(progress, "repair", f"Reviewer found a problem ({critique.get('issue') or 'unspecified'}): repairing once")

    # First attempt rejected by the critic: one repair, either the critic's
    # own corrected SQL or a fresh generation told what went wrong.
    corrected_sql = critique.get("corrected_sql")
    if not corrected_sql:
        issue_note = critique.get("issue", "The previous query was invalid.")
        corrected_sql = generate_sql(
            f"{user_question}\n\nNote: a previous attempt at this query had the "
            f"following problem, avoid repeating it: {issue_note}",
            schema,
        )

    if critique_sql(user_question, schema, corrected_sql).get("is_valid"):
        return _run(user_question, schema, corrected_sql, attempts=2, progress=progress)

    return {"status": "failed", "reason": REPHRASE_MSG, "detail": "critic rejected the repaired query"}


def _speculate(pool, question: str, sql: str):
    """Execute `sql` and, if it returned rows, start the explanation and the
    soundness check. Returns None when execution failed or gave no rows, so the
    caller falls back to the normal (repairing) path."""
    exec_result = execute_query(sql)
    if exec_result["status"] != "success" or not exec_result["rows"]:
        return None
    return {
        "exec": exec_result,
        "explain": _submit(pool, explain_result, question, exec_result["columns"], exec_result["rows"]),
        "sound": _submit(pool, check_soundness, question, sql),
    }


def _assemble(spec: dict, sql: str, attempts: int, progress=None) -> dict:
    exec_result = spec["exec"]
    columns, rows = exec_result["columns"], exec_result["rows"]
    _emit(progress, "explain", f"Got {len(rows):,} row(s): writing the answer and checking for misleading-number risks")
    explanation, soundness = spec["explain"].result(), spec["sound"].result()
    chart = select_chart(columns, rows)

    caveat = soundness.get("caveat_text") if soundness.get("needs_caveat") else None
    if exec_result.get("truncated"):
        note = "Only the first 1,000 rows are shown; the answer above is based on those rows."
        caveat = f"{caveat} {note}" if caveat else note

    return {
        "status": "success", "sql": sql, "attempts": attempts,
        "columns": columns, "rows": rows, "truncated": bool(exec_result.get("truncated")),
        "explanation": explanation, "chart": chart, "caveat": caveat,
    }


def _run(question: str, schema: str, sql: str, attempts: int, progress=None) -> dict:
    """Executes SQL that has already passed critique. If the database rejects
    it (bad column, timeout...) and we still have an attempt left, feed the
    error back for one repair. Then add explanation, chart and caveat."""
    _emit(progress, "execute", "Running on a read-only connection (validated, 10s limit, 1,000-row cap)")
    exec_result = execute_query(sql)

    if exec_result["status"] != "success" and attempts < MAX_ATTEMPTS:
        _emit(progress, "repair", "The database rejected the query: feeding the error back for one repair")
        repaired_sql = generate_sql(
            f"{question}\n\nNote: this query failed when executed.\n"
            f"Failed SQL:\n{sql}\nError: {exec_result['reason']}\n"
            f"Write a corrected query that avoids this error.",
            schema,
        )
        if critique_sql(question, schema, repaired_sql).get("is_valid"):
            sql, attempts = repaired_sql, attempts + 1
            exec_result = execute_query(sql)

    if exec_result["status"] != "success":
        return {"status": "failed", "reason": REPHRASE_MSG, "detail": exec_result["reason"]}

    columns = exec_result["columns"]
    rows = exec_result["rows"]

    if not rows:
        return {
            "status": "success", "sql": sql, "attempts": attempts,
            "columns": columns, "rows": [], "truncated": False,
            "explanation": "The query ran successfully but returned no rows — nothing in the data matches that question.",
            "chart": {"chart_type": "none", "reason": "No rows."},
            "caveat": None,
        }

    with ThreadPoolExecutor(max_workers=2) as pool:
        spec = {
            "exec": exec_result,
            "explain": _submit(pool, explain_result, question, columns, rows),
            "sound": _submit(pool, check_soundness, question, sql),
        }
        return _assemble(spec, sql, attempts, progress)


if __name__ == "__main__":
    test_questions = [
        "How many orders came from São Paulo?",
        "What's the average order value?",
        "Which payment method is used most often?",
        "How has monthly order volume changed over time?",
        "What percentage of customers only ordered once?",
    ]

    for q in test_questions:
        print(f"Q: {q}")
        result = answer_question(q)
        print(result)
        print()
