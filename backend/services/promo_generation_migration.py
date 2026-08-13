"""One-shot, fail-closed migration of legacy Promo generation pointers.
The v1 pointer format predates the canonical POS JSON materialization.  It
references approved spreadsheets directly, so the v2 runtime correctly marks
it unusable rather than reparsing an unbounded workbook on every dashboard
request.  This module creates a *new* immutable v2 generation and switches the
pointer once, guarded by the exact v1 pointer bytes observed during planning.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import shutil
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import HTTPException

from services.dashboard_specials import validate_special_cards_config
from services.imports import (
    ImportsService, PromoActualsParseResult, _promo_actuals_material_bytes,
)
from services.product_lists import get_repo_root, resolve_path
from services.promo_generation_migration_hash import (
    target_generation_id as _target_generation_id,
)
from services.promo_generation_publisher import (
    _canonical_json_bytes,
    _fsync_directory,
    _write_durable_private_file,
)
from services.spreadsheet_safety import (
    PROMO_ACTUALS_SPREADSHEET_LIMITS,
    SpreadsheetUploadError,
    validate_spreadsheet_upload,
)


class PromoGenerationMigrationError(RuntimeError):
    """A legacy generation cannot be safely converted without operator repair."""


class PromoGenerationMigrationConflict(PromoGenerationMigrationError):
    """The v1 pointer changed between dry-run validation and promotion."""


@dataclass(frozen=True, slots=True)
class PromoGenerationMigrationResult:
    status: str
    previous_generation_id: str
    generation_id: str | None
    source_count: int
    promotion_count: int
    pointer_sha256: str


@dataclass(frozen=True, slots=True)
class _SourcePlan:
    legacy_path: Path
    source_sha256: str
    cutoff_date: date
    import_month: str
    sheet_name: str
    content: bytes
    material: bytes
    source_name: str
    material_name: str


@dataclass(frozen=True, slots=True)
class _MigrationPlan:
    data_dir: Path
    pointer_path: Path
    expected_pointer: bytes
    previous_generation_id: str
    generation_id: str
    config: dict[str, Any]
    sources: tuple[_SourcePlan, ...]
    material_sha256: str


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _read_json(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        content = path.read_bytes()
        payload = json.loads(content)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PromoGenerationMigrationError(f"{label} este invalid.") from exc
    if not isinstance(payload, dict):
        raise PromoGenerationMigrationError(f"{label} este invalid.")
    return payload, content


def _valid_generation_id(value: object) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 32
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise PromoGenerationMigrationError("ID-ul generației Promo este invalid.")
    return value


def _within_generation_root(root: Path, relative: object) -> Path:
    if not isinstance(relative, str) or not relative:
        raise PromoGenerationMigrationError("Calea configului generației Promo este invalidă.")
    candidate_relative = Path(relative)
    if candidate_relative.is_absolute() or ".." in candidate_relative.parts:
        raise PromoGenerationMigrationError("Calea configului generației Promo este invalidă.")
    candidate = (root / candidate_relative).resolve()
    if candidate.parent.parent != root.resolve() or not candidate.is_file():
        raise PromoGenerationMigrationError("Configul generației Promo lipsește.")
    return candidate


def _verify_recovery_pointer(root: Path, pointer: dict[str, Any]) -> None:
    """Validate v1 pointer evidence when this v2 was produced by this tool."""
    raw_file = pointer.get("previous_pointer_file")
    expected_sha256 = pointer.get("previous_pointer_sha256")
    if raw_file is None and expected_sha256 is None:
        return
    if not isinstance(raw_file, str) or not isinstance(expected_sha256, str) or len(expected_sha256) != 64:
        raise PromoGenerationMigrationError("Evidence-ul pointerului Promo precedent este invalid.")
    path = _within_generation_root(root, raw_file)
    if _sha256(path.read_bytes()) != expected_sha256:
        raise PromoGenerationMigrationError("Evidence-ul pointerului Promo precedent nu corespunde hashului.")


def _source_manifest(pointer: dict[str, Any]) -> dict[str, str]:
    raw_manifest = pointer.get("actuals")
    if not isinstance(raw_manifest, list) or not raw_manifest:
        raise PromoGenerationMigrationError("Manifestul surselor Promo este invalid.")
    result: dict[str, str] = {}
    for entry in raw_manifest:
        if not isinstance(entry, dict):
            raise PromoGenerationMigrationError("Manifestul surselor Promo este invalid.")
        raw_path = entry.get("file")
        sha256 = entry.get("sha256")
        if (
            not isinstance(raw_path, str)
            or not raw_path
            or not isinstance(sha256, str)
            or len(sha256) != 64
            or any(character not in "0123456789abcdef" for character in sha256)
            or raw_path in result
        ):
            raise PromoGenerationMigrationError("Manifestul surselor Promo este invalid.")
        result[raw_path] = sha256
    return result


def _parse_cutoff(value: object) -> date:
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise PromoGenerationMigrationError("Cutoff-ul unei surse Promo este invalid.") from exc


def _source_key(raw_path: str, cutoff: date, sheet_name: str) -> tuple[str, str, str]:
    return raw_path, cutoff.isoformat(), sheet_name


def _parse_source(content: bytes, suffix: str, sheet_name: str) -> PromoActualsParseResult:
    try:
        validate_spreadsheet_upload(
            content,
            suffix,
            limits=PROMO_ACTUALS_SPREADSHEET_LIMITS,
        )
    except SpreadsheetUploadError as exc:
        raise PromoGenerationMigrationError("O sursă Promo nu respectă limitele structurale.") from exc
    try:
        parsed = ImportsService._validate_promo_actuals_report(content, sheet_name=sheet_name)
    except HTTPException as exc:
        raise PromoGenerationMigrationError("O sursă Promo nu poate fi materializată.") from exc
    if not isinstance(parsed, PromoActualsParseResult):
        raise PromoGenerationMigrationError("Parserul Promo nu a produs materializarea canonică.")
    return parsed


def _already_v2_result(
    data_dir: Path,
    root: Path,
    pointer: dict[str, Any],
    *,
    generation_id: str,
    pointer_hash: str,
) -> PromoGenerationMigrationResult:
    from services.dashboard_specials import _generated_config_path

    try:
        _generated_config_path(data_dir)
    except ValueError as exc:
        raise PromoGenerationMigrationError(
            "Generația Promo v2 activă este invalidă."
        ) from exc
    _verify_recovery_pointer(root, pointer)
    actuals = pointer.get("actuals", [])
    return PromoGenerationMigrationResult(
        status="already_v2",
        previous_generation_id=generation_id,
        generation_id=generation_id,
        source_count=len(actuals) if isinstance(actuals, list) else 0,
        promotion_count=0,
        pointer_sha256=pointer_hash,
    )


def _validated_v1_config(
    root: Path,
    pointer: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, str]]:
    config_path = _within_generation_root(root, pointer.get("config_file"))
    config, config_bytes = _read_json(config_path, "Configul generației Promo")
    expected_hash = pointer.get("config_sha256")
    if not isinstance(expected_hash, str) or _sha256(config_bytes) != expected_hash:
        raise PromoGenerationMigrationError(
            "Configul Promo nu corespunde hashului aprobat."
        )
    promotions = config.get("promotions")
    if not isinstance(promotions, list) or not promotions:
        raise PromoGenerationMigrationError(
            "Configul Promo nu conține promoții valide."
        )
    manifest = _source_manifest(pointer)
    try:
        _definitions, material_hash = validate_special_cards_config(config)
    except ValueError as exc:
        raise PromoGenerationMigrationError(
            "Configul Promo v1 nu poate fi materializat."
        ) from exc
    if pointer.get("material_sha256") != material_hash:
        raise PromoGenerationMigrationError(
            "Hashul materializării Promo v1 nu corespunde configului aprobat."
        )
    return config, promotions, manifest


def _promotion_source_metadata(
    promotion: dict[str, Any],
) -> tuple[str, date, str] | None:
    raw_source = promotion.get("actuals_source_file")
    if raw_source is None or raw_source == "":
        return None
    if not isinstance(raw_source, str):
        raise PromoGenerationMigrationError(
            "Configul Promo nu corespunde manifestului surselor."
        )
    cutoff = _parse_cutoff(promotion.get("actuals_cutoff_date"))
    sheet_name = str(
        promotion.get("actuals_sheet") or "AccesoriPromoLunar"
    ).strip()
    if not sheet_name:
        raise PromoGenerationMigrationError(
            "Foaia unei surse Promo este invalidă."
        )
    return raw_source, cutoff, sheet_name


def _verified_source_content(
    raw_source: str,
    cutoff: date,
    manifest: dict[str, str],
) -> tuple[Path, bytes, str, date]:
    if raw_source not in manifest:
        raise PromoGenerationMigrationError(
            "Configul Promo nu corespunde manifestului surselor."
        )
    source_path = resolve_path(raw_source, get_repo_root())
    try:
        content = source_path.read_bytes()
    except OSError as exc:
        raise PromoGenerationMigrationError(
            "O sursă Promo aprobată lipsește."
        ) from exc
    source_hash = _sha256(content)
    if source_hash != manifest[raw_source]:
        raise PromoGenerationMigrationError(
            "O sursă Promo nu corespunde hashului aprobat."
        )
    if source_path.suffix.casefold() not in {".xls", ".xlsx"}:
        raise PromoGenerationMigrationError(
            "Formatul unei surse Promo nu este suportat."
        )
    return source_path, content, source_hash, cutoff


def _collect_promo_sources(
    promotions: list[dict[str, Any]],
    manifest: dict[str, str],
) -> tuple[
    dict[tuple[str, str, str], list[dict[str, Any]]],
    dict[tuple[str, str, str], tuple[Path, bytes, str, date]],
]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    content_by_key: dict[tuple[str, str, str], tuple[Path, bytes, str, date]] = {}
    metadata_by_source: dict[str, tuple[date, str]] = {}
    for promotion in promotions:
        if not isinstance(promotion, dict):
            raise PromoGenerationMigrationError(
                "Configul Promo conține o promoție invalidă."
            )
        metadata = _promotion_source_metadata(promotion)
        if metadata is None:
            continue
        raw_source, cutoff, sheet_name = metadata
        if raw_source not in manifest:
            raise PromoGenerationMigrationError(
                "Configul Promo nu corespunde manifestului surselor."
            )
        source_metadata = (cutoff, sheet_name)
        previous = metadata_by_source.setdefault(raw_source, source_metadata)
        if previous != source_metadata:
            raise PromoGenerationMigrationError(
                "Metadatele unei surse Promo sunt incompatibile."
            )
        key = _source_key(raw_source, cutoff, sheet_name)
        grouped.setdefault(key, []).append(promotion)
        if key not in content_by_key:
            content_by_key[key] = _verified_source_content(
                raw_source,
                cutoff,
                manifest,
            )
    declared = {raw_source for raw_source, _cutoff, _sheet in grouped}
    if declared != set(manifest):
        raise PromoGenerationMigrationError(
            "Manifestul Promo declară surse nefolosite."
        )
    return grouped, content_by_key


def _build_source_plans(
    source_content: dict[
        tuple[str, str, str], tuple[Path, bytes, str, date]
    ],
) -> list[_SourcePlan]:
    plans: list[_SourcePlan] = []
    for index, (key, source_data) in enumerate(sorted(source_content.items()), 1):
        raw_source, cutoff_raw, sheet_name = key
        source_path, content, source_hash, cutoff = source_data
        if cutoff_raw != cutoff.isoformat():
            raise PromoGenerationMigrationError(
                "Metadatele unei surse Promo sunt incompatibile."
            )
        parsed = _parse_source(content, source_path.suffix, sheet_name)
        material = _promo_actuals_material_bytes(
            parsed,
            source_sha256=source_hash,
            import_month=cutoff.strftime("%Y-%m"),
            cutoff_date=cutoff,
        )
        token = hashlib.sha256(
            f"{raw_source}\0{cutoff.isoformat()}\0{source_hash}".encode("utf-8")
        ).hexdigest()[:16]
        plans.append(
            _SourcePlan(
                legacy_path=source_path,
                source_sha256=source_hash,
                cutoff_date=cutoff,
                import_month=cutoff.strftime("%Y-%m"),
                sheet_name=sheet_name,
                content=content,
                material=material,
                source_name=(
                    f"promo_actuals-{index}-{token}{source_path.suffix.casefold()}"
                ),
                material_name=f"promo_actuals-{index}-{token}.json",
            )
        )
    return plans


def _materialized_target_config(
    config: dict[str, Any],
    *,
    target_dir: Path,
    source_plans: list[_SourcePlan],
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]],
    manifest: dict[str, str],
) -> tuple[dict[str, Any], str]:
    config_copy = json.loads(json.dumps(config))
    plan_by_key = {
        _source_key(str(raw_source), source.cutoff_date, source.sheet_name): source
        for source in source_plans
        for raw_source, cutoff, sheet_name in grouped
        if cutoff == source.cutoff_date.isoformat()
        and sheet_name == source.sheet_name
        and source.source_sha256 == manifest[raw_source]
        and resolve_path(raw_source, get_repo_root()) == source.legacy_path
    }
    if len(plan_by_key) != len(grouped):
        raise PromoGenerationMigrationError(
            "Metadatele surselor Promo sunt ambigue."
        )
    for promotion in config_copy["promotions"]:
        metadata = _promotion_source_metadata(promotion)
        if metadata is None:
            continue
        raw_source, cutoff, sheet_name = metadata
        source = plan_by_key[_source_key(raw_source, cutoff, sheet_name)]
        promotion["actuals_source_file"] = str(target_dir / source.source_name)
        promotion["actuals_source_sha256"] = source.source_sha256
        promotion["actuals_material_file"] = str(target_dir / source.material_name)
        promotion["actuals_material_sha256"] = _sha256(source.material)
    try:
        _definitions, material_hash = validate_special_cards_config(config_copy)
    except ValueError as exc:
        raise PromoGenerationMigrationError(
            "Configul Promo materializat este invalid."
        ) from exc
    return config_copy, material_hash


def _build_plan(data_dir: Path) -> _MigrationPlan | PromoGenerationMigrationResult:
    data_dir = data_dir.resolve()
    root = data_dir / "promo_generations"
    pointer_path = root / "current.json"
    if not pointer_path.is_file():
        raise PromoGenerationMigrationError("Pointerul Promo activ lipsește.")
    pointer, pointer_bytes = _read_json(pointer_path, "Pointerul Promo activ")
    pointer_hash = _sha256(pointer_bytes)
    generation_id = _valid_generation_id(pointer.get("generation_id"))
    version = pointer.get("version")
    if version == 2:
        return _already_v2_result(
            data_dir,
            root,
            pointer,
            generation_id=generation_id,
            pointer_hash=pointer_hash,
        )
    if version != 1:
        raise PromoGenerationMigrationError(
            "Versiunea pointerului Promo nu este suportată."
        )
    config, promotions, manifest = _validated_v1_config(root, pointer)
    grouped, source_content = _collect_promo_sources(promotions, manifest)
    source_plans = _build_source_plans(source_content)
    target_generation_id = _target_generation_id(pointer_bytes, source_plans)
    target_dir = root / target_generation_id
    target_config, material_hash = _materialized_target_config(
        config,
        target_dir=target_dir,
        source_plans=source_plans,
        grouped=grouped,
        manifest=manifest,
    )
    return _MigrationPlan(
        data_dir=data_dir,
        pointer_path=pointer_path,
        expected_pointer=pointer_bytes,
        previous_generation_id=generation_id,
        generation_id=target_generation_id,
        config=target_config,
        sources=tuple(source_plans),
        material_sha256=material_hash,
    )

def _verify_existing_target(target_dir: Path, planned: _MigrationPlan) -> None:
    """Allow a safe retry after an interruption before the pointer switch."""
    expected_config = _canonical_json_bytes(planned.config)
    config_path = target_dir / "hub_specials.json"
    previous_pointer_path = target_dir / "previous-current-v1.json"
    try:
        if config_path.read_bytes() != expected_config:
            raise ValueError
        if previous_pointer_path.read_bytes() != planned.expected_pointer:
            raise ValueError
        for source in planned.sources:
            if (target_dir / source.source_name).read_bytes() != source.content:
                raise ValueError
            if (target_dir / source.material_name).read_bytes() != source.material:
                raise ValueError
    except (OSError, ValueError) as exc:
        raise PromoGenerationMigrationError("Generația Promo țintă existentă nu corespunde planului validat.") from exc
    target_dir.chmod(0o700)
    config_path.chmod(0o600)
    previous_pointer_path.chmod(0o600)
    for source in planned.sources:
        (target_dir / source.source_name).chmod(0o600)
        (target_dir / source.material_name).chmod(0o600)


def migrate_legacy_promo_generation(
    *,
    data_dir: Path,
    apply: bool = False,
) -> PromoGenerationMigrationResult:
    """Validate v1 and, only with ``apply=True``, atomically switch to v2.

    Dry-run still reads, hashes and reparses every approved source.  It never
    creates files or lock directories.  An apply retry is idempotent: after a
    successful switch the current v2 pointer returns ``already_v2``.
    """
    planned = _build_plan(data_dir)
    if isinstance(planned, PromoGenerationMigrationResult):
        return planned
    result = PromoGenerationMigrationResult(
        status="dry_run" if not apply else "migrated",
        previous_generation_id=planned.previous_generation_id,
        generation_id=planned.generation_id,
        source_count=len(planned.sources),
        promotion_count=len(planned.config["promotions"]),
        pointer_sha256=_sha256(planned.expected_pointer),
    )
    if not apply:
        return result

    root = planned.pointer_path.parent
    target_dir = root / planned.generation_id
    lock_path = root / ".promotion.lock"
    staging = root / f".staging-v1-v2-{uuid4()}"
    root.mkdir(parents=True, exist_ok=True, mode=0o770)
    root.chmod(0o770)
    try:
        with lock_path.open("a+b") as lock_file:
            os.fchmod(lock_file.fileno(), 0o660)
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                current_pointer = planned.pointer_path.read_bytes()
            except OSError as exc:
                raise PromoGenerationMigrationConflict("Pointerul Promo activ nu mai poate fi citit.") from exc
            if current_pointer != planned.expected_pointer:
                raise PromoGenerationMigrationConflict("Pointerul Promo s-a schimbat; rulează din nou dry-run.")
            target_exists = target_dir.exists()
            if target_exists:
                _verify_existing_target(target_dir, planned)
            else:
                staging.mkdir(mode=0o770)
                staging.chmod(0o770)
            actuals_manifest: list[dict[str, str]] = []
            materials_manifest: list[dict[str, str]] = []
            for source in planned.sources:
                if not target_exists:
                    target_source = staging / source.source_name
                    target_material = staging / source.material_name
                    _write_durable_private_file(target_source, source.content)
                    _write_durable_private_file(target_material, source.material)
                actuals_manifest.append(
                    {
                        "file": str(target_dir / source.source_name),
                        "sha256": source.source_sha256,
                    }
                )
                materials_manifest.append(
                    {
                        "file": str(target_dir / source.material_name),
                        "sha256": _sha256(source.material),
                    }
                )
            config_bytes = _canonical_json_bytes(planned.config)
            config_sha256 = _sha256(config_bytes)
            if not target_exists:
                _write_durable_private_file(staging / "hub_specials.json", config_bytes)
                _write_durable_private_file(staging / "previous-current-v1.json", planned.expected_pointer)
                _fsync_directory(staging)
                _fsync_directory(root)
                staging.replace(target_dir)
                _fsync_directory(root)

            pointer = {
                "version": 2,
                "generation_id": planned.generation_id,
                "config_file": f"{planned.generation_id}/hub_specials.json",
                "config_sha256": config_sha256,
                "actuals_sha256": _sha256(_canonical_json_bytes({"actuals": actuals_manifest})),
                "actuals": actuals_manifest,
                "actuals_material_sha256": _sha256(_canonical_json_bytes({"materials": materials_manifest})),
                "actuals_materials": materials_manifest,
                "material_sha256": planned.material_sha256,
                "previous_generation_id": planned.previous_generation_id,
                "previous_pointer_file": f"{planned.generation_id}/previous-current-v1.json",
                "previous_pointer_sha256": _sha256(planned.expected_pointer),
                "parser_resources": {
                    "parser": "promo_actuals_v1_migration",
                    "sources": len(planned.sources),
                    "rows": sum(json.loads(source.material)["report_rows"] for source in planned.sources),
                },
                "promoted_at": datetime.now(timezone.utc).isoformat(),
            }
            if planned.pointer_path.read_bytes() != planned.expected_pointer:
                raise PromoGenerationMigrationConflict("Pointerul Promo s-a schimbat; generația v2 nu a fost activată.")
            pointer_tmp = root / f".current-v1-v2-{uuid4()}.tmp"
            _write_durable_private_file(pointer_tmp, _canonical_json_bytes(pointer))
            _fsync_directory(root)
            pointer_tmp.replace(planned.pointer_path)
            _fsync_directory(root)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    return result
