import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

from pytest_mock import MockerFixture

from azure_finops_dashboard.retry_config import RETRY_KWARGS
from azure_finops_dashboard.trend import get_trend


def _fake_result(rows: list[list[object]]) -> SimpleNamespace:
    return SimpleNamespace(
        columns=[SimpleNamespace(name=name) for name in ["Cost", "BillingMonth", "Currency"]],
        rows=rows,
    )


def _freeze_today(mocker: MockerFixture, frozen: datetime.date) -> None:
    mock_date = mocker.patch("azure_finops_dashboard.trend.date", wraps=datetime.date)
    mock_date.today.return_value = frozen


def test_get_trend_parses_and_sorts_out_of_order_rows(mocker: MockerFixture) -> None:
    # Deliberately out of chronological order to confirm sorting; matches the real API's
    # BillingMonth-as-ISO-datetime-string shape, not an int.
    result = _fake_result(
        [
            [200.0, "2024-03-01T00:00:00", "USD"],
            [100.0, "2024-01-01T00:00:00", "USD"],
        ]
    )
    mock_client = MagicMock()
    mock_client.query.usage.return_value = result
    mocker.patch("azure_finops_dashboard.trend.CostManagementClient", return_value=mock_client)
    _freeze_today(mocker, datetime.date(2024, 3, 15))

    summary = get_trend(credential=MagicMock(), subscription_id="sub-1", months=3)

    assert [m.month for m in summary.months] == ["2024-01", "2024-02", "2024-03"]
    assert [m.cost for m in summary.months] == [100.0, 0.0, 200.0]
    assert summary.currency == "USD"


def test_get_trend_fills_zero_cost_months_omitted_by_api(mocker: MockerFixture) -> None:
    # The real Cost Management API omits months with zero cost entirely rather than
    # returning a zero-cost row - confirm those gaps get filled in, not dropped.
    result = _fake_result([[100.0, "2024-01-01T00:00:00", "USD"]])
    mock_client = MagicMock()
    mock_client.query.usage.return_value = result
    mocker.patch("azure_finops_dashboard.trend.CostManagementClient", return_value=mock_client)
    _freeze_today(mocker, datetime.date(2024, 3, 15))

    summary = get_trend(credential=MagicMock(), subscription_id="sub-1", months=3)

    assert [m.month for m in summary.months] == ["2024-01", "2024-02", "2024-03"]
    assert [m.cost for m in summary.months] == [100.0, 0.0, 0.0]


def test_get_trend_delta_handles_zero_prior_month(mocker: MockerFixture) -> None:
    result = _fake_result(
        [
            [100.0, "2024-01-01T00:00:00", "USD"],
            [50.0, "2024-03-01T00:00:00", "USD"],
        ]
    )
    mock_client = MagicMock()
    mock_client.query.usage.return_value = result
    mocker.patch("azure_finops_dashboard.trend.CostManagementClient", return_value=mock_client)
    _freeze_today(mocker, datetime.date(2024, 3, 15))

    summary = get_trend(credential=MagicMock(), subscription_id="sub-1", months=3)

    assert summary.deltas[0] is None  # first month has no prior month
    assert summary.deltas[1] == -100.0  # 100 -> 0
    assert summary.deltas[2] is None  # prior month (0) would divide by zero


def test_get_trend_uses_tuned_retry_kwargs(mocker: MockerFixture) -> None:
    mock_client_cls = mocker.patch("azure_finops_dashboard.trend.CostManagementClient")
    mock_client_cls.return_value.query.usage.return_value = _fake_result([])
    _freeze_today(mocker, datetime.date(2024, 3, 15))

    get_trend(credential=MagicMock(), subscription_id="sub-1", months=3)

    _, kwargs = mock_client_cls.call_args
    for key, value in RETRY_KWARGS.items():
        assert kwargs[key] == value
