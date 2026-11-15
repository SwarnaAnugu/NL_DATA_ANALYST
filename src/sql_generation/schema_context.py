import sqlite3

from config import DB_PATH

# Facts about the Olist dataset that a model cannot learn from column names
# alone. Every line here was verified against the real database (see
# eval/verify_gold.py and the project notes). This is the cheapest accuracy
# win in the whole pipeline: it removes the guesses the model would otherwise
# have to make.
DATASET_NOTES = """\
Dataset notes (verified facts about this data):
- Orders span 2016-09 to 2018-10. 2016 and Sep/Oct 2018 are very sparse; the full months are 2017-01 to 2018-08.
- All timestamps are TEXT 'YYYY-MM-DD HH:MM:SS'. Use strftime('%Y-%m', col) for months and julianday(a) - julianday(b) for durations in days.
- orders.order_status is one of: delivered, shipped, canceled, unavailable, invoiced, processing, created, approved.
- Delivery columns (order_delivered_customer_date etc.) are NULL for orders that were never delivered. For delivery-time questions filter order_status = 'delivered' AND order_delivered_customer_date IS NOT NULL.
- customer_id is generated per ORDER; customer_unique_id identifies the real person. Count people with COUNT(DISTINCT customer_unique_id), never customer_id.
- Revenue means SUM(order_items.price) (item price, excluding freight). order_items.freight_value is shipping. order_payments.payment_value is what customers paid (item price + freight) and can have several rows per order.
- Never JOIN order_items and order_payments in the same aggregate: each order has several rows in both, so SUMs get multiplied. Aggregate one side in a subquery first.
- An order can have several order_items rows (one per item) and, rarely, more than one review.
- product_category_name is Portuguese. For English names JOIN product_category_name_translation ON product_category_name and use product_category_name_english. Some products have a NULL category.
- There is no 'region' column. If asked about regions, map customer_state to the five Brazilian regions with a CASE expression: North (AC,AP,AM,PA,RO,RR,TO), Northeast (AL,BA,CE,MA,PB,PE,PI,RN,SE), Central-West (DF,GO,MT,MS), Southeast (ES,MG,RJ,SP), South (PR,RS,SC).
- customers.customer_city is lowercase with accents stripped (e.g. 'sao paulo', 'brasilia'). sellers.seller_city is messy free text (mixed case, accents, state suffixes), so avoid exact city matches on sellers.
- payment_type is one of: credit_card, boleto, voucher, debit_card, not_defined.
- geolocation has one row per zip code prefix (mean coordinates); join on customer_zip_code_prefix or seller_zip_code_prefix.
- review_score is a 1-5 integer given by the customer.
- Column names product_name_lenght and product_description_lenght are misspelled in the data; use them exactly as written.
"""


def get_table_names(conn):
    """Return all real table names, skipping SQLite's internal ones."""
    cur = conn.cursor()
    cur.execute("""
        SELECT name FROM sqlite_master
        WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
    """)
    return [row[0] for row in cur.fetchall()]


def get_table_schema(conn, table_name):
    """Return column info for one table: name, type, is it a primary key."""
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table_name})")
    columns = cur.fetchall()
    return [
        {"name": col[1], "type": col[2], "is_primary_key": bool(col[5])}
        for col in columns
    ]


def build_schema_context(include_notes: bool = True):
    """Build a single text block describing every table and column (plus
    verified dataset notes), for prompting Claude."""
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    try:
        table_names = get_table_names(conn)
        lines = []
        for table in table_names:
            columns = get_table_schema(conn, table)
            column_descriptions = []
            for col in columns:
                desc = f"{col['name']} ({col['type']})"
                if col["is_primary_key"]:
                    desc += " [PRIMARY KEY]"
                column_descriptions.append(desc)
            lines.append(f"Table: {table}\n  " + "\n  ".join(column_descriptions))
        text = "\n\n".join(lines)
        return f"{text}\n\n{DATASET_NOTES}" if include_notes else text
    finally:
        conn.close()


if __name__ == "__main__":
    print(build_schema_context())
