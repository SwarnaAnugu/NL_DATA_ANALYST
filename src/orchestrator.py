from sql_generation.ambiguity_check import check_ambiguity
from sql_generation.generate_sql import generate_sql, critique_sql
from sql_generation.schema_context import build_schema_context
from db.execute_query import execute_query
from charting.chart_selector import select_chart
from answering.explain_result import explain_result


def answer_question(user_question: str) -> dict:
    """
    Orchestrates the full pipeline:
    ambiguity check -> generate -> critique -> (at most 1 retry) -> execute -> explain.

    Returns a dict, always one of:
      {"status": "clarify", "question": "..."}
      {"status": "success", "sql": "...", "attempts": 1 or 2, "columns": [...], "rows": [...], "explanation": "...", "chart": {...}}
      {"status": "failed", "reason": "..."}
    """
    schema = build_schema_context()

    ambiguity_result = check_ambiguity(user_question, schema)
    if ambiguity_result.get("is_ambiguous"):
        return {
            "status": "clarify",
            "question": ambiguity_result.get("clarifying_question")
        }

    sql = generate_sql(user_question, schema)
    critique = critique_sql(user_question, schema, sql)

    if critique.get("is_valid"):
        return _run(user_question, sql, attempts=1)

    corrected_sql = critique.get("corrected_sql")

    if corrected_sql:
        retry_critique = critique_sql(user_question, schema, corrected_sql)
        if retry_critique.get("is_valid"):
            return _run(user_question, corrected_sql, attempts=2)
        return {
            "status": "failed",
            "reason": f"Corrected SQL also failed critique: {retry_critique.get('issue')}"
        }

    else:
        issue_note = critique.get("issue", "The previous query was invalid.")
        retry_question = (
            f"{user_question}\n\n"
            f"Note: a previous attempt at this query had the following problem, "
            f"avoid repeating it: {issue_note}"
        )
        retry_sql = generate_sql(retry_question, schema)
        retry_critique = critique_sql(user_question, schema, retry_sql)

        if retry_critique.get("is_valid"):
            return _run(user_question, retry_sql, attempts=2)
        return {
            "status": "failed",
            "reason": f"Retry generation also failed critique: {retry_critique.get('issue')}"
        }


def _run(question: str, sql: str, attempts: int) -> dict:
    """Executes SQL that has already passed critique, then adds a plain-
    English explanation and a chart selection on top of the raw result."""
    exec_result = execute_query(sql)

    if exec_result["status"] != "success":
        return {
            "status": "failed",
            "reason": f"SQL passed critique but failed at execution: {exec_result['reason']}"
        }

    columns = exec_result["columns"]
    rows = exec_result["rows"]

    explanation = explain_result(question, columns, rows)
    chart = select_chart(columns, rows)

    return {
        "status": "success",
        "sql": sql,
        "attempts": attempts,
        "columns": columns,
        "rows": rows,
        "explanation": explanation,
        "chart": chart
    }


if __name__ == "__main__":
    result = answer_question("What is the total revenue from all orders?")
    print(result)

    print()

    result2 = answer_question("What is the total revenue by customer state?")
    print(result2)