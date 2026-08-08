def select_chart(columns: list, rows: list) -> dict:
    """
    Deterministic, heuristic-based chart type selection.
    No LLM calls — pure logic based on the shape of the result set.

    Returns a dict, always one of:
      {"chart_type": "none", "reason": "..."}
      {"chart_type": "bar", "x": column_name, "y": column_name}
      {"chart_type": "line", "x": column_name, "y": column_name}
    """
    num_rows = len(rows)
    num_cols = len(columns)

    # Rule 1: a single value (e.g. total revenue, a count) needs no chart.
    if num_rows == 1 and num_cols == 1:
        return {"chart_type": "none", "reason": "Single value result — no chart needed."}

    # Only handle the clean 2-column case for now. Anything else is
    # ambiguous enough that we'd rather show a table than guess wrong.
    if num_cols != 2:
        return {"chart_type": "none", "reason": "Chart selection only supports 2-column results currently."}

    col_a, col_b = columns[0], columns[1]
    sample_row = rows[0]
    val_a, val_b = sample_row[0], sample_row[1]

    # Figure out which of the two columns is numeric and which is the
    # "label" column (text, or something that looks like a date string).
    a_is_numeric = isinstance(val_a, (int, float))
    b_is_numeric = isinstance(val_b, (int, float))

    if a_is_numeric and not b_is_numeric:
        numeric_col, label_col = col_a, col_b
        label_val = val_b
    elif b_is_numeric and not a_is_numeric:
        numeric_col, label_col = col_b, col_a
        label_val = val_a
    else:
        # Both numeric, or both non-numeric — too ambiguous to auto-pick axes.
        return {"chart_type": "none", "reason": "Could not confidently identify a numeric column and a label column."}

    # Rule 2: does the label column look like a date/time?
    if _looks_like_date(str(label_val)):
        return {"chart_type": "line", "x": label_col, "y": numeric_col}

    # Rule 3: otherwise, treat it as a category -> bar chart.
    return {"chart_type": "bar", "x": label_col, "y": numeric_col}


def _looks_like_date(value: str) -> bool:
    """Very lightweight date-shape check: looks for YYYY-MM or YYYY-MM-DD
    style strings without needing to actually parse them."""
    import re
    return bool(re.match(r"^\d{4}-\d{2}(-\d{2})?", value))


if __name__ == "__main__":
    # Test 1: single value, no chart
    print(select_chart(["total_revenue"], [(16008872.12,)]))

    # Test 2: category + number, should pick bar
    print(select_chart(
        ["product_category", "total_sales"],
        [("electronics", 5000), ("furniture", 3200)]
    ))

    # Test 3: date + number, should pick line
    print(select_chart(
        ["order_month", "total_sales"],
        [("2018-01", 12000), ("2018-02", 15000)]
    ))

    # Test 4: two numeric columns, ambiguous, should decline
    print(select_chart(
        ["order_count", "total_sales"],
        [(120, 5000), (95, 3200)]
    ))