from scripts.map_store_pnl_sites import normalize


def test_normalize_ignores_closed_location_suffix() -> None:
    assert normalize("FOCSANI CARREFOUR - locatie inchisa") == normalize("Focsani Carrefour")


def test_normalize_removes_diacritics_and_spacing() -> None:
    assert normalize("Piața  Sudului") == "PIATASUDULUI"
