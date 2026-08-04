from pathlib import Path

from azure.core.exceptions import ClientAuthenticationError
from pytest_mock import MockerFixture
from typer.testing import CliRunner

from azure_finops_dashboard import __version__
from azure_finops_dashboard.audit import ResourceInfo, VmInfo
from azure_finops_dashboard.budgets import BudgetStatus
from azure_finops_dashboard.cli import app
from azure_finops_dashboard.config import Config
from azure_finops_dashboard.cost import CostSummary
from azure_finops_dashboard.subscriptions import SubscriptionInfo
from azure_finops_dashboard.trend import TrendMonth, TrendSummary

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


def test_cost_summary_with_output(mocker: MockerFixture, tmp_path: Path) -> None:
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
    output_path = tmp_path / "summary.csv"

    result = runner.invoke(
        app, ["cost", "summary", "--all-subscriptions", "--output", str(output_path)]
    )

    assert result.exit_code == 0
    assert output_path.exists()
    assert "Wrote summary" in result.stdout


def test_cost_summary_with_tag_key(mocker: MockerFixture) -> None:
    mocker.patch("azure_finops_dashboard.cli.auth.get_credential")
    mocker.patch("azure_finops_dashboard.cli.config.load_config", return_value=Config())
    mocker.patch(
        "azure_finops_dashboard.cli.subscriptions.list_subscriptions",
        return_value=[
            SubscriptionInfo(subscription_id="sub-1", display_name="Sub One", state="Enabled")
        ],
    )
    get_summary = mocker.patch(
        "azure_finops_dashboard.cli.cost.get_cost_summary",
        return_value=CostSummary(
            subscription_id="sub-1",
            currency="USD",
            total_cost=142.5,
            by_service=[("Compute", 100.0)],
            by_resource_group=[("rg-a", 100.0)],
            by_tag=[("prod", 100.0)],
        ),
    )

    result = runner.invoke(
        app, ["cost", "summary", "--all-subscriptions", "--tag-key", "Environment"]
    )

    assert result.exit_code == 0
    assert "prod" in result.stdout
    assert get_summary.call_args.kwargs["tag_key"] == "Environment"


def test_cost_summary_start_end_must_be_paired() -> None:
    result = runner.invoke(app, ["cost", "summary", "--start", "2024-01-01"])

    assert result.exit_code == 1
    assert "--start and --end must be given together" in result.stdout


def test_cost_summary_malformed_date() -> None:
    result = runner.invoke(
        app, ["cost", "summary", "--start", "not-a-date", "--end", "2024-01-31"]
    )

    assert result.exit_code == 1
    assert "YYYY-MM-DD" in result.stdout


def test_cost_summary_custom_date_range_uses_custom_timeframe(mocker: MockerFixture) -> None:
    mocker.patch("azure_finops_dashboard.cli.auth.get_credential")
    mocker.patch("azure_finops_dashboard.cli.config.load_config", return_value=Config())
    mocker.patch(
        "azure_finops_dashboard.cli.subscriptions.list_subscriptions",
        return_value=[
            SubscriptionInfo(subscription_id="sub-1", display_name="Sub One", state="Enabled")
        ],
    )
    get_summary = mocker.patch(
        "azure_finops_dashboard.cli.cost.get_cost_summary",
        return_value=CostSummary(subscription_id="sub-1", currency="USD", total_cost=1.0),
    )

    result = runner.invoke(
        app,
        [
            "cost",
            "summary",
            "--all-subscriptions",
            "--start",
            "2024-01-01",
            "--end",
            "2024-01-31",
        ],
    )

    assert result.exit_code == 0
    assert get_summary.call_args.kwargs["timeframe"] == "Custom"
    assert get_summary.call_args.kwargs["time_period"] is not None


def test_cost_summary_rollup_combines_multiple_subscriptions(mocker: MockerFixture) -> None:
    mocker.patch("azure_finops_dashboard.cli.auth.get_credential")
    mocker.patch("azure_finops_dashboard.cli.config.load_config", return_value=Config())
    mocker.patch(
        "azure_finops_dashboard.cli.subscriptions.list_subscriptions",
        return_value=[
            SubscriptionInfo(subscription_id="sub-1", display_name="Sub One", state="Enabled"),
            SubscriptionInfo(subscription_id="sub-2", display_name="Sub Two", state="Enabled"),
        ],
    )
    mocker.patch(
        "azure_finops_dashboard.cli.cost.get_cost_summary",
        side_effect=[
            CostSummary(
                subscription_id="sub-1",
                currency="USD",
                total_cost=100.0,
                by_service=[("Compute", 100.0)],
            ),
            CostSummary(
                subscription_id="sub-2",
                currency="USD",
                total_cost=50.0,
                by_service=[("Compute", 50.0)],
            ),
        ],
    )

    result = runner.invoke(app, ["cost", "summary", "--all-subscriptions", "--rollup"])

    assert result.exit_code == 0
    assert "All Subscriptions" in result.stdout
    assert "150.00" in result.stdout


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


def test_cost_trend(mocker: MockerFixture) -> None:
    mocker.patch("azure_finops_dashboard.cli.auth.get_credential")
    mocker.patch("azure_finops_dashboard.cli.config.load_config", return_value=Config())
    mocker.patch(
        "azure_finops_dashboard.cli.subscriptions.list_subscriptions",
        return_value=[
            SubscriptionInfo(subscription_id="sub-1", display_name="Sub One", state="Enabled")
        ],
    )
    mocker.patch(
        "azure_finops_dashboard.cli.trend.get_trend",
        return_value=TrendSummary(
            subscription_id="sub-1",
            currency="USD",
            months=[
                TrendMonth(month="2024-01", cost=100.0),
                TrendMonth(month="2024-02", cost=150.0),
            ],
            deltas=[None, 50.0],
        ),
    )

    result = runner.invoke(app, ["cost", "trend", "--all-subscriptions"])

    assert result.exit_code == 0
    assert "Sub One" in result.stdout
    assert "2024-01" in result.stdout
    assert "2024-02" in result.stdout


def test_budget_status(mocker: MockerFixture) -> None:
    mocker.patch("azure_finops_dashboard.cli.auth.get_credential")
    mocker.patch("azure_finops_dashboard.cli.config.load_config", return_value=Config())
    mocker.patch(
        "azure_finops_dashboard.cli.subscriptions.list_subscriptions",
        return_value=[
            SubscriptionInfo(subscription_id="sub-1", display_name="Sub One", state="Enabled")
        ],
    )
    mocker.patch(
        "azure_finops_dashboard.cli.budgets.list_budget_statuses",
        return_value=[
            BudgetStatus(
                name="monthly-budget",
                amount=100.0,
                current_spend=150.0,
                currency="USD",
                time_grain="Monthly",
                percent_used=150.0,
                status="breached",
            )
        ],
    )

    result = runner.invoke(app, ["budget", "status", "--all-subscriptions"])

    assert result.exit_code == 0
    assert "Sub One" in result.stdout
    assert "monthly-budget" in result.stdout
    assert "breached" in result.stdout


def test_budget_status_no_budgets_configured(mocker: MockerFixture) -> None:
    mocker.patch("azure_finops_dashboard.cli.auth.get_credential")
    mocker.patch("azure_finops_dashboard.cli.config.load_config", return_value=Config())
    mocker.patch(
        "azure_finops_dashboard.cli.subscriptions.list_subscriptions",
        return_value=[
            SubscriptionInfo(subscription_id="sub-1", display_name="Sub One", state="Enabled")
        ],
    )
    mocker.patch("azure_finops_dashboard.cli.budgets.list_budget_statuses", return_value=[])

    result = runner.invoke(app, ["budget", "status", "--all-subscriptions"])

    assert result.exit_code == 0
    assert "No budgets configured" in result.stdout


def test_dashboard_combines_all_three_sections(mocker: MockerFixture) -> None:
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
        ),
    )
    mocker.patch(
        "azure_finops_dashboard.cli.trend.get_trend",
        return_value=TrendSummary(
            subscription_id="sub-1",
            currency="USD",
            months=[TrendMonth(month="2024-01", cost=100.0)],
            deltas=[None],
        ),
    )
    mocker.patch(
        "azure_finops_dashboard.cli.budgets.list_budget_statuses",
        return_value=[
            BudgetStatus(
                name="monthly-budget",
                amount=200.0,
                current_spend=142.5,
                currency="USD",
                time_grain="Monthly",
                percent_used=71.25,
                status="ok",
            )
        ],
    )

    result = runner.invoke(app, ["dashboard", "--all-subscriptions"])

    assert result.exit_code == 0
    assert "Compute" in result.stdout  # cost summary section
    assert "2024-01" in result.stdout  # trend section
    assert "monthly-budget" in result.stdout  # budget section
    # Regression: the subscription name should appear once (the section-divider rule),
    # not a second time as the cost panel's own redundant title right below it.
    assert result.stdout.count("Sub One") == 1


def test_dashboard_isolates_section_failures(mocker: MockerFixture) -> None:
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
        ),
    )
    mocker.patch(
        "azure_finops_dashboard.cli.trend.get_trend",
        side_effect=ClientAuthenticationError("no token"),
    )
    mocker.patch(
        "azure_finops_dashboard.cli.budgets.list_budget_statuses",
        return_value=[],
    )

    result = runner.invoke(app, ["dashboard", "--all-subscriptions"])

    assert result.exit_code == 0
    assert "Compute" in result.stdout  # cost summary still printed
    assert "az login" in result.stdout  # trend's friendly error
    assert "No budgets configured" in result.stdout  # budgets still printed
    assert "Traceback" not in result.stdout


def test_audit_run_combines_findings_from_all_detectors(mocker: MockerFixture) -> None:
    mocker.patch("azure_finops_dashboard.cli.auth.get_credential")
    mocker.patch("azure_finops_dashboard.cli.config.load_config", return_value=Config())
    mocker.patch(
        "azure_finops_dashboard.cli.subscriptions.list_subscriptions",
        return_value=[
            SubscriptionInfo(subscription_id="sub-1", display_name="Sub One", state="Enabled")
        ],
    )
    mocker.patch(
        "azure_finops_dashboard.cli.audit_queries.fetch_resources",
        return_value=[
            ResourceInfo("id-1", "res-1", "rg-a", "storage_account", tags={}),
        ],
    )
    mocker.patch(
        "azure_finops_dashboard.cli.audit_queries.fetch_vms",
        return_value=[VmInfo("id-2", "vm-1", "rg-a", "PowerState/stopped")],
    )
    mocker.patch("azure_finops_dashboard.cli.audit_queries.fetch_disks", return_value=[])
    mocker.patch("azure_finops_dashboard.cli.audit_queries.fetch_public_ips", return_value=[])

    result = runner.invoke(app, ["audit", "run", "--all-subscriptions"])

    assert result.exit_code == 0
    assert "Sub One" in result.stdout
    assert "res-1" in result.stdout  # untagged resource finding
    assert "vm-1" in result.stdout  # idle VM finding
    assert "high" in result.stdout  # idle VM finding's severity


def test_audit_run_no_findings(mocker: MockerFixture) -> None:
    mocker.patch("azure_finops_dashboard.cli.auth.get_credential")
    mocker.patch("azure_finops_dashboard.cli.config.load_config", return_value=Config())
    mocker.patch(
        "azure_finops_dashboard.cli.subscriptions.list_subscriptions",
        return_value=[
            SubscriptionInfo(subscription_id="sub-1", display_name="Sub One", state="Enabled")
        ],
    )
    mocker.patch("azure_finops_dashboard.cli.audit_queries.fetch_resources", return_value=[])
    mocker.patch("azure_finops_dashboard.cli.audit_queries.fetch_vms", return_value=[])
    mocker.patch("azure_finops_dashboard.cli.audit_queries.fetch_disks", return_value=[])
    mocker.patch("azure_finops_dashboard.cli.audit_queries.fetch_public_ips", return_value=[])

    result = runner.invoke(app, ["audit", "run", "--all-subscriptions"])

    assert result.exit_code == 0
    assert "No findings" in result.stdout


def test_audit_run_isolates_category_failures(mocker: MockerFixture) -> None:
    mocker.patch("azure_finops_dashboard.cli.auth.get_credential")
    mocker.patch("azure_finops_dashboard.cli.config.load_config", return_value=Config())
    mocker.patch(
        "azure_finops_dashboard.cli.subscriptions.list_subscriptions",
        return_value=[
            SubscriptionInfo(subscription_id="sub-1", display_name="Sub One", state="Enabled")
        ],
    )
    mocker.patch(
        "azure_finops_dashboard.cli.audit_queries.fetch_resources",
        side_effect=ClientAuthenticationError("no token"),
    )
    mocker.patch(
        "azure_finops_dashboard.cli.audit_queries.fetch_vms",
        return_value=[VmInfo("id-2", "vm-1", "rg-a", "PowerState/stopped")],
    )
    mocker.patch("azure_finops_dashboard.cli.audit_queries.fetch_disks", return_value=[])
    mocker.patch("azure_finops_dashboard.cli.audit_queries.fetch_public_ips", return_value=[])

    result = runner.invoke(app, ["audit", "run", "--all-subscriptions"])

    assert result.exit_code == 0
    assert "az login" in result.stdout  # resources' friendly error
    assert "vm-1" in result.stdout  # VMs still contributed a finding
    assert "Traceback" not in result.stdout
