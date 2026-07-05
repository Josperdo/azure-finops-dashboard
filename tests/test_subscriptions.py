from types import SimpleNamespace
from unittest.mock import MagicMock

from pytest_mock import MockerFixture

from azure_finops_dashboard.subscriptions import SubscriptionInfo, list_subscriptions


def test_list_subscriptions_parses_client_response(mocker: MockerFixture) -> None:
    fake_subs = [
        SimpleNamespace(subscription_id="sub-1", display_name="Sub One", state="Enabled"),
        SimpleNamespace(subscription_id="sub-2", display_name="Sub Two", state="Disabled"),
    ]
    mock_client = MagicMock()
    mock_client.subscriptions.list.return_value = fake_subs
    mocker.patch(
        "azure_finops_dashboard.subscriptions.SubscriptionClient", return_value=mock_client
    )

    result = list_subscriptions(credential=MagicMock())

    assert result == [
        SubscriptionInfo(subscription_id="sub-1", display_name="Sub One", state="Enabled"),
        SubscriptionInfo(subscription_id="sub-2", display_name="Sub Two", state="Disabled"),
    ]
