import csv
import json
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from azure_finops_dashboard.cost import CostSummary


def export_cost_summaries(summaries: list[CostSummary], path: Path) -> None:
    """Write cost summaries to disk. Format is inferred from the file extension."""
    writers = {
        ".csv": _write_csv,
        ".json": _write_json,
        ".pdf": _write_pdf,
    }
    suffix = path.suffix.lower()
    writer = writers.get(suffix)
    if writer is None:
        raise ValueError(
            f"Unsupported export format '{suffix}'. Use one of: {', '.join(writers)}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    writer(summaries, path)


def _write_csv(summaries: list[CostSummary], path: Path) -> None:
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


def _write_json(summaries: list[CostSummary], path: Path) -> None:
    data = [
        {
            "subscription_id": summary.subscription_id,
            "currency": summary.currency,
            "total_cost": summary.total_cost,
            "by_service": [{"name": name, "cost": cost} for name, cost in summary.by_service],
            "by_resource_group": [
                {"name": name, "cost": cost} for name, cost in summary.by_resource_group
            ],
        }
        for summary in summaries
    ]
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _write_pdf(summaries: list[CostSummary], path: Path) -> None:
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
        story.append(Spacer(1, 24))

    doc.build(story)


def _table(rows: list[tuple[str, float]], name_header: str) -> Table:
    data = [[name_header, "Cost"]] + [[name, f"{amount:,.2f}"] for name, amount in rows]
    table = Table(data)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ]
        )
    )
    return table
