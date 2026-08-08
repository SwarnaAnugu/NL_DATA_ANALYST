import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent.parent / "data" / "nl_data_analyst.db"

# Belt-and-suspenders check #1: reject obviously non-SELECT statements
# before we even touch the database.
def _looks_like_select(sql: str) -> bool:
    cleaned = sql.strip().lstrip("(").strip()
    return cleaned.upper().startswith("SELECT")


def execute_query(sql: str) -> dict:
    """
    Executes a validated SQL query against the database in read-only mode.

    Returns a dict, always one of:
      {"status": "success", "columns": [...], "rows": [...]}
      {"status": "rejected", "reason": "..."}   # failed the pre-check
      {"status": "error", "reason": "..."}      # DB itself raised an error
    """
    if not _looks_like_select(sql):
        return {
            "status": "rejected",
            "reason": "Only SELECT statements are permitted."
        }

    # Belt-and-suspenders check #2: the real enforcement layer.
    # Opening the connection in SQLite's read-only URI mode means the
    # database itself will refuse any write, no matter how the SQL is worded.
    try:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
        cur = conn.cursor()
        cur.execute(sql)
        rows = cur.fetchall()
        columns = [description[0] for description in cur.description]
        conn.close()
        return {"status": "success", "columns": columns, "rows": rows}

    except sqlite3.Error as e:
        return {"status": "error", "reason": str(e)}


if __name__ == "__main__":
    # Sanity test 1: a valid read query
    result = execute_query("SELECT COUNT(*) FROM orders")
    print("Valid query result:", result)

    # Sanity test 2: an attempted write, should be rejected before hitting the DB
    result = execute_query("DELETE FROM orders")
    print("Write attempt result:", result)

    # Sanity test 3: a write that dodges the naive string check by wrapping in parens
    # This should still be blocked — but by the DB connection, not the string check.
    result = execute_query("(DELETE FROM orders)".replace("(", "", 1))
    print("Malformed SQL result:", result)
    # Sanity test 4: bypass the string check entirely, prove the DB
    # connection itself refuses to write, no matter what.
    try:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
        cur = conn.cursor()
        cur.execute("DELETE FROM orders")
        conn.close()
        print("Direct write attempt: THIS SHOULD NOT PRINT")
    except sqlite3.Error as e:
        print("Direct write attempt correctly blocked by read-only connection:", e)
        # Sanity test 5: syntactically a SELECT, but semantically broken —
        # references a column that doesn't exist.
        result = execute_query("SELECT nonexistent_column FROM orders")
        print("Bad column result:", result)