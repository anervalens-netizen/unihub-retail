from typing import cast

import asyncpg

from scripts.map_store_pnl_sites import build_links, normalize


def test_normalize_ignores_closed_location_suffix() -> None:
    assert normalize("FOCSANI CARREFOUR - locatie inchisa") == normalize("Focsani Carrefour")


def test_normalize_removes_diacritics_and_spacing() -> None:
    assert normalize("Piața  Sudului") == "PIATASUDULUI"


def test_equal_fuzzy_scores_remain_unresolved_without_comparing_records() -> None:
    source_rows = cast(
        list[asyncpg.Record],
        [
            {
                "company_name": "Mobiup",
                "source_site_code": "TIE-SOURCE",
                "source_location_name": "Alpha",
            }
        ],
    )
    stores = cast(
        list[asyncpg.Record],
        [
            {"site_code": "TIE-A", "locatie": "Alphx", "firma": "Mobiup"},
            {"site_code": "TIE-B", "locatie": "Alphy", "firma": "Mobiup"},
        ],
    )

    links, unresolved = build_links(source_rows, stores)

    assert links == []
    assert len(unresolved) == 1
    assert "marja 0.00" in unresolved[0]
