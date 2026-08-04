from dataclasses import dataclass, field

from azure.core.credentials import TokenCredential
from azure.mgmt.costmanagement import CostManagementClient
from azure.mgmt.costmanagement.models import (
    QueryAggregation,
    QueryDataset,
    QueryDefinition,
    QueryGrouping,
)

from azure_finops_dashboard.query_utils import as_float, column_index, parse_query_result

TIMEFRAMES = {"mtd": "MonthToDate", "last-month": "TheLastMonth"}


@dataclass
class CostSummary:
    subscription_id: str
    currency: str
    total_cost: float
    by_service: list[tuple[str, float]] = field(default_factory=list)
    by_resource_group: list[tuple[str, float]] = field(default_factory=list)


def _query(
    client: CostManagementClient, scope: str, timeframe: str, group_by: str | None
) -> tuple[list[str], list[list[object]]]:
    grouping = [QueryGrouping(type="Dimension", name=group_by)] if group_by else []
    definition = QueryDefinition(
        type="ActualCost",
        timeframe=timeframe,
        dataset=QueryDataset(
            granularity=None,
            aggregation={"totalCost": QueryAggregation(name="Cost", function="Sum")},
            grouping=grouping,
        ),
    )
    result = client.query.usage(scope=scope, parameters=definition)
    return parse_query_result(result)


def _rows_to_pairs(
    columns: list[str], rows: list[list[object]], group_by: str
) -> list[tuple[str, float]]:
    name_idx = column_index(columns, group_by)
    cost_idx = column_index(columns, "Cost")
    pairs = [(str(row[name_idx]), as_float(row[cost_idx])) for row in rows]
    return sorted(pairs, key=lambda p: p[1], reverse=True)


def get_cost_summary(
    credential: TokenCredential,
    subscription_id: str,
    timeframe: str = "MonthToDate",
    top_n: int = 10,
) -> CostSummary:
    """Fetch a month-to-date (or last-month) cost summary for one subscription."""
    client = CostManagementClient(credential)
    scope = f"/subscriptions/{subscription_id}"

    total_columns, total_rows = _query(client, scope, timeframe, group_by=None)
    cost_idx = column_index(total_columns, "Cost")
    currency_idx = column_index(total_columns, "Currency")
    total_cost = as_float(total_rows[0][cost_idx]) if total_rows else 0.0
    currency = str(total_rows[0][currency_idx]) if total_rows else ""

    service_columns, service_rows = _query(client, scope, timeframe, group_by="ServiceName")
    by_service = _rows_to_pairs(service_columns, service_rows, "ServiceName")[:top_n]

    rg_columns, rg_rows = _query(client, scope, timeframe, group_by="ResourceGroupName")
    by_resource_group = _rows_to_pairs(rg_columns, rg_rows, "ResourceGroupName")[:top_n]

    return CostSummary(
        subscription_id=subscription_id,
        currency=currency,
        total_cost=total_cost,
        by_service=by_service,
        by_resource_group=by_resource_group,
    )
