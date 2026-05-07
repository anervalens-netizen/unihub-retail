"""Extended tests for services/filters.py — cover where_clauses, transaction_filter_parts, scoped_clauses."""
from __future__ import annotations

from services.filters import (
    normalize_filter,
    base_filter_values,
    scoped_clauses,
    where_clauses,
    transaction_filter_parts,
)


def test_normalize_filter_none():
    assert normalize_filter(None) is None


def test_normalize_filter_sentinels():
    for s in ["Toate", "Toti", "Toți", "", "  Toate  "]:
        assert normalize_filter(s) is None, f"Expected None for sentinel '{s}'"


def test_normalize_filter_valid():
    assert normalize_filter("FirmaA") == "FirmaA"
    assert normalize_filter("  Region1  ") == "Region1"


def test_base_filter_values_no_filters():
    params, positions = base_filter_values("2026-05", None, None, None, None, None)
    assert params == ["2026-05"]
    assert positions == {}


def test_base_filter_values_all_filters():
    params, positions = base_filter_values("2026-05", "F1", "R1", "A1", "SITE01", "Agent1")
    assert params == ["2026-05", "SITE01", "Agent1"]
    assert "firma" not in positions
    assert "regional" not in positions
    assert "asm" not in positions
    assert positions["site_code"] == 2
    assert "agent" in positions
    assert positions["agent"] == 3


def test_base_filter_values_partial():
    params, positions = base_filter_values("2026-05", "F1", "Toate", None, "SITE01", None)
    assert params == ["2026-05", "SITE01"]
    assert "regional" not in positions
    assert "firma" not in positions
    assert positions["site_code"] == 2


def test_scoped_clauses_empty():
    result = scoped_clauses({}, site_alias="agg", store_alias="agg")
    assert result == ["agg.locatie NOT ILIKE 'TR %'"]


def test_scoped_clauses_with_month():
    result = scoped_clauses({}, site_alias="agg", store_alias="agg",
                            month_alias="agg.import_month", month_position=1)
    assert len(result) == 2
    assert "agg.locatie NOT ILIKE 'TR %'" in result
    assert "agg.import_month = $1" in result


def test_scoped_clauses_with_filters():
    positions = {"firma": 2, "regional": 3, "site_code": 4, "agent": 5}
    result = scoped_clauses(positions, site_alias="st", store_alias="s",
                            agent_alias="st", month_alias="st.import_month", month_position=1)
    assert len(result) == 4
    assert "s.locatie NOT ILIKE 'TR %'" in result
    assert not any("s.firma" in clause for clause in result)
    assert not any("s.regional" in clause for clause in result)
    assert "st.site_code = ANY(string_to_array($4::TEXT, ','))" in result
    assert "st.agent = ANY(string_to_array($5::TEXT, ','))" in result


def test_scoped_clauses_cartela_filter():
    result = scoped_clauses({}, site_alias="st", store_alias="s",
                            include_cartela_filter=True)
    assert any("is_cartela" in c for c in result)


def test_scoped_clauses_agent_excluded_without_alias():
    positions = {"agent": 2}
    result = scoped_clauses(positions, site_alias="st", store_alias="s", agent_alias=None)
    assert not any("agent" in c for c in result)


def test_where_clauses_no_filters():
    clauses, params = where_clauses("2026-05", None, None, None, None)
    assert len(clauses) >= 1
    assert "import_month = $1" in clauses
    assert "locatie NOT ILIKE 'TR %'" in clauses
    assert params == ["2026-05"]


def test_where_clauses_with_agent():
    clauses, params = where_clauses("2026-05", None, None, None, None, "Agent1", include_agent=True)
    assert any("agent" in c for c in clauses)
    assert "Agent1" in params


def test_where_clauses_all_filters():
    clauses, params = where_clauses("2026-05", "F1", "R1", "A1", "SITE01", "Agent1", include_agent=True)
    assert len(clauses) == 4
    assert params == ["2026-05", "SITE01", "Agent1"]
    assert not any("firma" in clause for clause in clauses)
    assert not any("regional" in clause for clause in clauses)
    assert not any("asm" in clause for clause in clauses)


def test_transaction_filter_parts_no_filters():
    clauses, params = transaction_filter_parts("2026-05", None, None, None, None, None)
    assert any("st.import_month" in c for c in clauses)
    assert any("is_cartela" in c for c in clauses)
    assert any("s.locatie NOT ILIKE 'TR %'" in c for c in clauses)
    assert params == ["2026-05"]


def test_transaction_filter_parts_all_filters():
    clauses, params = transaction_filter_parts("2026-05", "F1", "R1", "A1", "SITE01", "Agent1")
    assert params == ["2026-05", "SITE01", "Agent1"]
    assert not any("s.firma" in c for c in clauses)
    assert not any("s.regional" in c for c in clauses)
    assert not any("s.asm" in c for c in clauses)
    assert any("st.site_code" in c for c in clauses)
    assert any("st.agent" in c for c in clauses)
    assert any("is_cartela" in c for c in clauses)
