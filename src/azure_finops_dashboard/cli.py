from pathlib import Path

import typer
from azure.core.credentials import TokenCredential
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from azure_finops_dashboard import (
    __version__,
    auth,
    budgets,
    config,
    cost,
    export,
    subscriptions,
    trend,
)
from azure_finops_dashboard.errors import friendly_error

app = typer.Typer(
    name="azure-finops",
    help="Azure cost visibility and FinOps audit CLI.",
    add_completion=False,
)
subscriptions_app = typer.Typer(help="Inspect subscriptions visible to the current identity.")
app.add_typer(subscriptions_app, name="subscriptions")
cost_app = typer.Typer(help="Azure spend summaries.")
app.add_typer(cost_app, name="cost")
budget_app = typer.Typer(help="Azure budget status.")
app.add_typer(budget_app, name="budget")
console = Console()


def _resolve_credential_and_subscriptions(
    subscription: list[str], all_subscriptions: bool
) -> tuple[TokenCredential, dict[str, str], list[str]]:
    credential = auth.get_credential()
    # Only pay for subscription discovery when --all-subscriptions actually needs it.
    discovered = subscriptions.list_subscriptions(credential) if all_subscriptions else []
    names_by_id = {sub.subscription_id: sub.display_name for sub in discovered}
    subscription_ids = config.resolve_subscriptions(
        cli_ids=subscription,
        all_flag=all_subscriptions,
        config=config.load_config(),
        discovered=[sub.subscription_id for sub in discovered],
    )
    return credential, names_by_id, subscription_ids


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"azure-finops-dashboard {__version__}")
        raise typer.Exit()


@app.callback()
def callback(
    version: bool | None = typer.Option(
        None,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show the application version and exit.",
    ),
) -> None:
    """Azure cost visibility and FinOps audit CLI."""


@subscriptions_app.command("list")
def subscriptions_list() -> None:
    """List subscriptions visible to the current Azure identity."""
    try:
        credential = auth.get_credential()
        subs = subscriptions.list_subscriptions(credential)
    except Exception as exc:  # noqa: BLE001 - translated into a friendly message below
        console.print(f"[red]Error:[/red] {friendly_error(exc)}")
        raise typer.Exit(1) from exc

    table = Table()
    table.add_column("Subscription ID")
    table.add_column("Name")
    table.add_column("State")
    for sub in subs:
        table.add_row(sub.subscription_id, sub.display_name, sub.state)
    console.print(table)


@cost_app.command("summary")
def cost_summary(
    subscription: list[str] = typer.Option(
        [], "--subscription", help="Subscription ID to query (repeatable)."
    ),
    all_subscriptions: bool = typer.Option(
        False, "--all-subscriptions", help="Query every subscription visible to this identity."
    ),
    timeframe: str = typer.Option(
        "mtd", "--timeframe", help="Time period to summarize: 'mtd' or 'last-month'."
    ),
    top: int = typer.Option(10, "--top", help="Number of services/resource groups to show."),
    output: Path | None = typer.Option(
        None, "--output", help="Also write the summary to a file (.csv, .json, or .pdf)."
    ),
) -> None:
    """Show month-to-date (or last-month) spend by service and resource group."""
    if timeframe not in cost.TIMEFRAMES:
        console.print(f"[red]Error:[/red] --timeframe must be one of {', '.join(cost.TIMEFRAMES)}")
        raise typer.Exit(1)

    try:
        credential, names_by_id, subscription_ids = _resolve_credential_and_subscriptions(
            subscription, all_subscriptions
        )
    except Exception as exc:  # noqa: BLE001 - translated into a friendly message below
        console.print(f"[red]Error:[/red] {friendly_error(exc)}")
        raise typer.Exit(1) from exc

    summaries: list[cost.CostSummary] = []
    for subscription_id in subscription_ids:
        label = names_by_id.get(subscription_id, subscription_id)
        try:
            with console.status(f"Fetching cost data for {label}..."):
                summary = cost.get_cost_summary(
                    credential,
                    subscription_id,
                    timeframe=cost.TIMEFRAMES[timeframe],
                    top_n=top,
                )
        except Exception as exc:  # noqa: BLE001 - translated into a friendly message below
            console.print(f"[red]Error ({label}):[/red] {friendly_error(exc)}")
            continue
        summaries.append(summary)

        headline = f"[bold]{summary.total_cost:,.2f} {summary.currency}[/bold]"
        console.print(Panel(headline, title=label))

        service_table = Table(title="Top Services")
        service_table.add_column("Service")
        service_table.add_column("Cost", justify="right")
        for name, amount in summary.by_service:
            service_table.add_row(name, f"{amount:,.2f}")
        console.print(service_table)

        rg_table = Table(title="Top Resource Groups")
        rg_table.add_column("Resource Group")
        rg_table.add_column("Cost", justify="right")
        for name, amount in summary.by_resource_group:
            rg_table.add_row(name, f"{amount:,.2f}")
        console.print(rg_table)

    if output is not None and summaries:
        try:
            export.export_cost_summaries(summaries, output)
        except Exception as exc:  # noqa: BLE001 - translated into a friendly message below
            console.print(f"[red]Error:[/red] {friendly_error(exc)}")
            raise typer.Exit(1) from exc
        console.print(f"Wrote summary to [bold]{output}[/bold]")


@cost_app.command("trend")
def cost_trend(
    subscription: list[str] = typer.Option(
        [], "--subscription", help="Subscription ID to query (repeatable)."
    ),
    all_subscriptions: bool = typer.Option(
        False, "--all-subscriptions", help="Query every subscription visible to this identity."
    ),
    months: int = typer.Option(6, "--months", help="Number of trailing months to show."),
) -> None:
    """Show a monthly spend trend with month-over-month change."""
    try:
        credential, names_by_id, subscription_ids = _resolve_credential_and_subscriptions(
            subscription, all_subscriptions
        )
    except Exception as exc:  # noqa: BLE001 - translated into a friendly message below
        console.print(f"[red]Error:[/red] {friendly_error(exc)}")
        raise typer.Exit(1) from exc

    for subscription_id in subscription_ids:
        label = names_by_id.get(subscription_id, subscription_id)
        try:
            with console.status(f"Fetching trend data for {label}..."):
                summary = trend.get_trend(credential, subscription_id, months=months)
        except Exception as exc:  # noqa: BLE001 - translated into a friendly message below
            console.print(f"[red]Error ({label}):[/red] {friendly_error(exc)}")
            continue
        console.print(Panel(f"[bold]{label}[/bold]"))
        console.print(trend.render_trend(summary))


@budget_app.command("status")
def budget_status(
    subscription: list[str] = typer.Option(
        [], "--subscription", help="Subscription ID to query (repeatable)."
    ),
    all_subscriptions: bool = typer.Option(
        False, "--all-subscriptions", help="Query every subscription visible to this identity."
    ),
) -> None:
    """Show budget status and breach flags for each subscription."""
    try:
        credential, names_by_id, subscription_ids = _resolve_credential_and_subscriptions(
            subscription, all_subscriptions
        )
    except Exception as exc:  # noqa: BLE001 - translated into a friendly message below
        console.print(f"[red]Error:[/red] {friendly_error(exc)}")
        raise typer.Exit(1) from exc

    for subscription_id in subscription_ids:
        label = names_by_id.get(subscription_id, subscription_id)
        try:
            with console.status(f"Fetching budgets for {label}..."):
                statuses = budgets.list_budget_statuses(credential, subscription_id)
        except Exception as exc:  # noqa: BLE001 - translated into a friendly message below
            console.print(f"[red]Error ({label}):[/red] {friendly_error(exc)}")
            continue
        console.print(Panel(f"[bold]{label}[/bold]"))
        if not statuses:
            console.print("No budgets configured for this subscription.")
            continue
        console.print(budgets.render_budget_status(statuses))


def main() -> None:
    app()


if __name__ == "__main__":
    main()
