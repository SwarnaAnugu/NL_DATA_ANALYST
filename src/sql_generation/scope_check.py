import json
import os
from dotenv import load_dotenv
import anthropic

load_dotenv()
client = anthropic.Anthropic()

SCOPE_CHECK_SYSTEM_PROMPT = """You are a gatekeeper for a tool that answers questions about a specific
Brazilian e-commerce dataset (orders, customers, products, sellers, payments, reviews).

Decide if the user's question could plausibly be answered by querying this dataset — even
loosely (e.g. "what is this dataset about" IS in scope, since it relates to the data).

Only mark something out of scope if it is clearly unrelated to e-commerce data — general
knowledge questions, small talk, requests about unrelated topics, or anything that has
nothing to do with orders, customers, products, sellers, payments, or reviews.

Respond ONLY with JSON in this exact format, nothing else:
{
  "is_in_scope": true or false,
  "reason": "brief explanation"
}
"""


def check_scope(question: str) -> dict:
    response = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=200,
        system=SCOPE_CHECK_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": question}]
    )

    raw_text = response.content[0].text.strip()

    if raw_text.startswith("```"):
        raw_text = raw_text.split("\n", 1)[1]
        raw_text = raw_text.rsplit("\n", 1)[0]
        raw_text = raw_text.strip()

    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        # Fail-safe default: if we can't parse the response, let it through
        # rather than blocking a possibly-legitimate question. The rest of
        # the pipeline will still fail gracefully if it truly can't be answered.
        return {
            "is_in_scope": True,
            "reason": "Failed to parse scope check response — defaulting to in-scope."
        }


if __name__ == "__main__":
    print(check_scope("What is the total revenue by state?"))
    print(check_scope("What's the weather like today?"))
    print(check_scope("What is this dataset about?"))