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


def test_prahova_carrefour_alias_does_not_conflate_balotesti() -> None:
    source_rows = cast(
        list[asyncpg.Record],
        [{
            "company_name": "Mobiup",
            "source_site_code": "CARPL",
            "source_location_name": "CARREFOUR PLOIESTI",
        }],
    )
    stores = cast(
        list[asyncpg.Record],
        [
            {"site_code": "PLCRF", "locatie": "PLOIESTI CARREFOUR", "firma": "Mobiup"},
            {"site_code": "MCRFBAL", "locatie": "CARREFOUR BALOTESTI", "firma": "Mobiup"},
        ],
    )

    links, unresolved = build_links(source_rows, stores)

    assert unresolved == []
    assert [(link.site_code, link.match_method, link.reviewed) for link in links] == [
        ("PLCRF", "manual_alias", True)
    ]


def test_reversed_finance_names_use_reviewed_aliases() -> None:
    source_rows = cast(
        list[asyncpg.Record],
        [
            {
                "company_name": "Mobicell",
                "source_site_code": "ACM",
                "source_location_name": "ALBA CAROLINA MALL",
            },
            {
                "company_name": "Mobicell",
                "source_site_code": "CTRAFI",
                "source_location_name": "COTROCENI AFI",
            },
        ],
    )
    stores = cast(
        list[asyncpg.Record],
        [
            {"site_code": "ALBACAROLINA", "locatie": "CAROLINA MALL ALBA", "firma": "Mobicell"},
            {"site_code": "AFICOTRO", "locatie": "AFI COTROCENI", "firma": "Mobicell"},
        ],
    )

    links, unresolved = build_links(source_rows, stores)

    assert unresolved == []
    assert [(link.source_site_code, link.site_code, link.match_method, link.reviewed) for link in links] == [
        ("ACM", "ALBACAROLINA", "manual_alias", True),
        ("CTRAFI", "AFICOTRO", "manual_alias", True),
    ]


def test_reviewed_aliases_preserve_renamed_and_transferred_store_history() -> None:
    source_rows = cast(
        list[asyncpg.Record],
        [
            {
                "company_name": "Mobicell",
                "source_site_code": "BRAILAPROMENADA",
                "source_location_name": "BRAILA PROMENADA",
            },
            {
                "company_name": "Mobicell",
                "source_site_code": "MOLDMALL",
                "source_location_name": "IASI MOLDOVA",
            },
        ],
    )
    stores = cast(
        list[asyncpg.Record],
        [
            {"site_code": "BRPROM", "locatie": "BRAILA PROMENADA", "firma": "Mobicell"},
            {"site_code": "ISMOLDMALL", "locatie": "IASI MOLDOVA MALL", "firma": "Mobiup"},
        ],
    )

    links, unresolved = build_links(source_rows, stores)

    assert unresolved == []
    assert [(link.source_site_code, link.site_code, link.match_method, link.reviewed) for link in links] == [
        ("BRAILAPROMENADA", "BRPROM", "manual_alias", True),
        ("MOLDMALL", "ISMOLDMALL", "manual_alias", True),
    ]
