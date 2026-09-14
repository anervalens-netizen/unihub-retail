"""Archive rows never bypass the official salary import source."""
from repositories.salary_report_source import SALARY_MONTHLY_REPORT_SOURCE


def test_official_salary_source_excludes_archive_fallback():
    assert "salary_records" in SALARY_MONTHLY_REPORT_SOURCE
    assert "salary_history_rows" not in SALARY_MONTHLY_REPORT_SOURCE
    assert "UNION" not in SALARY_MONTHLY_REPORT_SOURCE.upper()
