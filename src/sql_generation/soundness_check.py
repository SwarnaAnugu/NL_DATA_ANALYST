import json
from config import get_client, FAST_MODEL

SOUNDNESS_CHECK_SYSTEM_PROMPT = """You are checking whether a question, if answered from this specific dataset, would produce a number that looks authoritative but is actually misleading due to known structural limitations of the data.

This is a Brazilian e-commerce dataset (Olist) covering a FIXED date range: September 2016 to October 2018. There is no data before or after this window. Known landmines:

- Any "churn", "retention", "repeat purchase rate", "customer lifetime value", or similar time-dependent customer behavior metric is affected by right-censoring: a customer who ordered once near the end of the window hasn't necessarily "churned" - they simply haven't had time to reorder before the data ends. A naive one-time-vs-repeat calculation over the whole window will systematically overstate churn for no real behavioral reason.
- customer_id is generated per ORDER, not per customer. A single real customer has a different customer_id for every order they place. customer_unique_id is the actual stable customer identifier. Any question about repeat customers, customer counts, or customer-level behavior that uses customer_id instead of customer_unique_id will silently produce wrong (inflated) customer counts.
- Delivery/fulfillment dates are NULL for orders that were never delivered - questions about delivery time implicitly filter to delivered orders only.
- review_score is a subjective self-reported 1-5 rating, not a ground-truth product quality signal.

Your job: given a question and the SQL that would answer it, decide if the answer would be understood as MORE reliable or complete than it actually is, given the above limitations. Assume the SQL is technically correct - you are not reviewing JOIN logic here. You are judging whether presenting the resulting number WITHOUT context would mislead someone.

If yes, write ONE short, plain-English caveat sentence (under 40 words) to show alongside the answer. State the specific limitation as it applies to this specific question - do not write a generic disclaimer.

If the question is not affected by any of these patterns, needs_caveat should be false and caveat_text should be null.

{"needs_caveat": true or false, "reason": "short internal note on which landmine applies, or null", "caveat_text": "the user-facing sentence, or null"}
"""


def check_soundness(question: str, sql: str) -> dict:
    caveat_schema = {
        "type": "object",
        "properties": {
            "needs_caveat": {"type": "boolean"},
            "reason": {"type": ["string", "null"]},
            "caveat_text": {"type": ["string", "null"]}
        },
        "required": ["needs_caveat", "reason", "caveat_text"],
        "additionalProperties": False
    }

    response = get_client().messages.create(
        model=FAST_MODEL,
        max_tokens=500,
        system=SOUNDNESS_CHECK_SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": f"Question: {question}\n\nSQL:\n{sql}"
        }],
        output_config={
            "format": {
                "type": "json_schema",
                "schema": caveat_schema
            }
        }
    )

    raw_text = response.content[0].text

    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        return {
            "needs_caveat": True,
            "reason": "Failed to parse soundness check response - defaulting to caveat to be safe.",
            "caveat_text": "This answer may be affected by known limitations of the dataset (fixed date range, per-order customer IDs) - treat it as directional rather than precise."
        }


if __name__ == "__main__":
    from schema_context import build_schema_context

    question = "What's our customer churn rate?"
    sql = """
    SELECT COUNT(DISTINCT CASE WHEN order_count = 1 THEN customer_unique_id END) * 100.0
           / COUNT(DISTINCT customer_unique_id) AS churn_rate_percentage
    FROM (
        SELECT customer_unique_id, COUNT(DISTINCT order_id) AS order_count
        FROM customers c JOIN orders o ON c.customer_id = o.customer_id
        GROUP BY customer_unique_id
    ) t
    """

    result = check_soundness(question, sql)
    print(result)