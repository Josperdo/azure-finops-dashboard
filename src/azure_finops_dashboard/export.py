import csv
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from azure_finops_dashboard.audit import Finding
from azure_finops_dashboard.budgets import BudgetStatus
from azure_finops_dashboard.cost import CostSummary
from azure_finops_dashboard.trend import TrendSummary

_STYLE_TABLE = TableStyle(
    [
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
    ]
)


def _resolve_writer(
    path: Path, writers: dict[str, Callable[[Any, Path], None]]
) -> Callable[[Any, Path], None]:
    suffix = path.suffix.lower()
    writer = writers.get(suffix)
    if writer is None:
        raise ValueError(f"Unsupported export format '{suffix}'. Use one of: {', '.join(writers)}")
    return writer


def _table(rows: list[tuple[str, float]], name_header: str) -> Table:
    data = [[name_header, "Cost"]] + [[name, f"{amount:,.2f}"] for name, amount in rows]
    table = Table(data)
    table.setStyle(_STYLE_TABLE)
    return table


# --- Cost summaries ---------------------------------------------------------


def export_cost_summaries(summaries: list[CostSummary], path: Path) -> None:
    """Write cost summaries to disk. Format is inferred from the file extension."""
    writer = _resolve_writer(
        path, {".csv": _write_cost_csv, ".json": _write_cost_json, ".pdf": _write_cost_pdf}
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    writer(summaries, path)


def _write_cost_csv(summaries: list[CostSummary], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["subscription_id", "currency", "dimension", "name", "cost"])
        for summary in summaries:
            writer.writerow(
                [summary.subscription_id, summary.currency, "total", "", summary.total_cost]
            )
            for name, amount in summary.by_service:
                writer.writerow(
                    [summary.subscription_id, summary.currency, "service", name, amount]
                )
            for name, amount in summary.by_resource_group:
                writer.writerow(
                    [summary.subscription_id, summary.currency, "resource_group", name, amount]
                )
            for tag_key, pairs in summary.by_tag.items():
                for name, amount in pairs:
                    writer.writerow(
                        [summary.subscription_id, summary.currency, f"tag:{tag_key}", name, amount]
                    )


def _write_cost_json(summaries: list[CostSummary], path: Path) -> None:
    data = [
        {
            "subscription_id": summary.subscription_id,
            "currency": summary.currency,
            "total_cost": summary.total_cost,
            "by_service": [{"name": name, "cost": cost} for name, cost in summary.by_service],
            "by_resource_group": [
                {"name": name, "cost": cost} for name, cost in summary.by_resource_group
            ],
            "by_tag": {
                tag_key: [{"name": name, "cost": cost} for name, cost in pairs]
                for tag_key, pairs in summary.by_tag.items()
            },
        }
        for summary in summaries
    ]
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _write_cost_pdf(summaries: list[CostSummary], path: Path) -> None:
    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(str(path), pagesize=letter)
    story = []

    for summary in summaries:
        story.append(Paragraph(summary.subscription_id, styles["Heading2"]))
        story.append(
            Paragraph(f"Total: {summary.total_cost:,.2f} {summary.currency}", styles["Normal"])
        )
        story.append(Spacer(1, 12))
        story.append(Paragraph("Top Services", styles["Heading3"]))
        story.append(_table(summary.by_service, "Service"))
        story.append(Spacer(1, 12))
        story.append(Paragraph("Top Resource Groups", styles["Heading3"]))
        story.append(_table(summary.by_resource_group, "Resource Group"))
        for tag_key, pairs in summary.by_tag.items():
            if pairs:
                story.append(Spacer(1, 12))
                story.append(Paragraph(f"Top by Tag: {tag_key}", styles["Heading3"]))
                story.append(_table(pairs, "Tag Value"))
        story.append(Spacer(1, 24))

    doc.build(story)


# --- Trend -------------------------------------------------------------------


def export_trend(trends: list[TrendSummary], path: Path) -> None:
    """Write spend trends to disk. Format is inferred from the file extension."""
    writer = _resolve_writer(
        path, {".csv": _write_trend_csv, ".json": _write_trend_json, ".pdf": _write_trend_pdf}
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    writer(trends, path)


def _write_trend_csv(trends: list[TrendSummary], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["subscription_id", "currency", "month", "cost", "change_percent"])
        for trend in trends:
            for month, delta in zip(trend.months, trend.deltas, strict=True):
                writer.writerow(
                    [
                        trend.subscription_id,
                        trend.currency,
                        month.month,
                        month.cost,
                        "" if delta is None else delta,
                    ]
                )


def _write_trend_json(trends: list[TrendSummary], path: Path) -> None:
    data = [
        {
            "subscription_id": trend.subscription_id,
            "currency": trend.currency,
            "months": [
                {"month": month.month, "cost": month.cost, "change_percent": delta}
                for month, delta in zip(trend.months, trend.deltas, strict=True)
            ],
        }
        for trend in trends
    ]
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _write_trend_pdf(trends: list[TrendSummary], path: Path) -> None:
    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(str(path), pagesize=letter)
    story = []

    for trend in trends:
        story.append(Paragraph(trend.subscription_id, styles["Heading2"]))
        story.append(Spacer(1, 12))
        rows = [
            (month.month, month.cost) for month, _ in zip(trend.months, trend.deltas, strict=True)
        ]
        story.append(_table(rows, "Month"))
        story.append(Spacer(1, 24))

    doc.build(story)


# --- Budgets -------------------------------------------------------------------


def export_budget_statuses(statuses: list[BudgetStatus], path: Path) -> None:
    """Write budget statuses to disk. Format is inferred from the file extension."""
    writer = _resolve_writer(
        path, {".csv": _write_budgets_csv, ".json": _write_budgets_json, ".pdf": _write_budgets_pdf}
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    writer(statuses, path)


def _write_budgets_csv(statuses: list[BudgetStatus], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "subscription_id",
                "name",
                "time_grain",
                "currency",
                "spend",
                "amount",
                "percent_used",
                "status",
            ]
        )
        for s in statuses:
            writer.writerow(
                [
                    s.subscription_id,
                    s.name,
                    s.time_grain,
                    s.currency,
                    s.current_spend,
                    s.amount,
                    s.percent_used,
                    s.status,
                ]
            )


def _write_budgets_json(statuses: list[BudgetStatus], path: Path) -> None:
    data = [
        {
            "subscription_id": s.subscription_id,
            "name": s.name,
            "time_grain": s.time_grain,
            "currency": s.currency,
            "spend": s.current_spend,
            "amount": s.amount,
            "percent_used": s.percent_used,
            "status": s.status,
        }
        for s in statuses
    ]
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _write_budgets_pdf(statuses: list[BudgetStatus], path: Path) -> None:
    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(str(path), pagesize=letter)
    header = ["Subscription", "Budget", "Time Grain", "Spend", "Amount", "% Used", "Status"]
    rows = [
        [
            s.subscription_id,
            s.name,
            s.time_grain,
            f"{s.current_spend:,.2f} {s.currency}",
            f"{s.amount:,.2f} {s.currency}",
            f"{s.percent_used:.1f}%",
            s.status,
        ]
        for s in statuses
    ]
    table = Table([header, *rows])
    table.setStyle(_STYLE_TABLE)
    doc.build([Paragraph("Budget Status", styles["Heading2"]), Spacer(1, 12), table])


# --- Audit findings ------------------------------------------------------------


def export_findings(findings: list[Finding], path: Path) -> None:
    """Write audit findings to disk. Format is inferred from the file extension."""
    writer = _resolve_writer(
        path,
        {".csv": _write_findings_csv, ".json": _write_findings_json, ".pdf": _write_findings_pdf},
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    writer(findings, path)


def _write_findings_csv(findings: list[Finding], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "subscription_id",
                "severity",
                "resource_type",
                "resource_group",
                "resource_name",
                "issue",
            ]
        )
        for finding in findings:
            writer.writerow(
                [
                    finding.subscription_id,
                    finding.severity,
                    finding.resource_type,
                    finding.resource_group,
                    finding.resource_name,
                    finding.issue,
                ]
            )


def _write_findings_json(findings: list[Finding], path: Path) -> None:
    data = [
        {
            "subscription_id": f.subscription_id,
            "severity": f.severity,
            "resource_type": f.resource_type,
            "resource_group": f.resource_group,
            "resource_name": f.resource_name,
            "issue": f.issue,
        }
        for f in findings
    ]
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _write_findings_pdf(findings: list[Finding], path: Path) -> None:
    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(str(path), pagesize=letter)
    header = ["Subscription", "Severity", "Type", "Resource Group", "Name", "Issue"]
    rows = [
        [f.subscription_id, f.severity, f.resource_type, f.resource_group, f.resource_name, f.issue]
        for f in findings
    ]
    table = Table([header, *rows])
    table.setStyle(_STYLE_TABLE)
    doc.build([Paragraph("FinOps Audit Findings", styles["Heading2"]), Spacer(1, 12), table])
