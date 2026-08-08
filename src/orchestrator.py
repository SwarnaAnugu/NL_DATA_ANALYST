from sql_generation.ambiguity_check import check_ambiguity
from sql_generation.generate_sql import generate_sql, critique_sql
from sql_generation.schema_context import build_schema_context


def answer_question(user_question: str) -> dict:
    """
    Orchestrates the full English -> validated SQL pipeline:
    ambiguity check -> generate -> critique -> (at most 1 retry) -> result.

    Returns a dict describing the outcome. Always one of these shapes:
      {"status": "clarify", "question": "..."}
      {"status": "success", "sql": "...", "attempts": 1 or 2}
      {"status": "failed", "reason": "..."}
    """
    schema = build_schema_context()

    # Step 1: ambiguity check. Fail-safe default already lives inside
    # check_ambiguity() itself (unparseable -> ambiguous).
    ambiguity_result = check_ambiguity(user_question)
    if ambiguity_result.get("is_ambiguous"):
        return {
            "status": "clarify",
            "question": ambiguity_result.get("clarifying_question")
        }

    # Step 2: first generation attempt.
    sql = generate_sql(user_question, schema)

    # Step 3: critique attempt #1.
    critique = critique_sql(user_question, schema, sql)

    if critique.get("is_valid"):
        return {"status": "success", "sql": sql, "attempts": 1}

    # Step 4: not valid. Branch on whether the critique handed us a fix.
    corrected_sql = critique.get("corrected_sql")

    if corrected_sql:
        # Use the critique's own fix as the single retry attempt.
        retry_critique = critique_sql(user_question, schema, corrected_sql)
        if retry_critique.get("is_valid"):
            return {"status": "success", "sql": corrected_sql, "attempts": 2}
        return {
            "status": "failed",
            "reason": f"Corrected SQL also failed critique: {retry_critique.get('issue')}"
        }

    else:
        # No fix offered — fall back to a fresh generation attempt,
        # feeding the critique's issue back in as extra context.
        issue_note = critique.get("issue", "The previous query was invalid.")
        retry_question = (
            f"{user_question}\n\n"
            f"Note: a previous attempt at this query had the following problem, "
            f"avoid repeating it: {issue_note}"
        )
        retry_sql = generate_sql(retry_question, schema)
        retry_critique = critique_sql(user_question, schema, retry_sql)

        if retry_critique.get("is_valid"):
            return {"status": "success", "sql": retry_sql, "attempts": 2}
        return {
            "status": "failed",
            "reason": f"Retry generation also failed critique: {retry_critique.get('issue')}"
        }


if __name__ == "__main__":
    result = answer_question("What is the total revenue from all orders?")
    print(result)