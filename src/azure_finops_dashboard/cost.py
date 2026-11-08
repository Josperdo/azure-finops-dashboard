import time
from dataclasses import dataclass, field

from azure.core.credentials import TokenCredential
from azure.mgmt.costmanagement import CostManagementClient
from azure.mgmt.costmanagement.models import (
    QueryAggregation,
    QueryDataset,
    QueryDefinition,
    QueryGrouping,
    QueryTimePeriod,
)

from azure_finops_dashboard.client_config import CLIENT_KWARGS
from azure_finops_dashboard.query_utils import as_float, column_index, parse_query_result

TIMEFRAMES = {"mtd": "MonthToDate", "last-month": "TheLastMonth"}

# Cost Management is reported to throttle around 4 calls per scope per minute
# (https://learn.microsoft.com/en-us/answers/questions/1520105/) - get_cost_summary makes
# 3+ sequential calls itself (more with multiple tag keys), and firing them with zero
# pacing risks tripping that ceiling even with a dedicated ClientType quota pool (confirmed:
# a single-call query succeeded live while this function's 4-call burst still got a 429,
# immediately after the ClientType fix was added). This doesn't guarantee avoiding it, just
# makes a burst less likely to trip it.
_CALL_PACING_SECONDS = 2.0


@dataclass
class CostSummary:
    subscription_id: str
    currency: str
    total_cost: float
    by_service: list[tuple[str, float]] = field(default_factory=list)
    by_resource_group: list[tuple[str, float]] = field(default_factory=list)
    by_tag: dict[str, list[tuple[str, float]]] = field(default_factory=dict)


def _query(
    client: CostManagementClient,
    scope: str,
    timeframe: str,
    grouping: QueryGrouping | None,
    time_period: QueryTimePeriod | None = None,
) -> tuple[list[str], list[list[object]]]:
    definition = QueryDefinition(
        type="ActualCost",
        timeframe=timeframe,
        time_period=time_period,
        dataset=QueryDataset(
            granularity=None,
            aggregation={"totalCost": QueryAggregation(name="Cost", function="Sum")},
            grouping=[grouping] if grouping else [],
        ),
    )
    result = client.query.usage(scope=scope, parameters=definition)
    return parse_query_result(result)


def _rows_to_pairs(
    columns: list[str], rows: list[list[object]], group_by: str
) -> list[tuple[str, float]]:
    name_idx = column_index(columns, group_by)
    cost_idx = column_index(columns, "Cost")
    pairs = [
        (
            str(row[name_idx]) if row[name_idx] is not None else "(none)",
            as_float(row[cost_idx]),
        )
        for row in rows
    ]
    return sorted(pairs, key=lambda p: p[1], reverse=True)


def _merge_pairs(pair_lists: list[list[tuple[str, float]]], top_n: int) -> list[tuple[str, float]]:
    totals: dict[str, float] = {}
    for pairs in pair_lists:
        for name, amount in pairs:
            totals[name] = totals.get(name, 0.0) + amount
    return sorted(totals.items(), key=lambda p: p[1], reverse=True)[:top_n]


def rollup_cost_summaries(summaries: list[CostSummary], top_n: int = 10) -> CostSummary:
    """Combine multiple subscriptions' summaries into one merged view."""
    all_tag_keys = {key for s in summaries for key in s.by_tag}
    merged_by_tag = {
        key: _merge_pairs([s.by_tag.get(key, []) for s in summaries], top_n) for key in all_tag_keys
    }

    return CostSummary(
        subscription_id="(all)",
        currency=summaries[0].currency if summaries else "",
        total_cost=sum(s.total_cost for s in summaries),
        by_service=_merge_pairs([s.by_service for s in summaries], top_n),
        by_resource_group=_merge_pairs([s.by_resource_group for s in summaries], top_n),
        by_tag=merged_by_tag,
    )


def get_cost_summary(
    credential: TokenCredential,
    subscription_id: str,
    timeframe: str = "MonthToDate",
    top_n: int = 10,
    tag_keys: list[str] | None = None,
    time_period: QueryTimePeriod | None = None,
) -> CostSummary:
    """Fetch a cost summary for one subscription.

    `timeframe` follows the Cost Management API's TimeframeType values (e.g.
    "MonthToDate", "TheLastMonth", or "Custom" when `time_period` is supplied).
    """
    client = CostManagementClient(credential, **CLIENT_KWARGS)
    scope = f"/subscriptions/{subscription_id}"

    total_columns, total_rows = _query(
        client, scope, timeframe, grouping=None, time_period=time_period
    )
    cost_idx = column_index(total_columns, "Cost")
    currency_idx = column_index(total_columns, "Currency")
    total_cost = as_float(total_rows[0][cost_idx]) if total_rows else 0.0
    currency = str(total_rows[0][currency_idx]) if total_rows else ""

    time.sleep(_CALL_PACING_SECONDS)
    service_columns, service_rows = _query(
        client,
        scope,
        timeframe,
        grouping=QueryGrouping(type="Dimension", name="ServiceName"),
        time_period=time_period,
    )
    by_service = _rows_to_pairs(service_columns, service_rows, "ServiceName")[:top_n]

    time.sleep(_CALL_PACING_SECONDS)
    rg_columns, rg_rows = _query(
        client,
        scope,
        timeframe,
        grouping=QueryGrouping(type="Dimension", name="ResourceGroupName"),
        time_period=time_period,
    )
    by_resource_group = _rows_to_pairs(rg_columns, rg_rows, "ResourceGroupName")[:top_n]

    by_tag: dict[str, list[tuple[str, float]]] = {}
    for tag_key in tag_keys or []:
        time.sleep(_CALL_PACING_SECONDS)
        tag_columns, tag_rows = _query(
            client,
            scope,
            timeframe,
            grouping=QueryGrouping(type="TagKey", name=tag_key),
            time_period=time_period,
        )
        # TagKey groupings return fixed generic column names (TagKey/TagValue), not a
        # column named after the tag key itself - confirmed live, an assumption otherwise.
        by_tag[tag_key] = _rows_to_pairs(tag_columns, tag_rows, "TagValue")[:top_n]

    return CostSummary(
        subscription_id=subscription_id,
        currency=currency,
        total_cost=total_cost,
        by_service=by_service,
        by_resource_group=by_resource_group,
        by_tag=by_tag,
    )
