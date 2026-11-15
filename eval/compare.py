"""Result-set comparison for execution accuracy.

A predicted result is CORRECT if, for every column in the gold result, some
predicted column holds the same values, and the rows line up. Extra predicted
columns are allowed (an answer that also shows a name next to a number is
still right), column names and order are ignored, row order is ignored.

Numbers: if the gold value is an integer it must match exactly (a count that
is off by one is wrong). If the gold value is a float, a small tolerance is
allowed so '3.1' and '3.12' both match 3.1187 but '0.031' does not.
"""
from __future__ import annotations


def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _values_equal(pred, gold) -> bool:
    if pred is None or gold is None:
        return pred is None and gold is None
    if _is_num(gold) and _is_num(pred):
        if isinstance(gold, int):
            return float(pred) == float(gold)
        return abs(pred - gold) <= max(0.051, 1e-3 * abs(gold))
    return str(pred).strip().lower() == str(gold).strip().lower()


def _sort_key(v):
    if v is None:
        return (0, "")
    if _is_num(v):
        return (1, round(float(v), 0))
    return (2, str(v).strip().lower())


def _column_matches(pred_col: list, gold_col: list) -> bool:
    if len(pred_col) != len(gold_col):
        return False
    a, b = sorted(pred_col, key=_sort_key), sorted(gold_col, key=_sort_key)
    return all(_values_equal(x, y) for x, y in zip(a, b))


def results_match(pred_columns, pred_rows, gold_columns, gold_rows) -> bool:
    if len(pred_rows) != len(gold_rows):
        return False
    if not gold_rows:
        return True

    pred_cols = [[r[i] for r in pred_rows] for i in range(len(pred_columns))]
    gold_cols = [[r[i] for r in gold_rows] for i in range(len(gold_columns))]

    # Map each gold column to a distinct predicted column holding the same values.
    mapping, used = [], set()
    for g in gold_cols:
        hit = next((i for i, p in enumerate(pred_cols) if i not in used and _column_matches(p, g)), None)
        if hit is None:
            return False
        mapping.append(hit)
        used.add(hit)

    # Rows must line up too: project, canonical-sort, compare cell by cell.
    projected = [tuple(r[i] for i in mapping) for r in pred_rows]
    key = lambda row: tuple(_sort_key(v) for v in row)  # noqa: E731
    projected.sort(key=key)
    gold_sorted = sorted(gold_rows, key=key)
    return all(_values_equal(p, g) for pr, gr in zip(projected, gold_sorted) for p, g in zip(pr, gr))
