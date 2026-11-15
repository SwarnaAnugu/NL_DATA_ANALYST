import re

MAX_SERIES = 12          # more groups than this make an unreadable legend
MAX_MEASURES = 5         # more numeric columns than this: show the table instead


def select_chart(columns: list, rows: list) -> dict:
    """
    Deterministic, heuristic chart choice. No LLM calls: the result's shape decides.

    Returns a dict, always one of:
      {"chart_type": "none", "reason": "..."}
      {"chart_type": "bar" | "line", "x": col, "y": col}                   one measure
      {"chart_type": "bar" | "line", "x": col, "y": [col, ...]}            several measures
      {"chart_type": "bar" | "line", "x": col, "y": col, "color": col}     one measure per group

    "line" is used when the x column looks like a date/month, else "bar".
    """
    if not rows or not columns:
        return {"chart_type": "none", "reason": "No rows."}
    if len(rows) == 1 and len(columns) == 1:
        return {"chart_type": "none", "reason": "Single value result — no chart needed."}
    if len(rows) == 1:
        return {"chart_type": "none", "reason": "A single row reads better as text than as a chart."}

    kinds = [_column_kind(rows, i) for i in range(len(columns))]
    numeric = [c for c, k in zip(columns, kinds) if k == "number"]
    labels = [c for c, k in zip(columns, kinds) if k in ("text", "date")]
    date_cols = [c for c, k in zip(columns, kinds) if k == "date"]

    # One label, one measure (the classic case).
    if len(labels) == 1 and len(numeric) == 1:
        x = labels[0]
        return {"chart_type": "line" if x in date_cols else "bar", "x": x, "y": numeric[0]}

    # One label, several measures (e.g. month, orders, revenue): compare on one axis.
    if len(labels) == 1 and 2 <= len(numeric) <= MAX_MEASURES:
        x = labels[0]
        return {"chart_type": "line" if x in date_cols else "bar", "x": x, "y": numeric}

    # Two labels, one measure (e.g. month x state -> revenue): one series per group.
    if len(labels) == 2 and len(numeric) == 1:
        x = date_cols[0] if date_cols else labels[0]
        color = labels[1] if labels[0] == x else labels[0]
        n_groups = len({r[columns.index(color)] for r in rows})
        if n_groups > MAX_SERIES:
            return {"chart_type": "none", "reason": f"{n_groups} groups is too many to chart; see the table."}
        return {"chart_type": "line" if x in date_cols else "bar", "x": x, "y": numeric[0], "color": color}

    return {"chart_type": "none", "reason": "This result shape is better read as a table."}


def _column_kind(rows: list, index: int) -> str:
    """'number', 'date' (text that looks like YYYY-MM[-DD]) or 'text', judged on the first non-null value."""
    for row in rows:
        value = row[index]
        if value is None:
            continue
        if isinstance(value, bool):
            return "text"
        if isinstance(value, (int, float)):
            return "number"
        return "date" if _looks_like_date(str(value)) else "text"
    return "text"


def _looks_like_date(value: str) -> bool:
    """Lightweight check for YYYY-MM or YYYY-MM-DD style strings."""
    return bool(re.match(r"^\d{4}-\d{2}(-\d{2})?", value))
