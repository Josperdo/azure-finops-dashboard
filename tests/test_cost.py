from types import SimpleNamespace
from unittest.mock import MagicMock

from pytest_mock import MockerFixture

from azure_finops_dashboard.cost import get_cost_summary


def _fake_result(columns: list[str], rows: list[list]) -> SimpleNamespace:
    return SimpleNamespace(
        columns=[SimpleNamespace(name=name, type="String") for name in columns],
        rows=rows,
    )


def test_get_cost_summary_parses_total_and_breakdowns(mocker: MockerFixture) -> None:
    total_result = _fake_result(["Cost", "Currency"], [[123.456, "USD"]])
    service_result = _fake_result(
        ["ServiceName", "Cost", "Currency"],
        [["Storage", 20.0, "USD"], ["Compute", 80.0, "USD"], ["Networking", 23.456, "USD"]],
    )
    rg_result = _fake_result(
        ["ResourceGroupName", "Cost", "Currency"],
        [["rg-a", 100.0, "USD"], ["rg-b", 23.456, "USD"]],
    )

    mock_client = MagicMock()
    mock_client.query.usage.side_effect = [total_result, service_result, rg_result]
    mocker.patch("azure_finops_dashboard.cost.CostManagementClient", return_value=mock_client)

    summary = get_cost_summary(
        credential=MagicMock(), subscription_id="sub-1", timeframe="MonthToDate", top_n=2
    )

    assert summary.subscription_id == "sub-1"
    assert summary.currency == "USD"
    assert summary.total_cost == 123.456
    assert summary.by_service == [("Compute", 80.0), ("Networking", 23.456)]
    assert summary.by_resource_group == [("rg-a", 100.0), ("rg-b", 23.456)]
    assert mock_client.query.usage.call_count == 3


def test_get_cost_summary_handles_no_rows(mocker: MockerFixture) -> None:
    empty_total = _fake_result(["Cost", "Currency"], [])
    empty_service = _fake_result(["ServiceName", "Cost", "Currency"], [])
    empty_rg = _fake_result(["ResourceGroupName", "Cost", "Currency"], [])
    mock_client = MagicMock()
    mock_client.query.usage.side_effect = [empty_total, empty_service, empty_rg]
    mocker.patch("azure_finops_dashboard.cost.CostManagementClient", return_value=mock_client)

    summary = get_cost_summary(credential=MagicMock(), subscription_id="sub-1")

    assert summary.total_cost == 0.0
    assert summary.currency == ""
    assert summary.by_service == []
    assert summary.by_resource_group == []
