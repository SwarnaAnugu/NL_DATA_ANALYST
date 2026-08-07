from dotenv import load_dotenv
load_dotenv()

import json
import anthropic

client = anthropic.Anthropic()

AMBIGUITY_SYSTEM_PROMPT = """You are checking whether a natural-language question about a database \
can be turned into ONE unambiguous SQL query, or whether it has multiple genuinely different \
valid interpretations.

A question is ambiguous ONLY if there are genuinely multiple, structurally different \
valid interpretations that would produce different SQL queries and different answers. \
Do not flag a question as ambiguous just because it could be phrased more precisely — \
only flag it if answering it requires you to silently guess between real alternatives \
(e.g. "best" could mean highest revenue OR highest rating OR most units sold).

Respond with ONLY valid JSON, no other text, in this exact shape:
{"is_ambiguous": true or false, "clarifying_question": "string or null", "reasoning": "short internal note"}
"""
def check_ambiguity(question: str, schema_context: str) -> dict:
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=300,
        system=AMBIGUITY_SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": f"Schema:\n{schema_context}\n\nQuestion: {question}"
        }]
    )

    raw_text = response.content[0].text.strip()

    if raw_text.startswith("```"):
        raw_text = raw_text.split("\n", 1)[1]
        raw_text = raw_text.rsplit("\n", 1)[0]
        raw_text = raw_text.strip()

    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        return {
            "is_ambiguous": True,
            "clarifying_question": "I had trouble understanding that question — could you rephrase it?",
            "reasoning": "Failed to parse model response as JSON — defaulting to ambiguous to force clarification rather than risk a wrong query.",
            "raw_response": raw_text
        }
# if __name__ == "__main__":
#     sample_schema = "orders(order_id, customer_id, order_date), order_items(order_id, product_id, price)"
#
#     clear_question = "How many orders were placed in total?"
#     ambiguous_question = "What are the best products?"
#
#     print("Testing a CLEAR question:")
#     print(check_ambiguity(clear_question, sample_schema))
#
#     print("\nTesting an AMBIGUOUS question:")
#     print(check_ambiguity(ambiguous_question, sample_schema))


