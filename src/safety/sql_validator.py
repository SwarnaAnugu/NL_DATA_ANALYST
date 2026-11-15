"""Static SQL validation: the first of two read-only defences.

The second (the real one) is the read-only SQLite connection in
db/execute_query.py. This layer exists to give clear error messages and to
reject things a read-only connection would still allow but we don't want,
such as ATTACH, PRAGMA, or several statements stuffed into one string.
"""
import re

FORBIDDEN_KEYWORDS = {
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE",
    "ATTACH", "DETACH", "PRAGMA", "VACUUM", "REINDEX", "TRUNCATE",
    "BEGIN", "COMMIT", "ROLLBACK", "SAVEPOINT", "RELEASE",
}

# Functions that are read-only but dangerous in a public demo: they can leak
# server details (pragma_* table functions expose file paths and settings) or
# allocate huge amounts of memory in one call.
FORBIDDEN_FUNCTIONS = {"RANDOMBLOB", "ZEROBLOB", "LOAD_EXTENSION", "READFILE", "WRITEFILE", "EDIT"}
FORBIDDEN_PREFIXES = ("PRAGMA_",)

_STRING_RE = re.compile(r"'(?:[^']|'')*'|\"(?:[^\"]|\"\")*\"")
_LINE_COMMENT_RE = re.compile(r"--[^\n]*")
_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)


def _strip_literals_and_comments(sql: str) -> str:
    sql = _BLOCK_COMMENT_RE.sub(" ", sql)
    sql = _LINE_COMMENT_RE.sub(" ", sql)
    # Strip string literals so a keyword inside 'DROP' text doesn't trigger.
    return _STRING_RE.sub("''", sql)


def validate_sql(sql: str) -> tuple[bool, str | None]:
    """Return (True, None) if the SQL is a single read-only statement,
    else (False, reason)."""
    if not sql or not sql.strip():
        return False, "Empty query."

    cleaned = _strip_literals_and_comments(sql).strip()

    # Allow one trailing semicolon, nothing after it.
    body = cleaned.rstrip(";").strip()
    if ";" in body:
        return False, "Only a single statement is allowed."

    first = re.match(r"\(*\s*([A-Za-z]+)", body)
    if not first or first.group(1).upper() not in {"SELECT", "WITH"}:
        return False, "Only SELECT queries are permitted."

    words = set(re.findall(r"[A-Za-z_]+", body.upper()))
    bad = sorted(words & FORBIDDEN_KEYWORDS)
    if bad:
        return False, f"Query contains a forbidden keyword: {bad[0]}."

    bad_fn = sorted((words & FORBIDDEN_FUNCTIONS) | {w for w in words if w.startswith(FORBIDDEN_PREFIXES)})
    if bad_fn:
        return False, f"Query uses a function that is not permitted: {bad_fn[0].lower()}."

    return True, None
