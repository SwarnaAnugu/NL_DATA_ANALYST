import os
from pathlib import Path
import sqlite3
from dotenv import load_dotenv

load_dotenv()

# Resolve relative to the repo root, not the current working directory,
# so this works no matter which folder you run the script from.
REPO_ROOT = Path(__file__).resolve().parents[2]  # src/sql_generation -> src -> repo root
DB_PATH = REPO_ROOT / os.environ["DATABASE_PATH"]
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
def build_schema_context():
    """Build a single text block describing every table and column, for prompting Claude."""
    conn = sqlite3.connect(DB_PATH)
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
        return "\n\n".join(lines)
    finally:
        conn.close()
if __name__ == "__main__":
    print(build_schema_context())
