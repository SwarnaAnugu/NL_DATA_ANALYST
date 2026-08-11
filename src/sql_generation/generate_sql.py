import json
import os
from dotenv import load_dotenv
import anthropic

load_dotenv()

client = anthropic.Anthropic()

SQL_GENERATION_SYSTEM_PROMPT = """You are a SQL expert writing SQLite queries against a real e-commerce database.

Rules:
- Only generate SELECT statements. Never write INSERT, UPDATE, DELETE, DROP, or ALTER.
- Use only the tables and columns given in the schema. Never invent column or table names.
- Prefer explicit JOINs with clear ON conditions over implicit joins.
- Return ONLY the raw SQL query. No explanation, no markdown code fences, no commentary.
"""

SQL_CRITIQUE_SYSTEM_PROMPT = """You are reviewing a SQL query for correctness before it runs against a real database.

Check for these specific problems:
- Does the query actually answer the question asked, or does it answer something subtly different?
- Are JOINs correct? Could any JOIN cause duplicate rows to be double-counted in a SUM, COUNT, or AVG?
- Are column names used correctly according to the schema?
- Are there any non-SELECT statements (there should never be any)?

Do your reasoning silently. Do not write out your analysis, explanation, or thought process as
text. Your entire response must be ONLY the JSON object below and nothing else — no prose before
it, no prose after it, no markdown code fences.

{"is_valid": true or false, "issue": "string or null", "corrected_sql": "string or null"}

If is_valid is true, issue and corrected_sql should both be null.
If is_valid is false, describe the issue concisely and provide a corrected_sql that fixes it.
"""


def generate_sql(question: str, schema_context: str) -> str:
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=500,
        system=SQL_GENERATION_SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": f"Schema:\n{schema_context}\n\nQuestion: {question}\n\nWrite the SQL query."
        }]
    )

    raw_text = response.content[0].text.strip()

    if raw_text.startswith("```"):
        raw_text = raw_text.split("\n", 1)[1]
        raw_text = raw_text.rsplit("\n", 1)[0]
        raw_text = raw_text.strip()

    return raw_text


def critique_sql(question: str, schema_context: str, sql: str) -> dict:
    critique_schema = {
        "type": "object",
        "properties": {
            "is_valid": {"type": "boolean"},
            "issue": {"type": ["string", "null"]},
            "corrected_sql": {"type": ["string", "null"]}
        },
        "required": ["is_valid", "issue", "corrected_sql"],
        "additionalProperties": False
    }

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2500,  # thinking tokens + JSON output both count against this
        thinking={"type": "enabled", "budget_tokens": 1200},
        system=SQL_CRITIQUE_SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": f"Schema:\n{schema_context}\n\nQuestion: {question}\n\nSQL to review:\n{sql}"
        }],
        output_config={
            "format": {
                "type": "json_schema",
                "schema": critique_schema
            }
        }
    )

    # response.content now has a "thinking" block AND a "text" block —
    # pull out the text block specifically, don't assume content[0].
    text_block = next(b for b in response.content if b.type == "text")
    raw_text = text_block.text

    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        return {
            "is_valid": False,
            "issue": "Failed to parse critique response as JSON — treating as invalid to be safe.",
            "corrected_sql": None,
            "raw_response": raw_text
        }



if __name__ == "__main__":
    from schema_context import build_schema_context

    schema = build_schema_context()
    question = "What's our customer churn rate?"

    sql = generate_sql(question, schema)
    print("GENERATED SQL:")
    print(sql)
    print()

    critique = critique_sql(question, schema, sql)
    print("CRITIQUE RESULT:")
    print(critique)