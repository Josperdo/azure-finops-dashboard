from collections.abc import Iterable
from dataclasses import dataclass
from typing import cast

from azure.core.credentials import TokenCredential
from azure.mgmt.consumption import ConsumptionManagementClient
from azure.mgmt.consumption.models import Budget
from rich.table import Table

from azure_finops_dashboard.client_config import CLIENT_KWARGS

WARNING_THRESHOLD = 80.0
BREACH_THRESHOLD = 100.0

STATUS_STYLE = {"breached": "red", "warning": "yellow", "ok": "green"}
STATUS_ORDER = {"breached": 0, "warning": 1, "ok": 2}


@dataclass
class BudgetStatus:
    name: str
    amount: float
    current_spend: float
    currency: str
    time_grain: str
    percent_used: float
    status: str  # "breached" | "warning" | "ok"


def _status_for(percent_used: float) -> str:
    if percent_used >= BREACH_THRESHOLD:
        return "breached"
    if percent_used >= WARNING_THRESHOLD:
        return "warning"
    return "ok"


def list_budget_statuses(credential: TokenCredential, subscription_id: str) -> list[BudgetStatus]:
    """List budgets for a subscription along with their current breach status."""
    client = ConsumptionManagementClient(
        credential, subscription_id=subscription_id, **CLIENT_KWARGS
    )
    scope = f"/subscriptions/{subscription_id}"

    # The generated SDK stub types this as Iterable[BudgetsListResult] (the page model),
    # but azure-core's ItemPaged flattens pages at iteration time and actually yields
    # individual Budget items - the stub is just wrong here.
    raw_budgets = cast("Iterable[Budget]", client.budgets.list(scope=scope))

    statuses = []
    for budget in raw_budgets:
        amount = float(budget.amount) if budget.amount is not None else 0.0
        current_spend = (
            float(budget.current_spend.amount)
            if budget.current_spend and budget.current_spend.amount is not None
            else 0.0
        )
        currency = budget.current_spend.unit if budget.current_spend else ""
        percent_used = (current_spend / amount * 100) if amount else 0.0
        statuses.append(
            BudgetStatus(
                name=str(budget.name),
                amount=amount,
                current_spend=current_spend,
                currency=currency or "",
                time_grain=str(budget.time_grain) if budget.time_grain else "",
                percent_used=percent_used,
                status=_status_for(percent_used),
            )
        )
    return sorted(statuses, key=lambda s: STATUS_ORDER.get(s.status, 99))


def render_budget_status(statuses: list[BudgetStatus]) -> Table:
    table = Table(title="Budget Status", header_style="bold cyan")
    table.add_column("Budget")
    table.add_column("Time Grain")
    table.add_column("Spend", justify="right")
    table.add_column("Amount", justify="right")
    table.add_column("% Used", justify="right")
    table.add_column("Status")
    for s in statuses:
        style = STATUS_STYLE.get(s.status, "")
        table.add_row(
            s.name,
            s.time_grain,
            f"{s.current_spend:,.2f} {s.currency}",
            f"{s.amount:,.2f} {s.currency}",
            f"{s.percent_used:.1f}%",
            f"[{style}]{s.status}[/{style}]" if style else s.status,
        )
    return table
