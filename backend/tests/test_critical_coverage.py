from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.check_critical_coverage import evaluate_coverage


def report(*, importer: float = 95.1) -> dict:
    return {
        "files": {
            "permissions.py": {
                "summary": {"percent_covered": 100.0},
            },
            "services/importer.py": {
                "summary": {"percent_covered": importer},
            },
        }
    }


def test_critical_coverage_accepts_modules_at_or_above_floor() -> None:
    results = evaluate_coverage(
        report(),
        {
            "permissions.py": 100,
            "services/importer.py": 95,
        },
    )

    assert all(result.passed for result in results)


def test_critical_coverage_reports_regression_and_missing_module() -> None:
    results = evaluate_coverage(
        report(importer=94.99),
        {
            "permissions.py": 100,
            "services/importer.py": 95,
            "services/missing.py": 50,
        },
    )

    by_module = {result.module: result for result in results}
    assert by_module["permissions.py"].passed is True
    assert by_module["services/importer.py"].passed is False
    assert by_module["services/missing.py"].covered is None
    assert by_module["services/missing.py"].passed is False


def test_critical_coverage_rejects_invalid_report() -> None:
    with pytest.raises(ValueError, match="files object"):
        evaluate_coverage({}, {"services/importer.py": 95})


def test_critical_coverage_aggregates_modular_package() -> None:
    results = evaluate_coverage(
        {
            "files": {
                "services/target_calculator/__init__.py": {
                    "summary": {"covered_lines": 90, "num_statements": 100}
                },
                "services/target_calculator/scenarios.py": {
                    "summary": {"covered_lines": 9, "num_statements": 10}
                },
            }
        },
        {"services/target_calculator/*": 90},
    )

    assert results[0].covered == pytest.approx(90.0)
    assert results[0].passed is True


def test_split_export_boundaries_replace_the_removed_monolith_gate() -> None:
    backend = Path(__file__).resolve().parents[1]
    thresholds = json.loads(
        (backend / "critical_coverage_thresholds.json").read_text(encoding="utf-8")
    )

    assert "services/exports.py" not in thresholds
    expected = {
        "repositories/export_operations.py",
        "services/export_complex_worker.py",
        "services/export_operations.py",
        "services/export_xlsx_formatting.py",
        "services/exports/artifact.py",
        "services/exports/loaders.py",
        "services/exports/planner.py",
        "services/exports/service.py",
        "services/exports/table_renderer.py",
        "services/exports/validation.py",
    }
    assert expected.issubset(thresholds)
    assert all(float(thresholds[module]) >= 95 for module in expected)
