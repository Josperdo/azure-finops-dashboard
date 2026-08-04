from types import SimpleNamespace

import pytest

from azure_finops_dashboard.query_utils import as_float, column_index, parse_query_result


def test_parse_query_result_raises_on_none_result() -> None:
    with pytest.raises(ValueError, match="empty response"):
        parse_query_result(None)


def test_parse_query_result_raises_on_missing_columns() -> None:
    with pytest.raises(ValueError, match="empty response"):
        parse_query_result(SimpleNamespace(columns=None, rows=[]))


def test_parse_query_result_raises_on_missing_rows() -> None:
    with pytest.raises(ValueError, match="empty response"):
        parse_query_result(SimpleNamespace(columns=[], rows=None))


def test_column_index_raises_on_missing_column() -> None:
    with pytest.raises(ValueError, match="missing expected column 'Cost'"):
        column_index(["ServiceName"], "Cost")


def test_as_float_raises_on_non_numeric_value() -> None:
    with pytest.raises(TypeError, match="Expected a numeric cost value"):
        as_float(None)
