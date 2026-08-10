from decimal import Decimal

import pytest

from services import grile_pilot_v2


class FakeRepo:
    async def get_expected_by_site(self, _month: str):
        return {
            "PROMEN": {
                "db_target": Decimal("74000"),
                "db_sales_mtd": Decimal("13636.40"),
                "db_max_sale_date": "2026-08-09",
            },
            "ORAUCH": {
                "db_target": Decimal("62000"),
                "db_sales_mtd": Decimal("18005"),
                "db_max_sale_date": "2026-08-09",
            },
        }

    async def get_hierarchy(self):
        return {
            "PROMEN": {"locatie": "PROMENADA", "firma": "MobiCell", "asm": "Andrei Stancu"},
            "ORAUCH": {"locatie": "ORADEA AUCHAN", "firma": "Mobiup", "asm": "Bogdana Costan"},
        }

    async def get_current_statuses(self, _month: str):
        return [
            {"site_code": "PROMEN", "grila_target": Decimal("74000"), "grila_sales": Decimal("13638")},
            {"site_code": "ORAUCH", "grila_target": Decimal("62000"), "grila_sales": Decimal("18005")},
        ]


@pytest.mark.asyncio
async def test_pilot_v2_groups_by_manager_and_reconciles_reports_and_v1(monkeypatch):
    async def fake_readings():
        empty = grile_pilot_v2.PilotV2Reading(None, None, None, "Grila Google nu poate fi citită")
        return {
            "PROMEN": grile_pilot_v2.PilotV2Reading(
                Decimal("74000"), Decimal("13636.40"), Decimal("43910.64")
            ),
            "ORAUCH": grile_pilot_v2.PilotV2Reading(
                Decimal("62000"), Decimal("18005"), Decimal("55323")
            ),
            "MCRFBAL": empty,
            "CRFFEER": empty,
            "ORAUCHAN": empty,
        }

    monkeypatch.setattr(grile_pilot_v2, "read_pilot_v2_sheets", fake_readings)

    result = await grile_pilot_v2.get_pilot_v2_overview(FakeRepo(), "2026-08")

    assert [manager["name"] for manager in result["managers"]] == [
        "Andrei Stancu",
        "Bogdana Costan",
        "Nealocat",
    ]
    stores = {
        store["site_code"]: store
        for manager in result["managers"]
        for store in manager["stores"]
    }
    assert stores["PROMEN"]["report_check"]["status"] == "ok"
    assert stores["PROMEN"]["v1_check"]["status"] == "problem"
    assert stores["PROMEN"]["v1_check"]["message"] == "Realizat V2 -2 lei"
    assert stores["ORAUCH"]["forecast_pct_v2"] == Decimal("89.2")


@pytest.mark.asyncio
async def test_pilot_v2_rejects_other_months(monkeypatch):
    with pytest.raises(ValueError, match="august 2026"):
        await grile_pilot_v2.get_pilot_v2_overview(FakeRepo(), "2026-07")
