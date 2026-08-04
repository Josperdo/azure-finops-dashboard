from datetime import date, datetime, time, timezone
from pathlib import Path

import typer
from azure.core.credentials import TokenCredential
from azure.mgmt.costmanagement.models import QueryTimePeriod
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

from azure_finops_dashboard import (
    __version__,
    audit,
    audit_queries,
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
audit_app = typer.Typer(help="FinOps audit findings.")
app.add_typer(audit_app, name="audit")
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


def _progress() -> Progress:
    """A per-call progress display: spinner + description + elapsed time.

    Not a determinate percentage bar - a single blocking API call has no real sub-progress
    to report, and faking one would be misleading. This is still a genuine upgrade over a
    bare spinner (visible elapsed time, consistent with Rich's fuller Progress styling).
    """
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    )


def _print_cost_summary(label: str, summary: cost.CostSummary, show_title: bool = True) -> None:
    headline = f"[bold]{summary.total_cost:,.2f} {summary.currency}[/bold]"
    console.print(Panel(headline, title=label if show_title else None, border_style="cyan"))

    service_table = Table(title="Top Services", header_style="bold cyan")
    service_table.add_column("Service")
    service_table.add_column("Cost", justify="right")
    for name, amount in summary.by_service:
        service_table.add_row(name, f"{amount:,.2f}")
    console.print(service_table)

    rg_table = Table(title="Top Resource Groups", header_style="bold cyan")
    rg_table.add_column("Resource Group")
    rg_table.add_column("Cost", justify="right")
    for name, amount in summary.by_resource_group:
        rg_table.add_row(name, f"{amount:,.2f}")
    console.print(rg_table)

    if summary.by_tag:
        tag_table = Table(title="Top by Tag", header_style="bold cyan")
        tag_table.add_column("Tag Value")
        tag_table.add_column("Cost", justify="right")
        for name, amount in summary.by_tag:
            tag_table.add_row(name, f"{amount:,.2f}")
        console.print(tag_table)


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

    table = Table(header_style="bold cyan")
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
    tag_key: str | None = typer.Option(
        None, "--tag-key", help="Also break down spend by the values of this tag key."
    ),
    start: str | None = typer.Option(
        None, "--start", help="Custom range start date (YYYY-MM-DD). Requires --end."
    ),
    end: str | None = typer.Option(
        None, "--end", help="Custom range end date (YYYY-MM-DD). Requires --start."
    ),
    rollup: bool = typer.Option(
        False, "--rollup", help="Also print a combined view across all queried subscriptions."
    ),
) -> None:
    """Show month-to-date (or last-month) spend by service and resource group."""
    if timeframe not in cost.TIMEFRAMES:
        console.print(f"[red]Error:[/red] --timeframe must be one of {', '.join(cost.TIMEFRAMES)}")
        raise typer.Exit(1)

    if bool(start) != bool(end):
        console.print("[red]Error:[/red] --start and --end must be given together.")
        raise typer.Exit(1)

    query_timeframe = cost.TIMEFRAMES[timeframe]
    time_period: QueryTimePeriod | None = None
    if start and end:
        try:
            start_date = date.fromisoformat(start)
            end_date = date.fromisoformat(end)
        except ValueError:
            console.print("[red]Error:[/red] --start/--end must be in YYYY-MM-DD format.")
            raise typer.Exit(1) from None
        time_period = QueryTimePeriod(
            from_property=datetime.combine(start_date, time.min, tzinfo=timezone.utc),
            to=datetime.combine(end_date, time.max, tzinfo=timezone.utc),
        )
        query_timeframe = "Custom"

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
            with _progress() as progress:
                progress.add_task(f"Fetching cost data for {label}...", total=None)
                summary = cost.get_cost_summary(
                    credential,
                    subscription_id,
                    timeframe=query_timeframe,
                    top_n=top,
                    tag_key=tag_key,
                    time_period=time_period,
                )
        except Exception as exc:  # noqa: BLE001 - translated into a friendly message below
            console.print(f"[red]Error ({label}):[/red] {friendly_error(exc)}")
            continue
        summaries.append(summary)
        _print_cost_summary(label, summary)

    if rollup and len(summaries) > 1:
        rollup_summary = cost.rollup_cost_summaries(summaries, top_n=top)
        _print_cost_summary("All Subscriptions", rollup_summary)
        summaries.append(rollup_summary)

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
            with _progress() as progress:
                progress.add_task(f"Fetching trend data for {label}...", total=None)
                summary = trend.get_trend(credential, subscription_id, months=months)
        except Exception as exc:  # noqa: BLE001 - translated into a friendly message below
            console.print(f"[red]Error ({label}):[/red] {friendly_error(exc)}")
            continue
        console.print(Panel(f"[bold]{label}[/bold]", border_style="cyan"))
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
            with _progress() as progress:
                progress.add_task(f"Fetching budgets for {label}...", total=None)
                statuses = budgets.list_budget_statuses(credential, subscription_id)
        except Exception as exc:  # noqa: BLE001 - translated into a friendly message below
            console.print(f"[red]Error ({label}):[/red] {friendly_error(exc)}")
            continue
        console.print(Panel(f"[bold]{label}[/bold]", border_style="cyan"))
        if not statuses:
            console.print("No budgets configured for this subscription.")
            continue
        console.print(budgets.render_budget_status(statuses))


@app.command("dashboard")
def dashboard(
    subscription: list[str] = typer.Option(
        [], "--subscription", help="Subscription ID to query (repeatable)."
    ),
    all_subscriptions: bool = typer.Option(
        False, "--all-subscriptions", help="Query every subscription visible to this identity."
    ),
    top: int = typer.Option(10, "--top", help="Number of services/resource groups to show."),
    months: int = typer.Option(6, "--months", help="Number of trailing months for the trend."),
) -> None:
    """Show spend summary, trend, and budget status together in one run."""
    try:
        credential, names_by_id, subscription_ids = _resolve_credential_and_subscriptions(
            subscription, all_subscriptions
        )
    except Exception as exc:  # noqa: BLE001 - translated into a friendly message below
        console.print(f"[red]Error:[/red] {friendly_error(exc)}")
        raise typer.Exit(1) from exc

    for subscription_id in subscription_ids:
        label = names_by_id.get(subscription_id, subscription_id)
        console.rule(f"[bold cyan]{label}[/bold cyan]")

        try:
            with _progress() as progress:
                progress.add_task(f"Fetching cost data for {label}...", total=None)
                summary = cost.get_cost_summary(credential, subscription_id, top_n=top)
            # The rule above already identifies the subscription for this whole block -
            # showing the same name a second time as the panel's own title looked
            # genuinely redundant once rendered with real Unicode borders (confirmed via
            # a real screenshot; our own ASCII-fallback testing masked how similar the
            # rule and the panel's title bar actually look).
            _print_cost_summary(label, summary, show_title=False)
        except Exception as exc:  # noqa: BLE001 - translated into a friendly message below
            console.print(f"[red]Error ({label}, cost summary):[/red] {friendly_error(exc)}")

        try:
            with _progress() as progress:
                progress.add_task(f"Fetching trend data for {label}...", total=None)
                trend_summary = trend.get_trend(credential, subscription_id, months=months)
            console.print(trend.render_trend(trend_summary))
        except Exception as exc:  # noqa: BLE001 - translated into a friendly message below
            console.print(f"[red]Error ({label}, trend):[/red] {friendly_error(exc)}")

        try:
            with _progress() as progress:
                progress.add_task(f"Fetching budgets for {label}...", total=None)
                statuses = budgets.list_budget_statuses(credential, subscription_id)
            if statuses:
                console.print(budgets.render_budget_status(statuses))
            else:
                console.print("No budgets configured for this subscription.")
        except Exception as exc:  # noqa: BLE001 - translated into a friendly message below
            console.print(f"[red]Error ({label}, budgets):[/red] {friendly_error(exc)}")


@audit_app.command("run")
def audit_run(
    subscription: list[str] = typer.Option(
        [], "--subscription", help="Subscription ID to query (repeatable)."
    ),
    all_subscriptions: bool = typer.Option(
        False, "--all-subscriptions", help="Query every subscription visible to this identity."
    ),
) -> None:
    """Scan for untagged resources, idle VMs, unattached disks, and orphaned public IPs."""
    try:
        credential, names_by_id, subscription_ids = _resolve_credential_and_subscriptions(
            subscription, all_subscriptions
        )
    except Exception as exc:  # noqa: BLE001 - translated into a friendly message below
        console.print(f"[red]Error:[/red] {friendly_error(exc)}")
        raise typer.Exit(1) from exc

    for subscription_id in subscription_ids:
        label = names_by_id.get(subscription_id, subscription_id)
        console.rule(f"[bold cyan]{label}[/bold cyan]")

        findings = []

        try:
            with _progress() as progress:
                progress.add_task(f"Scanning resources for {label}...", total=None)
                resources = audit_queries.fetch_resources(credential, subscription_id)
            findings += audit.find_untagged_resources(resources)
        except Exception as exc:  # noqa: BLE001 - translated into a friendly message below
            console.print(f"[red]Error ({label}, resources):[/red] {friendly_error(exc)}")

        try:
            with _progress() as progress:
                progress.add_task(f"Scanning VMs for {label}...", total=None)
                vms = audit_queries.fetch_vms(credential, subscription_id)
            findings += audit.find_idle_vms(vms)
        except Exception as exc:  # noqa: BLE001 - translated into a friendly message below
            console.print(f"[red]Error ({label}, VMs):[/red] {friendly_error(exc)}")

        try:
            with _progress() as progress:
                progress.add_task(f"Scanning disks for {label}...", total=None)
                disks = audit_queries.fetch_disks(credential, subscription_id)
            findings += audit.find_unattached_disks(disks)
        except Exception as exc:  # noqa: BLE001 - translated into a friendly message below
            console.print(f"[red]Error ({label}, disks):[/red] {friendly_error(exc)}")

        try:
            with _progress() as progress:
                progress.add_task(f"Scanning public IPs for {label}...", total=None)
                ips = audit_queries.fetch_public_ips(credential, subscription_id)
            findings += audit.find_orphaned_public_ips(ips)
        except Exception as exc:  # noqa: BLE001 - translated into a friendly message below
            console.print(f"[red]Error ({label}, public IPs):[/red] {friendly_error(exc)}")

        if findings:
            console.print(audit.render_audit_report(findings))
        else:
            console.print("No findings.")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
