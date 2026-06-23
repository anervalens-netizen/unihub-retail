from __future__ import annotations

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
