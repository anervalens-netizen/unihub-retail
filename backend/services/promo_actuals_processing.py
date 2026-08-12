from __future__ import annotations

from datetime import date
import json
from pathlib import Path
from typing import Callable

from fastapi import HTTPException, status

from services.dashboard_specials import month_overlaps_period
from services.promo_generation_publisher import (
    PromoGenerationConflictError,
    PromoGenerationPointerIntegrityError,
)


PointerDigest = Callable[[Path], str | None]
PromoPublisher = Callable[..., tuple[str, str, str]]
ConfigValidator = Callable[[dict], tuple[object, str]]


def load_promo_config(
    *,
    data_dir: Path,
    expected_pointer_sha256: str | None,
    config_path: Path,
    pointer_sha256: PointerDigest,
) -> dict:
    try:
        if pointer_sha256(data_dir) != expected_pointer_sha256:
            raise PromoGenerationConflictError
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except PromoGenerationConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Configurația promo s-a schimbat; reîncarcă și reîncearcă"
            ),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Configuratia promo nu poate fi citita",
        ) from exc
    if (
        not isinstance(config, dict)
        or not isinstance(config.get("promotions"), list)
    ):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Configuratia promo este invalida",
        )
    return config


def _promotion_period(promotion: dict) -> tuple[date, date]:
    try:
        return (
            date.fromisoformat(str(promotion.get("start_date", ""))),
            date.fromisoformat(str(promotion.get("end_date", ""))),
        )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Configuratia promo este invalida",
        ) from None


def _previous_cutoff(promotion: dict) -> date | None:
    value = promotion.get("actuals_cutoff_date")
    try:
        return date.fromisoformat(str(value)) if value else None
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Configuratia promo este invalida",
        ) from None


def update_promo_config(
    config: dict,
    *,
    import_month: str,
    cutoff_date: date,
    sheet_name: str,
) -> int:
    updated = 0
    for promotion in config["promotions"]:
        if not isinstance(promotion, dict):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Configuratia promo este invalida",
            )
        start_date, end_date = _promotion_period(promotion)
        if not month_overlaps_period(
            import_month,
            start_date,
            end_date,
        ):
            continue
        previous_cutoff = _previous_cutoff(promotion)
        if previous_cutoff and cutoff_date < previous_cutoff:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Cutoff-ul promo nu poate regresa față de generația "
                    "curentă"
                ),
            )
        promotion["actuals_source_file"] = "@GENERATION_ACTUALS@"
        promotion["actuals_sheet"] = sheet_name
        promotion["actuals_cutoff_date"] = cutoff_date.isoformat()
        updated += 1
    if updated == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nu exista promotii configurate pentru luna selectata",
        )
    return updated


def publish_promo_config(
    *,
    data_dir: Path,
    config: dict,
    content: bytes,
    suffix: str,
    actuals_material: bytes,
    parser_resources: dict[str, int | float | str | None],
    expected_pointer_sha256: str | None,
    validate_config: ConfigValidator,
    publisher: PromoPublisher,
) -> tuple[str, str, str, str]:
    try:
        _definitions, material_sha256 = validate_config(config)
        generation_id, config_sha256, source_sha256 = publisher(
            data_dir=data_dir,
            config=config,
            content=content,
            suffix=suffix,
            material_sha256=material_sha256,
            actuals_material=actuals_material,
            parser_resources=parser_resources,
            expected_pointer_sha256=expected_pointer_sha256,
        )
    except PromoGenerationPointerIntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Configuratia promo activa este invalida; importul a fost oprit"
            ),
        ) from exc
    except PromoGenerationConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Configurația promo s-a schimbat; reîncarcă și reîncearcă"
            ),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Configuratia promo este invalida",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Generatia promo nu a putut fi promovata",
        ) from exc
    return (
        generation_id,
        config_sha256,
        source_sha256,
        material_sha256,
    )

