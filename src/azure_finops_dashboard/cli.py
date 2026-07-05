import typer
from rich.console import Console
from rich.table import Table

from azure_finops_dashboard import __version__, auth, subscriptions
from azure_finops_dashboard.errors import friendly_error

app = typer.Typer(
    name="azure-finops",
    help="Azure cost visibility and FinOps audit CLI.",
    add_completion=False,
)
subscriptions_app = typer.Typer(help="Inspect subscriptions visible to the current identity.")
app.add_typer(subscriptions_app, name="subscriptions")
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


def main() -> None:
    app()


if __name__ == "__main__":
    main()
