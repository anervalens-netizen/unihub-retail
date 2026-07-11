from __future__ import annotations

import json
from datetime import date
from io import BytesIO
from pathlib import Path

import pandas as pd
import pytest
from fastapi import HTTPException, UploadFile

import services.imports as imports_module
from services.imports import ImportsService


def service() -> ImportsService:
    return ImportsService(repo=object(), pool=object())  # type: ignore[arg-type]


def upload(content: bytes = b"promo-report", filename: str | None = "promo.xlsx") -> UploadFile:
    return UploadFile(file=BytesIO(content), filename=filename)


def configure_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    config: object,
) -> Path:
    config_path = tmp_path / "hub_specials.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    monkeypatch.setattr(imports_module, "get_special_cards_config_path", lambda: config_path)
    monkeypatch.setattr(imports_module, "get_data_dir", lambda: tmp_path / "data")
    return config_path


@pytest.mark.asyncio
@pytest.mark.parametrize("filename", [None, "promo.csv"])
async def test_promo_actuals_rejects_invalid_filename(filename: str | None) -> None:
    with pytest.raises(HTTPException) as exc:
        await service().import_promo_actuals(
            file=upload(filename=filename),
            import_month="2026-06",
            cutoff_date=date(2026, 6, 15),
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_promo_actuals_rejects_invalid_month() -> None:
    with pytest.raises(HTTPException) as exc:
        await service().import_promo_actuals(
            file=upload(),
            import_month="not-a-month",
            cutoff_date=date(2026, 6, 15),
        )
    assert exc.value.status_code == 400
    assert exc.value.detail == "Luna este invalida"


@pytest.mark.asyncio
async def test_promo_actuals_rejects_cutoff_outside_month() -> None:
    with pytest.raises(HTTPException) as exc:
        await service().import_promo_actuals(
            file=upload(),
            import_month="2026-06",
            cutoff_date=date(2026, 5, 31),
        )
    assert exc.value.status_code == 400
    assert exc.value.detail == "Data cutoff trebuie sa fie in luna selectata"


@pytest.mark.asyncio
async def test_promo_actuals_enforces_upload_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAX_PROMO_REPORT_UPLOAD_BYTES", "3")
    with pytest.raises(HTTPException) as exc:
        await service().import_promo_actuals(
            file=upload(content=b"1234"),
            import_month="2026-06",
            cutoff_date=date(2026, 6, 15),
        )
    assert exc.value.status_code == 413


@pytest.mark.asyncio
async def test_promo_actuals_rejects_empty_report() -> None:
    with pytest.raises(HTTPException) as exc:
        await service().import_promo_actuals(
            file=upload(content=b""),
            import_month="2026-06",
            cutoff_date=date(2026, 6, 15),
        )
    assert exc.value.status_code == 400
    assert exc.value.detail == "Raportul este gol"


@pytest.mark.asyncio
async def test_promo_actuals_reports_unreadable_config(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    missing = tmp_path / "missing.json"
    monkeypatch.setattr(imports_module, "get_special_cards_config_path", lambda: missing)
    monkeypatch.setattr(
        ImportsService,
        "_validate_promo_actuals_report",
        staticmethod(lambda _: (1, 2)),
    )

    with pytest.raises(HTTPException) as exc:
        await service().import_promo_actuals(
            file=upload(),
            import_month="2026-06",
            cutoff_date=date(2026, 6, 15),
        )
    assert exc.value.status_code == 500
    assert exc.value.detail == "Configuratia promo nu poate fi citita"


@pytest.mark.asyncio
@pytest.mark.parametrize("config", [[], {"promotions": {}}])
async def test_promo_actuals_rejects_invalid_config_shape(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    config: object,
) -> None:
    configure_paths(monkeypatch, tmp_path, config)
    monkeypatch.setattr(
        ImportsService,
        "_validate_promo_actuals_report",
        staticmethod(lambda _: (1, 2)),
    )

    with pytest.raises(HTTPException) as exc:
        await service().import_promo_actuals(
            file=upload(),
            import_month="2026-06",
            cutoff_date=date(2026, 6, 15),
        )
    assert exc.value.status_code == 500
    assert exc.value.detail == "Configuratia promo este invalida"


@pytest.mark.asyncio
async def test_promo_actuals_persists_file_and_updates_only_matching_promotions(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config_path = configure_paths(
        monkeypatch,
        tmp_path,
        {
            "promotions": [
                "invalid-entry",
                {"start_date": "invalid", "end_date": "2026-06-30"},
                {"key": "other-month", "start_date": "2026-05-01", "end_date": "2026-05-31"},
                {"key": "active", "start_date": "2026-06-01", "end_date": "2026-06-30"},
            ]
        },
    )
    monkeypatch.setattr(
        ImportsService,
        "_validate_promo_actuals_report",
        staticmethod(lambda _: (3, 7)),
    )

    result = await service().import_promo_actuals(
        file=upload(content=b"valid-promo-data", filename="PROMO.XLSX"),
        import_month="2026-06",
        cutoff_date=date(2026, 6, 15),
    )

    assert result.report_rows == 3
    assert result.promo_units == 7
    assert result.updated_promotions == 1
    assert result.filename == "PROMO.XLSX"

    stored = json.loads(config_path.read_text(encoding="utf-8"))
    active = next(item for item in stored["promotions"] if isinstance(item, dict) and item.get("key") == "active")
    destination = Path(active["actuals_source_file"])
    assert destination.read_bytes() == b"valid-promo-data"
    assert destination.suffix == ".xlsx"
    assert active["actuals_sheet"] == "AccesoriPromoLunar"
    assert active["actuals_cutoff_date"] == "2026-06-15"
    other = next(item for item in stored["promotions"] if isinstance(item, dict) and item.get("key") == "other-month")
    assert "actuals_source_file" not in other


@pytest.mark.asyncio
async def test_promo_actuals_removes_saved_file_when_no_promotion_matches(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    configure_paths(
        monkeypatch,
        tmp_path,
        {"promotions": [{"start_date": "2026-05-01", "end_date": "2026-05-31"}]},
    )
    monkeypatch.setattr(
        ImportsService,
        "_validate_promo_actuals_report",
        staticmethod(lambda _: (1, 1)),
    )

    with pytest.raises(HTTPException) as exc:
        await service().import_promo_actuals(
            file=upload(content=b"orphan"),
            import_month="2026-06",
            cutoff_date=date(2026, 6, 15),
        )

    assert exc.value.status_code == 400
    assert exc.value.detail == "Nu exista promotii configurate pentru luna selectata"
    assert list((tmp_path / "data").rglob("*")) == [tmp_path / "data" / "promo_actuals", tmp_path / "data" / "promo_actuals" / "2026-06"]


def test_validate_promo_actuals_report_maps_read_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(imports_module.pd, "read_excel", lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("bad workbook")))

    with pytest.raises(HTTPException) as exc:
        ImportsService._validate_promo_actuals_report(b"bad")
    assert exc.value.status_code == 400
    assert "AccesoriPromoLunar" in str(exc.value.detail)


def test_validate_promo_actuals_report_requires_expected_columns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(imports_module.pd, "read_excel", lambda *args, **kwargs: pd.DataFrame({"Other": [1]}))

    with pytest.raises(HTTPException) as exc:
        ImportsService._validate_promo_actuals_report(b"data")
    assert exc.value.status_code == 400
    assert "SiteCode" in str(exc.value.detail)


def test_validate_promo_actuals_report_counts_only_positive_valid_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dataframe = pd.DataFrame(
        {
            "SiteCode": ["S1", "", "nan", "S2", "S3"],
            "Cod": ["I1", "I2", "I3", "nan", "I4"],
            "Promo Luna Curenta": [2, 3, 4, 5, -1],
        }
    )
    monkeypatch.setattr(imports_module.pd, "read_excel", lambda *args, **kwargs: dataframe)

    assert ImportsService._validate_promo_actuals_report(b"data") == (1, 2)


def test_validate_promo_actuals_report_rejects_no_positive_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dataframe = pd.DataFrame(
        {
            "site_code": ["S1", "S2"],
            "item_code": ["I1", "I2"],
            "promo_qty": [0, -1],
        }
    )
    monkeypatch.setattr(imports_module.pd, "read_excel", lambda *args, **kwargs: dataframe)

    with pytest.raises(HTTPException) as exc:
        ImportsService._validate_promo_actuals_report(b"data")
    assert exc.value.status_code == 400
    assert exc.value.detail == "Raportul nu contine unitati promo pozitive"
