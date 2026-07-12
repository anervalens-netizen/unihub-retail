"""Unit tests for SalariiService — mock-based, no DB needed."""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.salarii import SalariiService
from salary_identity import make_salary_person_id

PERSON_ID_KEY = "synthetic-hmac-key-for-tests-abcdefghijklmnopqrstuvwxyz"
PERSON_ID = make_salary_person_id("synthetic-private-id-a", "Ana Popescu", PERSON_ID_KEY)


class FakeRow(dict):
    def __getattr__(self, name: str):
        return self[name]


@pytest.fixture
def mock_repo():
    repo = MagicMock()
    repo.fetch_overview = AsyncMock()
    repo.fetch_evolution_main = AsyncMock(return_value=[])
    repo.fetch_evolution_single_company = AsyncMock(return_value=[])
    repo.fetch_agents_summary = AsyncMock(return_value={"items": [], "total": 0})
    repo.fetch_agent_history = AsyncMock(return_value=[])
    repo.fetch_agent_history_by_person_id = AsyncMock(return_value=[])
    repo.fetch_agent_salary_link = AsyncMock(return_value=None)
    repo.fetch_agent_history_by_salary_link = AsyncMock(return_value=[])
    repo.fetch_latest_month = AsyncMock(return_value=None)
    repo.fetch_summary_by_site = AsyncMock(return_value=[])
    repo.fetch_trend = AsyncMock(return_value=[])
    repo.fetch_stores = AsyncMock(return_value=[])
    repo.fetch_records = AsyncMock(return_value=[])
    return repo


@pytest.fixture
def service(mock_repo):
    return SalariiService(mock_repo, PERSON_ID_KEY)


class TestSalariiOverview:
    @pytest.mark.asyncio
    async def test_overview_no_months(self, service, mock_repo):
        mock_repo.fetch_overview.return_value = {
            "months_row": None,
            "total": Decimal("0"),
            "by_company": [],
            "record_count": 0,
            "agent_count": 0,
            "agent_month_count": 0,
            "avg_agent_month_count": 0,
            "avg_salary": Decimal("0"),
        }
        result = await service.get_overview(None, None, None, None)
        assert result["months_span"] is None
        assert result["total"] == Decimal("0")
        assert result["avg_salary"] == 0

    @pytest.mark.asyncio
    async def test_overview_with_months(self, service, mock_repo):
        mock_repo.fetch_overview.return_value = {
            "months_row": FakeRow(min_year=2024, min_month=1, max_year=2026, max_month=5),
            "total": Decimal("150000"),
            "by_company": [{"company": "FirmaA", "total": Decimal("100000")}],
            "record_count": 500,
            "agent_count": 25,
            "agent_month_count": 40,
            "avg_agent_month_count": 35,
            "avg_salary": Decimal("4100"),
        }
        result = await service.get_overview(None, None, None, None)
        assert result["months_span"] == [2024, 1, 2026, 5]
        assert result["total"] == Decimal("150000")
        assert result["avg_salary"] == Decimal("4100")
        assert result["avg_agent_month_count"] == 35

    @pytest.mark.asyncio
    async def test_overview_with_filters(self, service, mock_repo):
        mock_repo.fetch_overview.return_value = {
            "months_row": FakeRow(min_year=2025, min_month=6, max_year=2026, max_month=3),
            "total": Decimal("50000"),
            "by_company": [],
            "record_count": 100,
            "agent_count": 10,
            "agent_month_count": 20,
            "avg_agent_month_count": 18,
            "avg_salary": Decimal("3200"),
        }
        result = await service.get_overview("FirmaA", "SITE01", "Region1", "Asm1")
        assert result["months_span"] == [2025, 6, 2026, 3]
        assert mock_repo.fetch_overview.call_args.kwargs == {
            "company_name": "FirmaA",
            "site_code": "SITE01",
            "regional": "Region1",
            "asm": "Asm1",
        }


class TestSalariiEvolution:
    @pytest.mark.asyncio
    async def test_evolution_no_company(self, service, mock_repo):
        mock_repo.fetch_evolution_main.return_value = [
            FakeRow(month="2026-04", total=Decimal("10000"), mobicell=Decimal("5000"), mobiup=Decimal("5000")),
        ]
        result = await service.get_evolution(None, None, None, None)
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_evolution_with_company(self, service, mock_repo):
        mock_repo.fetch_evolution_single_company.return_value = [
            FakeRow(month="2026-04", total=Decimal("7000")),
        ]
        result = await service.get_evolution("FirmaA", None, None, None)
        assert len(result) == 1
        assert result[0]["total"] == 7000.0
        assert result[0]["mobicell"] == 0.0

    @pytest.mark.asyncio
    async def test_evolution_with_regional_asm(self, service, mock_repo):
        mock_repo.fetch_evolution_main.return_value = []
        result = await service.get_evolution(None, "SITE01", "Region1", "Asm1")
        call = mock_repo.fetch_evolution_main.call_args
        assert call.kwargs == {
            "company_name": None,
            "site_code": "SITE01",
            "regional": "Region1",
            "asm": "Asm1",
        }

    @pytest.mark.asyncio
    async def test_evolution_company_with_regional(self, service, mock_repo):
        mock_repo.fetch_evolution_single_company.return_value = []
        result = await service.get_evolution("FirmaA", "SITE01", "Region1", None)
        call = mock_repo.fetch_evolution_single_company.call_args
        assert call.kwargs == {
            "company_name": "FirmaA",
            "site_code": "SITE01",
            "regional": "Region1",
            "asm": None,
        }


class TestSalariiAgentsSummary:
    @pytest.mark.asyncio
    async def test_agents_summary_no_filters(self, service, mock_repo):
        mock_repo.fetch_agents_summary.return_value = {"items": [], "total": 0}
        result = await service.get_agents_summary(None, None, None, None, None, None, None, 10, 0)
        assert result["total"] == 0

    @pytest.mark.asyncio
    async def test_agents_summary_all_filters(self, service, mock_repo):
        mock_repo.fetch_agents_summary.return_value = {"items": [{"person_id": PERSON_ID, "full_name": "Test", "company_name": "FirmaA", "locatie": None, "month_count": 1, "avg_month_count": 1, "total_salary": Decimal("3000"), "avg_salary": Decimal("3000")}], "total": 1}
        result = await service.get_agents_summary("search", "FirmaA", "SITE01", "Reg1", "Asm1", 2026, 5, 10, 0)
        assert result["total"] == 1
        call = mock_repo.fetch_agents_summary.call_args
        assert call.kwargs == {
            "q": "search",
            "company_name": "FirmaA",
            "site_code": "SITE01",
            "regional": "Reg1",
            "asm": "Asm1",
            "year": 2026,
            "month": 5,
            "limit": 10,
            "offset": 0,
            "person_id_key": PERSON_ID_KEY,
        }


class TestSalariiAgentHistory:
    @pytest.mark.asyncio
    async def test_agent_history_rejects_malformed_person_id(self, service):
        with pytest.raises(ValueError):
            await service.get_agent_history("not-an-opaque-id")

    @pytest.mark.asyncio
    async def test_agent_history_empty(self, service, mock_repo):
        mock_repo.fetch_agent_history_by_person_id.return_value = []
        with pytest.raises(LookupError):
            await service.get_agent_history(PERSON_ID)

    @pytest.mark.asyncio
    async def test_agent_history_with_data(self, service, mock_repo):
        mock_repo.fetch_agent_history_by_person_id.return_value = [
            FakeRow(total_salary=Decimal("3000"), month=4, year=2026, company_name="F1", site_code=None, locatie=None),
            FakeRow(total_salary=Decimal("3500"), month=5, year=2026, company_name="F1", site_code=None, locatie=None),
        ]
        result = await service.get_agent_history(PERSON_ID)
        assert result["month_count"] == 2
        assert result["total"] == 6500.0
        assert result["avg"] == 3250.0
        assert result["avg_month_count"] == 2

    @pytest.mark.asyncio
    async def test_agent_history_average_excludes_months_under_2000(self, service, mock_repo):
        mock_repo.fetch_agent_history_by_person_id.return_value = [
            FakeRow(total_salary=Decimal("1500"), month=4, year=2026, company_name="F1", site_code=None, locatie=None),
            FakeRow(total_salary=Decimal("3000"), month=5, year=2026, company_name="F1", site_code=None, locatie=None),
        ]
        result = await service.get_agent_history(PERSON_ID)
        assert result["total"] == 4500.0
        assert result["month_count"] == 2
        assert result["avg_month_count"] == 1
        assert result["avg"] == 3000.0

    @pytest.mark.asyncio
    async def test_agent_history_by_retail_code_without_link(self, service, mock_repo):
        result = await service.get_agent_history_by_retail_code(agent_code="AG1", site_code="S1")

        assert result == {
            "link": None,
            "records": [],
            "total": 0.0,
            "avg": 0.0,
            "month_count": 0,
            "avg_month_count": 0,
        }
        mock_repo.fetch_agent_salary_link.assert_awaited_once_with(agent_code="AG1", site_code="S1", person_id_key=PERSON_ID_KEY)
        mock_repo.fetch_agent_history_by_salary_link.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_agent_history_by_retail_code_with_unknown_link(self, service, mock_repo):
        mock_repo.fetch_agent_salary_link.return_value = FakeRow(
            agent_code="AG1",
            site_code="S1",
            salary_full_name=None,
            salary_cnp=None,
            person_id=PERSON_ID,
            match_status="unknown",
            match_source="manual",
            confidence="unknown",
            effective_from_month="2026-06",
            note="Fara potrivire",
        )

        result = await service.get_agent_history_by_retail_code(agent_code="AG1", site_code="S1")

        assert result["link"] == {
            "agent_code": "AG1",
            "site_code": "S1",
            "salary_full_name": None,
            "person_id": None,
            "match_status": "unknown",
            "match_source": "manual",
            "confidence": "unknown",
            "effective_from_month": "2026-06",
            "note": "Fara potrivire",
        }
        assert result["records"] == []
        assert result["total"] == 0.0
        assert result["avg"] == 0.0
        assert result["month_count"] == 0
        assert result["avg_month_count"] == 0
        mock_repo.fetch_agent_history_by_salary_link.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_agent_history_by_retail_code_with_matched_link(self, service, mock_repo):
        mock_repo.fetch_agent_salary_link.return_value = FakeRow(
            agent_code="AG1",
            site_code="S1",
            salary_full_name="Ana Popescu",
            salary_cnp="synthetic-private-id-a",
            person_id=PERSON_ID,
            match_status="confirmed",
            match_source="manual",
            confidence="high",
            effective_from_month="2026-06",
            note="Confirmat manual",
        )
        mock_repo.fetch_agent_history_by_salary_link.return_value = [
            FakeRow(total_salary=Decimal("3000"), month=4, year=2026, company_name="F1", site_code=None, locatie=None),
            FakeRow(total_salary=Decimal("3500"), month=5, year=2026, company_name="F1", site_code=None, locatie=None),
        ]

        result = await service.get_agent_history_by_retail_code(agent_code="AG1", site_code="S1")

        assert result["link"]["salary_full_name"] == "Ana Popescu"
        assert result["records"] == [
            {"total_salary": 3000.0, "month": 4, "year": 2026, "company_name": "F1", "site_code": None, "locatie": None},
            {"total_salary": 3500.0, "month": 5, "year": 2026, "company_name": "F1", "site_code": None, "locatie": None},
        ]
        assert result["total"] == 6500.0
        assert result["avg"] == 3250.0
        assert result["month_count"] == 2
        assert result["avg_month_count"] == 2
        mock_repo.fetch_agent_history_by_salary_link.assert_awaited_once_with(
            person_id=PERSON_ID,
            person_id_key=PERSON_ID_KEY,
        )

    @pytest.mark.asyncio
    async def test_confirmed_link_with_empty_history_keeps_link_payload(self, service, mock_repo):
        mock_repo.fetch_agent_salary_link.return_value = FakeRow(
            agent_code="AG1", site_code="S1", salary_full_name="Ana Popescu",
            person_id=PERSON_ID, match_status="confirmed", match_source="manual",
            confidence="high", effective_from_month=None, note=None,
        )
        mock_repo.fetch_agent_history_by_salary_link.return_value = []
        result = await service.get_agent_history_by_retail_code(agent_code="AG1", site_code="S1")
        assert result["link"]["person_id"] == PERSON_ID
        assert result["records"] == []

    @pytest.mark.asyncio
    async def test_confirmed_link_with_blank_display_name_keeps_valid_person_id(self, service, mock_repo):
        mock_repo.fetch_agent_salary_link.return_value = FakeRow(
            agent_code="AG1", site_code="S1", salary_full_name="",
            person_id=PERSON_ID, match_status="confirmed", match_source="manual",
            confidence="high", effective_from_month=None, note=None,
        )
        mock_repo.fetch_agent_history_by_salary_link.return_value = []

        result = await service.get_agent_history_by_retail_code(agent_code="AG1", site_code="S1")

        assert result["link"]["person_id"] == PERSON_ID
        mock_repo.fetch_agent_history_by_salary_link.assert_awaited_once_with(
            person_id=PERSON_ID,
            person_id_key=PERSON_ID_KEY,
        )


class TestSalariiSummary:
    @pytest.mark.asyncio
    async def test_summary_no_data(self, service, mock_repo):
        result = await service.get_summary(None, None, None, None, None, None)
        assert result["month"] is None
        assert result["items"] == []

    @pytest.mark.asyncio
    async def test_summary_with_latest_month(self, service, mock_repo):
        mock_repo.fetch_latest_month.return_value = FakeRow(year=2026, month=5)
        mock_repo.fetch_summary_by_site.return_value = [
            FakeRow(site_code="S1", locatie="Store 1", company_name="F1",
                    total_salary=Decimal("5000"), agent_count=3, avg_agent_count=2,
                    avg_salary=Decimal("2250"), total_sales=Decimal("50000")),
        ]
        result = await service.get_summary(None, None, None, None, None, None)
        assert result["month"] == "2026-05"
        assert len(result["items"]) == 1
        assert result["items"][0]["ratio"] == pytest.approx(10.0)
        assert result["items"][0]["avg_salary"] == 2250.0
        assert result["items"][0]["avg_agent_count"] == 2

    @pytest.mark.asyncio
    async def test_summary_explicit_year_month(self, service, mock_repo):
        mock_repo.fetch_summary_by_site.return_value = [
            FakeRow(site_code="S1", locatie="Store 1", company_name="F1",
                    total_salary=Decimal("3000"), agent_count=2, avg_agent_count=1,
                    avg_salary=Decimal("2500"), total_sales=Decimal("0")),
        ]
        result = await service.get_summary(None, None, None, None, 2026, 4)
        assert result["month"] == "2026-04"
        assert result["items"][0]["ratio"] == 0


class TestSalariiTrend:
    @pytest.mark.asyncio
    async def test_trend_empty(self, service, mock_repo):
        result = await service.get_trend(None, None, None, None)
        assert result == []

    @pytest.mark.asyncio
    async def test_trend_aggregation(self, service, mock_repo):
        mock_repo.fetch_trend.return_value = [
            FakeRow(year=2026, month=4, total_salary=Decimal("5000"), total_sales=Decimal("50000"),
                    agent_count=2, avg_agent_count=1, avg_salary=Decimal("3500")),
            FakeRow(year=2026, month=5, total_salary=Decimal("6000"), total_sales=Decimal("60000"),
                    agent_count=3, avg_agent_count=2, avg_salary=Decimal("2750")),
        ]
        result = await service.get_trend(None, None, None, None)
        assert len(result) == 2
        assert result[0]["month"] == "2026-04"
        assert result[0]["avg_salary"] == 3500
        assert result[0]["avg_agent_count"] == 1

    @pytest.mark.asyncio
    async def test_trend_with_company(self, service, mock_repo):
        mock_repo.fetch_trend.return_value = [
            FakeRow(year=2026, month=5, total_salary=Decimal("4000"),
                    total_sales=Decimal("40000"), agent_count=1,
                    avg_agent_count=1, avg_salary=Decimal("4000")),
        ]
        result = await service.get_trend("FirmaA", None, None, None)
        assert len(result) == 1
        assert "by_company" in result[0]
        assert result[0]["by_company"] == {}
        assert result[0]["avg_salary"] == 4000


class TestSalariiSummaryFilters:
    @pytest.mark.asyncio
    async def test_summary_with_regional_asm(self, service, mock_repo):
        mock_repo.fetch_latest_month.return_value = FakeRow(year=2026, month=5)
        mock_repo.fetch_summary_by_site.return_value = []
        result = await service.get_summary(None, None, "Region1", "Asm1", None, None)
        assert result["month"] == "2026-05"

    @pytest.mark.asyncio
    async def test_summary_with_company_and_site(self, service, mock_repo):
        mock_repo.fetch_summary_by_site.return_value = [
            FakeRow(site_code="S1", locatie="Store 1", company_name="F1",
                    total_salary=Decimal("4000"), agent_count=2, avg_agent_count=1,
                    avg_salary=Decimal("3000"), total_sales=Decimal("40000")),
        ]
        result = await service.get_summary("FirmaA", "SITE01", None, None, 2026, 5)
        assert len(result["items"]) == 1
        assert result["items"][0]["ratio"] == pytest.approx(10.0)


class TestSalariiTrendFilters:
    @pytest.mark.asyncio
    async def test_trend_with_regional_asm(self, service, mock_repo):
        mock_repo.fetch_trend.return_value = []
        result = await service.get_trend(None, None, "Region1", "Asm1")
        call = mock_repo.fetch_trend.call_args
        assert call.kwargs == {
            "company_name": None,
            "site_code": None,
            "regional": "Region1",
            "asm": "Asm1",
        }

    @pytest.mark.asyncio
    async def test_trend_with_site_code(self, service, mock_repo):
        mock_repo.fetch_trend.return_value = []
        result = await service.get_trend(None, "SITE01", None, None)
        call = mock_repo.fetch_trend.call_args
        assert call.kwargs == {
            "company_name": None,
            "site_code": "SITE01",
            "regional": None,
            "asm": None,
        }


class TestSalariiStores:
    @pytest.mark.asyncio
    async def test_stores_no_filter(self, service, mock_repo):
        mock_repo.fetch_stores.return_value = [
            FakeRow(site_code="S1", locatie="Store 1"),
        ]
        result = await service.get_stores(None)
        assert len(result) == 1
        assert result[0]["site_code"] == "S1"

    @pytest.mark.asyncio
    async def test_stores_with_company(self, service, mock_repo):
        mock_repo.fetch_stores.return_value = []
        result = await service.get_stores("FirmaA")
        assert result == []
        call = mock_repo.fetch_stores.call_args
        assert call.kwargs == {"company_name": "FirmaA"}


class TestSalariiRecords:
    @pytest.mark.asyncio
    async def test_records_no_filter(self, service, mock_repo):
        mock_repo.fetch_records.return_value = [
            FakeRow(id=1, year=2026, month=5, full_name="Test Agent", person_id=PERSON_ID, total_salary=Decimal("3000"), company_name="FirmaA", site_code=None, locatie=None),
        ]
        result = await service.get_records(None, None, None, None, 10, 0)
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_records_all_filters(self, service, mock_repo):
        mock_repo.fetch_records.return_value = []
        result = await service.get_records("FirmaA", 2026, 5, "SITE01", 10, 0)
        assert result == []
        call = mock_repo.fetch_records.call_args
        assert call.kwargs == {
            "company_name": "FirmaA",
            "year": 2026,
            "month": 5,
            "site_code": "SITE01",
            "limit": 10,
            "offset": 0,
            "person_id_key": PERSON_ID_KEY,
        }
