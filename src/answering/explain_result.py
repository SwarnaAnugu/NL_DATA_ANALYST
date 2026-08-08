import os
from dotenv import load_dotenv
import anthropic

load_dotenv()
client = anthropic.Anthropic()

EXPLAIN_SYSTEM_PROMPT = """You are explaining a database query result to a non-technical user in plain English.

You will be given the user's original question and the raw result (column names and rows).

Write a short, direct answer — 1 to 3 sentences. Rules:
- State the actual number(s) or finding(s) clearly.
- Do not mention SQL, tables, columns, or the query itself.
- Do not add unrequested commentary, caveats, or filler like "Based on the data provided."
- If the result has many rows, summarize the pattern rather than listing every row.
- Format currency and large numbers in a readable way (e.g. "R$16,008,872.12" not raw floats with excess decimals).
"""


def explain_result(question: str, columns: list, rows: list) -> str:
    result_text = f"Columns: {columns}\nRows: {rows}"

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=300,
        system=EXPLAIN_SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": f"Question: {question}\n\nResult:\n{result_text}"
        }]
    )

    return response.content[0].text.strip()


if __name__ == "__main__":
    answer = explain_result(
        "What is the total revenue from all orders?",
        ["total_revenue"],
        [(16008872.12,)]
    )
    print(answer)