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

if __name__ == "__main__":
    from schema_context import build_schema_context

    schema = build_schema_context()
    question = "How many orders were placed by customers in Sao Paulo state?"

    sql = generate_sql(question, schema)
    print(sql)