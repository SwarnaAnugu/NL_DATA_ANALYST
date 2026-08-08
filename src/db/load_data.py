import sqlite3
import pandas as pd
from pathlib import Path

DB_PATH = Path("data/nl_data_analyst.db")
DATA_DIR = Path("data")
SCHEMA_PATH = Path("src/db/schema.sql")

FILES_TO_TABLES = [
    ("olist_customers_dataset.csv", "customers"),
    ("olist_sellers_dataset.csv", "sellers"),
    ("product_category_name_translation.csv", "product_category_name_translation"),
    ("olist_products_dataset.csv", "products"),
    ("olist_orders_dataset.csv", "orders"),
    ("olist_order_items_dataset.csv", "order_items"),
    ("olist_order_payments_dataset.csv", "order_payments"),
    ("olist_order_reviews_dataset.csv", "order_reviews"),
    ("olist_geolocation_dataset.csv", "geolocation"),
]

def load_all():
    if DB_PATH.exists():
        DB_PATH.unlink()
        print(f"Deleted existing database at {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)

    schema_sql = SCHEMA_PATH.read_text()
    conn.executescript(schema_sql)
    print("Schema created from schema.sql")

    for csv_name, table_name in FILES_TO_TABLES:
        df = pd.read_csv(DATA_DIR / csv_name)
        df.to_sql(table_name, conn, if_exists="append", index=False)
        print(f"Loaded {len(df):>8} rows into {table_name}")

    conn.close()

if __name__ == "__main__":
    load_all()