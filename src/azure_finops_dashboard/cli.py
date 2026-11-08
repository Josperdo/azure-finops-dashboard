import dataclasses
from collections.abc import Callable
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Any

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


def _export_all(
    data: Any, output: list[Path], export_fn: Callable[[Any, Path], None], label: str
) -> None:
    """Write `data` to every path in `output`, format inferred per-path from its extension.

    Multiple --output flags with different extensions is what gives "export to CSV, JSON,
    and PDF in one run" - one mechanism serving two roadmap items at once.
    """
    for path in output:
        try:
            export_fn(data, path)
        except Exception as exc:  # noqa: BLE001 - translated into a friendly message below
            console.print(f"[red]Error:[/red] {friendly_error(exc)}")
            raise typer.Exit(1) from exc
        console.print(f"Wrote {label} to [bold]{path}[/bold]")


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

    for tag_key, pairs in summary.by_tag.items():
        tag_table = Table(title=f"Top by Tag: {tag_key}", header_style="bold cyan")
        tag_table.add_column("Tag Value")
        tag_table.add_column("Cost", justify="right")
        for name, amount in pairs:
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
    output: list[Path] = typer.Option(
        [], "--output", help="Also write the summary to a file (.csv, .json, or .pdf; repeatable)."
    ),
    tag_key: list[str] = typer.Option(
        [], "--tag-key", help="Also break down spend by the values of this tag key (repeatable)."
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
            from_property=datetime.combine(start_date, time.min, tzinfo=UTC),
            to=datetime.combine(end_date, time.max, tzinfo=UTC),
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
                    tag_keys=tag_key or None,
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

    if output and summaries:
        _export_all(summaries, output, export.export_cost_summaries, "summary")


@cost_app.command("trend")
def cost_trend(
    subscription: list[str] = typer.Option(
        [], "--subscription", help="Subscription ID to query (repeatable)."
    ),
    all_subscriptions: bool = typer.Option(
        False, "--all-subscriptions", help="Query every subscription visible to this identity."
    ),
    months: int = typer.Option(6, "--months", help="Number of trailing months to show."),
    output: list[Path] = typer.Option(
        [], "--output", help="Also write the trend to a file (.csv, .json, or .pdf; repeatable)."
    ),
) -> None:
    """Show a monthly spend trend with month-over-month change."""
    try:
        credential, names_by_id, subscription_ids = _resolve_credential_and_subscriptions(
            subscription, all_subscriptions
        )
    except Exception as exc:  # noqa: BLE001 - translated into a friendly message below
        console.print(f"[red]Error:[/red] {friendly_error(exc)}")
        raise typer.Exit(1) from exc

    trends: list[trend.TrendSummary] = []
    for subscription_id in subscription_ids:
        label = names_by_id.get(subscription_id, subscription_id)
        try:
            with _progress() as progress:
                progress.add_task(f"Fetching trend data for {label}...", total=None)
                summary = trend.get_trend(credential, subscription_id, months=months)
        except Exception as exc:  # noqa: BLE001 - translated into a friendly message below
            console.print(f"[red]Error ({label}):[/red] {friendly_error(exc)}")
            continue
        trends.append(summary)
        console.print(Panel(f"[bold]{label}[/bold]", border_style="cyan"))
        console.print(trend.render_trend(summary))

    if output and trends:
        _export_all(trends, output, export.export_trend, "trend")


@budget_app.command("status")
def budget_status(
    subscription: list[str] = typer.Option(
        [], "--subscription", help="Subscription ID to query (repeatable)."
    ),
    all_subscriptions: bool = typer.Option(
        False, "--all-subscriptions", help="Query every subscription visible to this identity."
    ),
    output: list[Path] = typer.Option(
        [],
        "--output",
        help="Also write budget status to a file (.csv, .json, or .pdf; repeatable).",
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

    all_statuses: list[budgets.BudgetStatus] = []
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
        all_statuses.extend(statuses)
        console.print(budgets.render_budget_status(statuses))

    if output and all_statuses:
        _export_all(all_statuses, output, export.export_budget_statuses, "budget status")


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
    region: list[str] = typer.Option(
        [], "--region", help="Only scan resources in these Azure regions (repeatable)."
    ),
    output: list[Path] = typer.Option(
        [], "--output", help="Also write findings to a file (.csv, .json, or .pdf; repeatable)."
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

    regions = region or None
    all_findings: list[audit.Finding] = []
    for subscription_id in subscription_ids:
        label = names_by_id.get(subscription_id, subscription_id)
        console.rule(f"[bold cyan]{label}[/bold cyan]")

        findings: list[audit.Finding] = []

        try:
            with _progress() as progress:
                progress.add_task(f"Scanning resources for {label}...", total=None)
                resources = audit_queries.fetch_resources(credential, subscription_id, regions)
            findings += [
                dataclasses.replace(f, subscription_id=subscription_id)
                for f in audit.find_untagged_resources(resources)
            ]
        except Exception as exc:  # noqa: BLE001 - translated into a friendly message below
            console.print(f"[red]Error ({label}, resources):[/red] {friendly_error(exc)}")

        try:
            with _progress() as progress:
                progress.add_task(f"Scanning VMs for {label}...", total=None)
                vms = audit_queries.fetch_vms(credential, subscription_id, regions)
            findings += [
                dataclasses.replace(f, subscription_id=subscription_id)
                for f in audit.find_idle_vms(vms)
            ]
        except Exception as exc:  # noqa: BLE001 - translated into a friendly message below
            console.print(f"[red]Error ({label}, VMs):[/red] {friendly_error(exc)}")

        try:
            with _progress() as progress:
                progress.add_task(f"Scanning disks for {label}...", total=None)
                disks = audit_queries.fetch_disks(credential, subscription_id, regions)
            findings += [
                dataclasses.replace(f, subscription_id=subscription_id)
                for f in audit.find_unattached_disks(disks)
            ]
        except Exception as exc:  # noqa: BLE001 - translated into a friendly message below
            console.print(f"[red]Error ({label}, disks):[/red] {friendly_error(exc)}")

        try:
            with _progress() as progress:
                progress.add_task(f"Scanning public IPs for {label}...", total=None)
                ips = audit_queries.fetch_public_ips(credential, subscription_id, regions)
            findings += [
                dataclasses.replace(f, subscription_id=subscription_id)
                for f in audit.find_orphaned_public_ips(ips)
            ]
        except Exception as exc:  # noqa: BLE001 - translated into a friendly message below
            console.print(f"[red]Error ({label}, public IPs):[/red] {friendly_error(exc)}")

        if findings:
            console.print(audit.render_audit_report(findings))
        else:
            console.print("No findings.")
        all_findings.extend(findings)

    if output and all_findings:
        _export_all(all_findings, output, export.export_findings, "audit findings")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
