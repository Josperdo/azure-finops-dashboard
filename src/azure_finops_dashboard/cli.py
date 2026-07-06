import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from azure_finops_dashboard import __version__, auth, config, cost, subscriptions
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
console = Console()


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
) -> None:
    """Show month-to-date (or last-month) spend by service and resource group."""
    if timeframe not in cost.TIMEFRAMES:
        console.print(f"[red]Error:[/red] --timeframe must be one of {', '.join(cost.TIMEFRAMES)}")
        raise typer.Exit(1)

    try:
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
    except Exception as exc:  # noqa: BLE001 - translated into a friendly message below
        console.print(f"[red]Error:[/red] {friendly_error(exc)}")
        raise typer.Exit(1) from exc

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


def main() -> None:
    app()


if __name__ == "__main__":
    main()
