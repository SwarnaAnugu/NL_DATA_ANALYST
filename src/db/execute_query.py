import sqlite3
import time

from config import DB_PATH, MAX_ROWS, QUERY_TIMEOUT_S
from safety.sql_validator import validate_sql


def execute_query(sql: str) -> dict:
    """
    Executes a SQL query against the database with three layers of protection:
      1. Static validation (single SELECT/WITH statement, no forbidden keywords)
      2. A read-only SQLite connection (the database itself refuses writes)
      3. A wall-clock timeout and a row cap, so one bad query can't hang the app

    Returns a dict, always one of:
      {"status": "success", "columns": [...], "rows": [...], "truncated": bool}
      {"status": "rejected", "reason": "..."}   # failed static validation
      {"status": "error", "reason": "..."}      # the database raised an error
    """
    ok, reason = validate_sql(sql)
    if not ok:
        return {"status": "rejected", "reason": reason}

    conn = None
    try:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
        conn.execute("PRAGMA query_only = ON")

        # Hard limits enforced by SQLite itself, as a backstop to the static
        # validator: no string/blob over 10 MB, no SQL text over 20k chars,
        # no extension loading.
        conn.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 10_000_000)
        conn.setlimit(sqlite3.SQLITE_LIMIT_SQL_LENGTH, 20_000)
        conn.enable_load_extension(False) if hasattr(conn, "enable_load_extension") else None

        # SQLite calls this handler every N VM instructions; returning a
        # truthy value aborts the query.
        deadline = time.monotonic() + QUERY_TIMEOUT_S
        conn.set_progress_handler(lambda: time.monotonic() > deadline, 100_000)

        cur = conn.cursor()
        cur.execute(sql)
        columns = [d[0] for d in cur.description]
        rows = cur.fetchmany(MAX_ROWS + 1)
        truncated = len(rows) > MAX_ROWS
        return {
            "status": "success",
            "columns": columns,
            "rows": rows[:MAX_ROWS],
            "truncated": truncated,
        }
    except sqlite3.OperationalError as e:
        if "interrupted" in str(e).lower():
            return {"status": "error", "reason": f"Query exceeded the {QUERY_TIMEOUT_S}s time limit."}
        return {"status": "error", "reason": str(e)}
    except sqlite3.Error as e:
        return {"status": "error", "reason": str(e)}
    finally:
        if conn is not None:
            conn.close()


if __name__ == "__main__":
    print("valid   :", execute_query("SELECT COUNT(*) FROM orders"))
    print("write   :", execute_query("DELETE FROM orders"))
    print("multi   :", execute_query("SELECT 1; DROP TABLE orders"))
    print("pragma  :", execute_query("PRAGMA table_info(orders)"))
    print("bad col :", execute_query("SELECT nonexistent_column FROM orders"))
