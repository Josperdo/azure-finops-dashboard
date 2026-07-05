from azure.core.exceptions import ClientAuthenticationError
from pytest_mock import MockerFixture
from typer.testing import CliRunner

from azure_finops_dashboard import __version__
from azure_finops_dashboard.cli import app
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
