import csv
import json
from pathlib import Path

import pytest

from azure_finops_dashboard.cost import CostSummary
from azure_finops_dashboard.export import export_cost_summaries

SUMMARIES = [
    CostSummary(
        subscription_id="sub-1",
        currency="USD",
        total_cost=123.45,
        by_service=[("Compute", 100.0), ("Storage", 23.45)],
        by_resource_group=[("rg-a", 123.45)],
    )
]


def test_export_csv(tmp_path: Path) -> None:
    path = tmp_path / "summary.csv"
    export_cost_summaries(SUMMARIES, path)

    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))

    assert rows[0] == ["subscription_id", "currency", "dimension", "name", "cost"]
    assert ["sub-1", "USD", "total", "", "123.45"] in rows
    assert ["sub-1", "USD", "service", "Compute", "100.0"] in rows
    assert ["sub-1", "USD", "resource_group", "rg-a", "123.45"] in rows


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
