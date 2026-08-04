import csv
import json
from pathlib import Path

import pytest

from azure_finops_dashboard.audit import Finding
from azure_finops_dashboard.budgets import BudgetStatus
from azure_finops_dashboard.cost import CostSummary
from azure_finops_dashboard.export import (
    export_budget_statuses,
    export_cost_summaries,
    export_findings,
    export_trend,
)
from azure_finops_dashboard.trend import TrendMonth, TrendSummary

SUMMARIES = [
    CostSummary(
        subscription_id="sub-1",
        currency="USD",
        total_cost=123.45,
        by_service=[("Compute", 100.0), ("Storage", 23.45)],
        by_resource_group=[("rg-a", 123.45)],
        by_tag={"Environment": [("prod", 123.45)]},
    )
]

TRENDS = [
    TrendSummary(
        subscription_id="sub-1",
        currency="USD",
        months=[TrendMonth(month="2024-01", cost=100.0), TrendMonth(month="2024-02", cost=150.0)],
        deltas=[None, 50.0],
    )
]

BUDGET_STATUSES = [
    BudgetStatus(
        name="my-budget",
        amount=100.0,
        current_spend=50.0,
        currency="USD",
        time_grain="Monthly",
        percent_used=50.0,
        status="ok",
        subscription_id="sub-1",
    )
]

FINDINGS = [
    Finding(
        resource_id="id-1",
        resource_name="res-1",
        resource_group="rg-a",
        resource_type="storage_account",
        issue="No tags applied",
        severity="low",
        subscription_id="sub-1",
    )
]


# --- Cost summaries ---------------------------------------------------------


def test_export_csv(tmp_path: Path) -> None:
    path = tmp_path / "summary.csv"
    export_cost_summaries(SUMMARIES, path)

    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))

    assert rows[0] == ["subscription_id", "currency", "dimension", "name", "cost"]
    assert ["sub-1", "USD", "total", "", "123.45"] in rows
    assert ["sub-1", "USD", "service", "Compute", "100.0"] in rows
    assert ["sub-1", "USD", "resource_group", "rg-a", "123.45"] in rows
    assert ["sub-1", "USD", "tag:Environment", "prod", "123.45"] in rows


def test_export_json(tmp_path: Path) -> None:
    path = tmp_path / "summary.json"
    export_cost_summaries(SUMMARIES, path)

    data = json.loads(path.read_text(encoding="utf-8"))

    assert data == [
        {
            "subscription_id": "sub-1",
            "currency": "USD",
            "total_cost": 123.45,
            "by_service": [
                {"name": "Compute", "cost": 100.0},
                {"name": "Storage", "cost": 23.45},
            ],
            "by_resource_group": [{"name": "rg-a", "cost": 123.45}],
            "by_tag": {"Environment": [{"name": "prod", "cost": 123.45}]},
        }
    ]


def test_export_pdf(tmp_path: Path) -> None:
    path = tmp_path / "summary.pdf"
    export_cost_summaries(SUMMARIES, path)

    assert path.exists()
    assert path.read_bytes()[:5] == b"%PDF-"


def test_export_unsupported_extension(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Unsupported export format"):
        export_cost_summaries(SUMMARIES, tmp_path / "summary.txt")


def test_export_creates_parent_directories(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "dir" / "summary.json"
    export_cost_summaries(SUMMARIES, path)
    assert path.exists()


# --- Trend -------------------------------------------------------------------


def test_export_trend_csv(tmp_path: Path) -> None:
    path = tmp_path / "trend.csv"
    export_trend(TRENDS, path)

    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))

    assert rows[0] == ["subscription_id", "currency", "month", "cost", "change_percent"]
    assert ["sub-1", "USD", "2024-01", "100.0", ""] in rows
    assert ["sub-1", "USD", "2024-02", "150.0", "50.0"] in rows


def test_export_trend_json(tmp_path: Path) -> None:
    path = tmp_path / "trend.json"
    export_trend(TRENDS, path)

    data = json.loads(path.read_text(encoding="utf-8"))

    assert data == [
        {
            "subscription_id": "sub-1",
            "currency": "USD",
            "months": [
                {"month": "2024-01", "cost": 100.0, "change_percent": None},
                {"month": "2024-02", "cost": 150.0, "change_percent": 50.0},
            ],
        }
    ]


def test_export_trend_pdf(tmp_path: Path) -> None:
    path = tmp_path / "trend.pdf"
    export_trend(TRENDS, path)
    assert path.read_bytes()[:5] == b"%PDF-"


def test_export_trend_unsupported_extension(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Unsupported export format"):
        export_trend(TRENDS, tmp_path / "trend.txt")


# --- Budgets -------------------------------------------------------------------


def test_export_budget_statuses_csv(tmp_path: Path) -> None:
    path = tmp_path / "budgets.csv"
    export_budget_statuses(BUDGET_STATUSES, path)

    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))

    assert rows[0] == [
        "subscription_id",
        "name",
        "time_grain",
        "currency",
        "spend",
        "amount",
        "percent_used",
        "status",
    ]
    assert ["sub-1", "my-budget", "Monthly", "USD", "50.0", "100.0", "50.0", "ok"] in rows


def test_export_budget_statuses_json(tmp_path: Path) -> None:
    path = tmp_path / "budgets.json"
    export_budget_statuses(BUDGET_STATUSES, path)

    data = json.loads(path.read_text(encoding="utf-8"))

    assert data == [
        {
            "subscription_id": "sub-1",
            "name": "my-budget",
            "time_grain": "Monthly",
            "currency": "USD",
            "spend": 50.0,
            "amount": 100.0,
            "percent_used": 50.0,
            "status": "ok",
        }
    ]


def test_export_budget_statuses_pdf(tmp_path: Path) -> None:
    path = tmp_path / "budgets.pdf"
    export_budget_statuses(BUDGET_STATUSES, path)
    assert path.read_bytes()[:5] == b"%PDF-"


# --- Audit findings ------------------------------------------------------------


def test_export_findings_csv(tmp_path: Path) -> None:
    path = tmp_path / "findings.csv"
    export_findings(FINDINGS, path)

    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))

    assert rows[0] == [
        "subscription_id",
        "severity",
        "resource_type",
        "resource_group",
        "resource_name",
        "issue",
    ]
    assert ["sub-1", "low", "storage_account", "rg-a", "res-1", "No tags applied"] in rows


def test_export_findings_json(tmp_path: Path) -> None:
    path = tmp_path / "findings.json"
    export_findings(FINDINGS, path)

    data = json.loads(path.read_text(encoding="utf-8"))

    assert data == [
        {
            "subscription_id": "sub-1",
            "severity": "low",
            "resource_type": "storage_account",
            "resource_group": "rg-a",
            "resource_name": "res-1",
            "issue": "No tags applied",
        }
    ]


def test_export_findings_pdf(tmp_path: Path) -> None:
    path = tmp_path / "findings.pdf"
    export_findings(FINDINGS, path)
    assert path.read_bytes()[:5] == b"%PDF-"
