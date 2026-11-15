"""Headline numbers about the dataset, shown at the top of the app."""
from db.execute_query import execute_query

_QUERIES = {
    "orders": "SELECT COUNT(*) FROM orders",
    "customers": "SELECT COUNT(DISTINCT customer_unique_id) FROM customers",
    "sellers": "SELECT COUNT(*) FROM sellers",
    "revenue": "SELECT SUM(price) FROM order_items",
    "first": "SELECT MIN(substr(order_purchase_timestamp, 1, 7)) FROM orders",
    "last": "SELECT MAX(substr(order_purchase_timestamp, 1, 7)) FROM orders",
}


def dataset_overview() -> dict:
    """Returns {name: value}; any failed query becomes None so the UI degrades quietly."""
    out = {}
    for name, sql in _QUERIES.items():
        r = execute_query(sql)
        out[name] = r["rows"][0][0] if r["status"] == "success" and r["rows"] else None
    return out
