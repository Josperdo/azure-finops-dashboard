from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone

from azure.core.credentials import TokenCredential
from azure.mgmt.costmanagement import CostManagementClient
from azure.mgmt.costmanagement.models import (
    QueryAggregation,
    QueryDataset,
    QueryDefinition,
    QueryTimePeriod,
)
from rich.table import Table

from azure_finops_dashboard.client_config import CLIENT_KWARGS
from azure_finops_dashboard.query_utils import as_float, column_index, parse_query_result


@dataclass
class TrendMonth:
    month: str  # "YYYY-MM"
    cost: float


@dataclass
class TrendSummary:
    subscription_id: str
    currency: str
    months: list[TrendMonth] = field(default_factory=list)
    deltas: list[float | None] = field(default_factory=list)


def _month_start(d: date) -> date:
    return d.replace(day=1)


def _shift_months(d: date, delta: int) -> date:
    month_index = d.month - 1 + delta
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, 1)


def _billing_month_key(value: object) -> str:
    # The API returns an ISO datetime string, e.g. "2026-03-01T00:00:00".
    if not isinstance(value, str) or len(value) < 7:
        raise TypeError(f"Expected a billing month string, got {value!r}")
    return value[:7]


def _month_range(start: date, end: date) -> list[str]:
    months = []
    cursor = start
    while cursor <= end:
        months.append(f"{cursor.year:04d}-{cursor.month:02d}")
        cursor = _shift_months(cursor, 1)
    return months


def get_trend(
    credential: TokenCredential, subscription_id: str, months: int = 6
) -> TrendSummary:
    """Fetch monthly spend for the last `months` calendar months (rolling, includes MTD)."""
    client = CostManagementClient(credential, **CLIENT_KWARGS)
    scope = f"/subscriptions/{subscription_id}"

    today = date.today()
    start = _shift_months(_month_start(today), -(months - 1))
    definition = QueryDefinition(
        type="ActualCost",
        timeframe="Custom",
        time_period=QueryTimePeriod(
            from_property=datetime.combine(start, time.min, tzinfo=timezone.utc),
            to=datetime.combine(today, time.max, tzinfo=timezone.utc),
        ),
        dataset=QueryDataset(
            granularity="Monthly",
            aggregation={"totalCost": QueryAggregation(name="Cost", function="Sum")},
            grouping=[],
        ),
    )
    result = client.query.usage(scope=scope, parameters=definition)
    columns, rows = parse_query_result(result)
    cost_idx = column_index(columns, "Cost")
    month_idx = column_index(columns, "BillingMonth")
    currency_idx = column_index(columns, "Currency")

    # The API omits months with zero cost entirely rather than returning a zero row,
    # so build the full expected month range and fill in the gaps.
    cost_by_month = {_billing_month_key(row[month_idx]): as_float(row[cost_idx]) for row in rows}
    month_entries = [
        TrendMonth(month=m, cost=cost_by_month.get(m, 0.0)) for m in _month_range(start, today)
    ]

    currency = str(rows[0][currency_idx]) if rows else ""

    deltas: list[float | None] = [None]
    for prev, curr in zip(month_entries, month_entries[1:], strict=False):
        deltas.append(((curr.cost - prev.cost) / prev.cost * 100) if prev.cost else None)

    return TrendSummary(
        subscription_id=subscription_id,
        currency=currency,
        months=month_entries,
        deltas=deltas,
    )


def _ascii_bar(value: float, max_value: float, width: int = 20) -> str:
    # Plain ASCII, not rich.bar.Bar: Bar renders Unicode block-shading characters with
    # no fallback, which crashes on Windows terminals stuck on a legacy cp1252 console
    # (confirmed against a real Windows terminal - Rich's Table borders auto-downgrade
    # to ASCII in that situation, but Bar does not).
    filled = round((value / max_value) * width) if max_value > 0 else 0
    return "#" * filled + "-" * (width - filled)


def _delta_color(delta: float | None) -> str:
    # No prior month to compare against - not a judgment either way, leave uncolored.
    if delta is None:
        return ""
    if delta > 0:
        return "red"  # spend went up
    if delta < 0:
        return "green"  # spend went down
    return "yellow"  # unchanged


def render_trend(trend: TrendSummary) -> Table:
    table = Table(title="Spend Trend", header_style="bold cyan")
    table.add_column("Month")
    table.add_column("Cost", justify="right")
    table.add_column("Change")
    table.add_column("Trend")

    max_cost = max((m.cost for m in trend.months), default=0.0)
    for month, delta in zip(trend.months, trend.deltas, strict=True):
        change = "-" if delta is None else f"{delta:+.1f}%"
        bar = _ascii_bar(month.cost, max_cost)
        color = _delta_color(delta)
        if color:
            change = f"[{color}]{change}[/{color}]"
            bar = f"[{color}]{bar}[/{color}]"
        table.add_row(month.month, f"{month.cost:,.2f} {trend.currency}", change, bar)
    return table
