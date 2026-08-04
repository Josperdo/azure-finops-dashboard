from types import SimpleNamespace
from unittest.mock import MagicMock

from pytest_mock import MockerFixture

from azure_finops_dashboard.budgets import BudgetStatus, list_budget_statuses
from azure_finops_dashboard.client_config import CLIENT_KWARGS


def _fake_budget(name: str, amount: float, spend: float, currency: str = "USD") -> SimpleNamespace:
    return SimpleNamespace(
        name=name,
        amount=amount,
        time_grain="Monthly",
        current_spend=SimpleNamespace(amount=spend, unit=currency),
    )


def test_list_budget_statuses_classifies_correctly(mocker: MockerFixture) -> None:
    fake_budgets = [
        _fake_budget("under-budget", amount=100.0, spend=10.0),
        _fake_budget("near-limit", amount=100.0, spend=85.0),
        _fake_budget("over-limit", amount=100.0, spend=150.0),
    ]
    mock_client = MagicMock()
    mock_client.budgets.list.return_value = fake_budgets
    mocker.patch(
        "azure_finops_dashboard.budgets.ConsumptionManagementClient", return_value=mock_client
    )

    statuses = list_budget_statuses(credential=MagicMock(), subscription_id="sub-1")

    by_name = {s.name: s for s in statuses}
    assert by_name["under-budget"].status == "ok"
    assert by_name["near-limit"].status == "warning"
    assert by_name["over-limit"].status == "breached"
    # Sorted worst-first.
    assert [s.name for s in statuses] == ["over-limit", "near-limit", "under-budget"]


def test_list_budget_statuses_handles_zero_amount(mocker: MockerFixture) -> None:
    fake_budgets = [_fake_budget("zero-amount", amount=0.0, spend=0.0)]
    mock_client = MagicMock()
    mock_client.budgets.list.return_value = fake_budgets
    mocker.patch(
        "azure_finops_dashboard.budgets.ConsumptionManagementClient", return_value=mock_client
    )

    statuses = list_budget_statuses(credential=MagicMock(), subscription_id="sub-1")

    assert statuses == [
        BudgetStatus(
            name="zero-amount",
            amount=0.0,
            current_spend=0.0,
            currency="USD",
            time_grain="Monthly",
            percent_used=0.0,
            status="ok",
            subscription_id="sub-1",
        )
    ]


def test_list_budget_statuses_uses_tuned_client_kwargs(mocker: MockerFixture) -> None:
    mock_client_cls = mocker.patch("azure_finops_dashboard.budgets.ConsumptionManagementClient")
    mock_client_cls.return_value.budgets.list.return_value = []

    list_budget_statuses(credential=MagicMock(), subscription_id="sub-1")

    _, kwargs = mock_client_cls.call_args
    for key, value in CLIENT_KWARGS.items():
        assert kwargs[key] == value
