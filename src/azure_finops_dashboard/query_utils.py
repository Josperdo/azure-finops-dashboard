"""Shared helpers for parsing Cost Management Query API responses.

The API returns a columns/rows table shape (not named dicts), so both `cost.py` and
`trend.py` need the same lookup and coercion logic.
"""

from typing import Any


def parse_query_result(result: Any) -> tuple[list[str], list[list[object]]]:
    if result is None or result.columns is None or result.rows is None:
        raise ValueError("Cost Management API returned an empty response")
    columns = [str(c.name) for c in result.columns]
    return columns, list(result.rows)


def column_index(columns: list[str], name: str) -> int:
    for i, col in enumerate(columns):
        if col == name:
            return i
    raise ValueError(f"Cost Management response is missing expected column '{name}'")


def as_float(value: object) -> float:
    if isinstance(value, int | float | str):
        return float(value)
    raise TypeError(f"Expected a numeric cost value, got {type(value).__name__}")
