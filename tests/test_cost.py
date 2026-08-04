from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from azure.mgmt.costmanagement.models import QueryTimePeriod
from pytest_mock import MockerFixture

from azure_finops_dashboard.client_config import CLIENT_KWARGS
from azure_finops_dashboard.cost import CostSummary, get_cost_summary, rollup_cost_summaries


@pytest.fixture(autouse=True)
def _no_real_sleep(mocker: MockerFixture) -> None:
    # get_cost_summary paces its sequential calls with a real time.sleep() to avoid
    # bursting Cost Management's throttling - don't actually wait for it in tests.
    mocker.patch("azure_finops_dashboard.cost.time.sleep")


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


def test_get_cost_summary_with_tag_key_runs_extra_query(mocker: MockerFixture) -> None:
    # Real API shape confirmed live: TagKey groupings return fixed generic column names
    # (TagKey/TagValue), not a column named after the requested tag key.
    total_result = _fake_result(["Cost", "Currency"], [[10.0, "USD"]])
    service_result = _fake_result(["ServiceName", "Cost", "Currency"], [])
    rg_result = _fake_result(["ResourceGroupName", "Cost", "Currency"], [])
    tag_result = _fake_result(
        ["TagKey", "TagValue", "Cost", "Currency"],
        [
            ["environment", "prod", 7.0, "USD"],
            ["environment", "dev", 3.0, "USD"],
        ],
    )
    mock_client = MagicMock()
    mock_client.query.usage.side_effect = [total_result, service_result, rg_result, tag_result]
    mocker.patch("azure_finops_dashboard.cost.CostManagementClient", return_value=mock_client)

    summary = get_cost_summary(
        credential=MagicMock(), subscription_id="sub-1", tag_key="Environment"
    )

    assert summary.by_tag == [("prod", 7.0), ("dev", 3.0)]
    assert mock_client.query.usage.call_count == 4


def test_get_cost_summary_tag_key_handles_null_tag_value(mocker: MockerFixture) -> None:
    # Confirmed live: a tag key can appear with a null TagValue and zero cost (e.g. tag
    # applied to a resource but not yet attributed to any cost record).
    total_result = _fake_result(["Cost", "Currency"], [[10.0, "USD"]])
    service_result = _fake_result(["ServiceName", "Cost", "Currency"], [])
    rg_result = _fake_result(["ResourceGroupName", "Cost", "Currency"], [])
    tag_result = _fake_result(
        ["TagKey", "TagValue", "Cost", "Currency"],
        [["environment", None, 0.0, "USD"]],
    )
    mock_client = MagicMock()
    mock_client.query.usage.side_effect = [total_result, service_result, rg_result, tag_result]
    mocker.patch("azure_finops_dashboard.cost.CostManagementClient", return_value=mock_client)

    summary = get_cost_summary(
        credential=MagicMock(), subscription_id="sub-1", tag_key="Environment"
    )

    assert summary.by_tag == [("(none)", 0.0)]


def test_get_cost_summary_without_tag_key_skips_extra_query(mocker: MockerFixture) -> None:
    total_result = _fake_result(["Cost", "Currency"], [[10.0, "USD"]])
    service_result = _fake_result(["ServiceName", "Cost", "Currency"], [])
    rg_result = _fake_result(["ResourceGroupName", "Cost", "Currency"], [])
    mock_client = MagicMock()
    mock_client.query.usage.side_effect = [total_result, service_result, rg_result]
    mocker.patch("azure_finops_dashboard.cost.CostManagementClient", return_value=mock_client)

    summary = get_cost_summary(credential=MagicMock(), subscription_id="sub-1")

    assert summary.by_tag == []
    assert mock_client.query.usage.call_count == 3


def test_get_cost_summary_passes_time_period_through(mocker: MockerFixture) -> None:
    total_result = _fake_result(["Cost", "Currency"], [[10.0, "USD"]])
    empty_service = _fake_result(["ServiceName", "Cost", "Currency"], [])
    empty_rg = _fake_result(["ResourceGroupName", "Cost", "Currency"], [])
    mock_client = MagicMock()
    mock_client.query.usage.side_effect = [total_result, empty_service, empty_rg]
    mocker.patch("azure_finops_dashboard.cost.CostManagementClient", return_value=mock_client)
    time_period = QueryTimePeriod(from_property="2024-01-01", to="2024-01-31")

    get_cost_summary(
        credential=MagicMock(),
        subscription_id="sub-1",
        timeframe="Custom",
        time_period=time_period,
    )

    for call in mock_client.query.usage.call_args_list:
        assert call.kwargs["parameters"].time_period is time_period
        assert call.kwargs["parameters"].timeframe == "Custom"


def test_get_cost_summary_uses_tuned_client_kwargs(mocker: MockerFixture) -> None:
    mock_client_cls = mocker.patch("azure_finops_dashboard.cost.CostManagementClient")
    mock_client_cls.return_value.query.usage.return_value = _fake_result(
        ["ServiceName", "ResourceGroupName", "Cost", "Currency"], []
    )

    get_cost_summary(credential=MagicMock(), subscription_id="sub-1")

    _, kwargs = mock_client_cls.call_args
    for key, value in CLIENT_KWARGS.items():
        assert kwargs[key] == value


def test_rollup_cost_summaries_merges_by_name() -> None:
    summaries = [
        CostSummary(
            subscription_id="sub-1",
            currency="USD",
            total_cost=100.0,
            by_service=[("Compute", 80.0), ("Storage", 20.0)],
            by_resource_group=[("rg-a", 100.0)],
        ),
        CostSummary(
            subscription_id="sub-2",
            currency="USD",
            total_cost=50.0,
            by_service=[("Compute", 40.0), ("Networking", 10.0)],
            by_resource_group=[("rg-b", 50.0)],
        ),
    ]

    rollup = rollup_cost_summaries(summaries, top_n=2)

    assert rollup.subscription_id == "(all)"
    assert rollup.total_cost == 150.0
    assert rollup.by_service == [("Compute", 120.0), ("Storage", 20.0)]
    assert rollup.by_resource_group == [("rg-a", 100.0), ("rg-b", 50.0)]


def test_rollup_cost_summaries_empty_list() -> None:
    rollup = rollup_cost_summaries([])
    assert rollup.total_cost == 0.0
    assert rollup.currency == ""
