import pytest
from safety.sql_validator import validate_sql
from db.execute_query import execute_query

GOOD = [
    "SELECT COUNT(*) FROM orders",
    "select * from orders;",
    "WITH t AS (SELECT 1 AS x) SELECT x FROM t",
    "SELECT replace(customer_city, 'a', 'b') FROM customers",
    "SELECT review_creation_date FROM order_reviews",          # contains CREATE as a substring only
    "SELECT 'please DROP TABLE orders' AS note",               # keyword only inside a string literal
    "SELECT 1 -- DELETE FROM orders",                          # keyword only inside a comment
    "(SELECT 1)",
]
BAD = [
    "DELETE FROM orders",
    "UPDATE orders SET order_status='x'",
    "DROP TABLE orders",
    "SELECT 1; DROP TABLE orders",
    "SELECT 1; SELECT 2",
    "PRAGMA table_info(orders)",
    "ATTACH DATABASE 'x.db' AS x",
    "INSERT INTO orders VALUES (1)",
    "WITH t AS (SELECT 1) DELETE FROM orders",
    "",
    "   ",
    "EXPLAIN SELECT 1",
    "SELECT * FROM pragma_table_info('orders')",
    "SELECT * FROM pragma_database_list",
    "SELECT hex(randomblob(1000000000))",
    "SELECT length(zeroblob(2000000000))",
    "SELECT load_extension('x')",
]


@pytest.mark.parametrize("sql", GOOD)
def test_validator_accepts(sql):
    assert validate_sql(sql)[0], sql


@pytest.mark.parametrize("sql", BAD)
def test_validator_rejects(sql):
    ok, reason = validate_sql(sql)
    assert not ok and reason, sql


def test_execute_ok():
    r = execute_query("SELECT COUNT(*) FROM orders")
    assert r["status"] == "success" and r["rows"] == [(99441,)] and r["truncated"] is False


def test_execute_rejects_write_before_db():
    assert execute_query("DELETE FROM orders")["status"] == "rejected"


def test_execute_bad_column_is_error():
    assert execute_query("SELECT nope FROM orders")["status"] == "error"


def test_row_cap_and_truncation_flag():
    r = execute_query("SELECT order_id FROM orders")
    assert r["status"] == "success" and len(r["rows"]) == 1000 and r["truncated"] is True


def test_timeout(monkeypatch):
    import db.execute_query as eq
    monkeypatch.setattr(eq, "QUERY_TIMEOUT_S", 0.3)
    # Cartesian product of two big tables: would run for minutes.
    r = eq.execute_query("SELECT COUNT(*) FROM order_items a, order_items b, order_items c")
    assert r["status"] == "error" and "time limit" in r["reason"]


def test_db_connection_itself_is_read_only():
    import sqlite3
    from config import DB_PATH
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("DELETE FROM orders")
    conn.close()


def test_sqlite_size_limit_backstop_stops_string_doubling_bomb():
    # Passes the static validator (plain recursive CTE), but would build a multi-GB string.
    # The connection-level LENGTH limit must kill it quickly, not exhaust memory.
    bomb = ("SELECT length(s) FROM (WITH RECURSIVE t(s,n) AS (SELECT 'xxxxxxxxxx',0 UNION ALL "
            "SELECT s||s, n+1 FROM t WHERE n<30) SELECT s FROM t ORDER BY n DESC LIMIT 1)")
    assert validate_sql(bomb)[0]
    r = execute_query(bomb)
    assert r["status"] == "error" and "too big" in r["reason"]
