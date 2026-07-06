from azure.core.exceptions import ClientAuthenticationError
from pytest_mock import MockerFixture
from typer.testing import CliRunner

from azure_finops_dashboard import __version__
from azure_finops_dashboard.cli import app
from azure_finops_dashboard.config import Config
from azure_finops_dashboard.cost import CostSummary
from azure_finops_dashboard.subscriptions import SubscriptionInfo

runner = CliRunner()


def test_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_help() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Azure cost visibility" in result.stdout


def test_subscriptions_list(mocker: MockerFixture) -> None:
    mocker.patch("azure_finops_dashboard.cli.auth.get_credential")
    mocker.patch(
        "azure_finops_dashboard.cli.subscriptions.list_subscriptions",
        return_value=[
            SubscriptionInfo(subscription_id="sub-1", display_name="Sub One", state="Enabled")
        ],
    )

    result = runner.invoke(app, ["subscriptions", "list"])

    assert result.exit_code == 0
    assert "sub-1" in result.stdout
    assert "Sub One" in result.stdout


def test_subscriptions_list_friendly_auth_error(mocker: MockerFixture) -> None:
    mocker.patch(
        "azure_finops_dashboard.cli.auth.get_credential",
        side_effect=ClientAuthenticationError("no token"),
    )

    result = runner.invoke(app, ["subscriptions", "list"])

    assert result.exit_code == 1
    assert "az login" in result.stdout
    assert "Traceback" not in result.stdout


def test_cost_summary(mocker: MockerFixture) -> None:
    mocker.patch("azure_finops_dashboard.cli.auth.get_credential")
    mocker.patch("azure_finops_dashboard.cli.config.load_config", return_value=Config())
    mocker.patch(
        "azure_finops_dashboard.cli.subscriptions.list_subscriptions",
        return_value=[
            SubscriptionInfo(subscription_id="sub-1", display_name="Sub One", state="Enabled")
        ],
    )
    mocker.patch(
        "azure_finops_dashboard.cli.cost.get_cost_summary",
        return_value=CostSummary(
            subscription_id="sub-1",
            currency="USD",
            total_cost=142.5,
            by_service=[("Compute", 100.0)],
            by_resource_group=[("rg-a", 100.0)],
        ),
    )

    result = runner.invoke(app, ["cost", "summary", "--all-subscriptions"])

    assert result.exit_code == 0
    assert "Sub One" in result.stdout
    assert "142.5" in result.stdout
    assert "Compute" in result.stdout
    assert "rg-a" in result.stdout


def test_cost_summary_no_subscription_specified(mocker: MockerFixture) -> None:
    mocker.patch("azure_finops_dashboard.cli.auth.get_credential")
    mocker.patch("azure_finops_dashboard.cli.config.load_config", return_value=Config())
    list_subscriptions = mocker.patch("azure_finops_dashboard.cli.subscriptions.list_subscriptions")

    result = runner.invoke(app, ["cost", "summary"])

    assert result.exit_code == 1
    assert "No subscription specified" in result.stdout
    list_subscriptions.assert_not_called()


def test_cost_summary_friendly_error_per_subscription(mocker: MockerFixture) -> None:
    mocker.patch("azure_finops_dashboard.cli.auth.get_credential")
    mocker.patch("azure_finops_dashboard.cli.config.load_config", return_value=Config())
    mocker.patch(
        "azure_finops_dashboard.cli.subscriptions.list_subscriptions",
        return_value=[
            SubscriptionInfo(subscription_id="sub-1", display_name="Sub One", state="Enabled")
        ],
    )
    mocker.patch(
        "azure_finops_dashboard.cli.cost.get_cost_summary",
        side_effect=ClientAuthenticationError("no token"),
    )

    result = runner.invoke(app, ["cost", "summary", "--all-subscriptions"])

    assert result.exit_code == 0
    assert "az login" in result.stdout
    assert "Traceback" not in result.stdout
