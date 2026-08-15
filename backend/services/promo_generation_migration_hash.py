"""Deterministic identity and validation helpers for Promo generation upgrades."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import hashlib
import json
from pathlib import Path
from typing import Any

from services.dashboard_specials import validate_special_cards_config
from services.product_lists import get_repo_root, resolve_path
from services.promo_generation_publisher import (
    _RuleSource,
    _canonical_json_bytes,
    _collect_rule_sources,
    _materialize_rule_config,
)


class PromoGenerationMigrationError(RuntimeError):
    """A generation cannot be safely converted without operator repair."""


@dataclass(frozen=True, slots=True)
class PromoGenerationMigrationResult:
    status: str
    previous_generation_id: str
    generation_id: str | None
    source_count: int
    promotion_count: int
    pointer_sha256: str


@dataclass(frozen=True, slots=True)
class V2UpgradePlan:
    data_dir: Path
    pointer_path: Path
    expected_pointer: bytes
    pointer: dict[str, Any]
    previous_generation_id: str
    generation_id: str
    config: dict[str, Any]
    rule_sources: tuple[_RuleSource, ...]
    material_sha256: str


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def read_json(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        content = path.read_bytes()
        payload = json.loads(content)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PromoGenerationMigrationError(f"{label} este invalid.") from exc
    if not isinstance(payload, dict):
        raise PromoGenerationMigrationError(f"{label} este invalid.")
    return payload, content


def valid_generation_id(value: object) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 32
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise PromoGenerationMigrationError("ID-ul generației Promo este invalid.")
    return value


def within_generation_root(root: Path, relative: object) -> Path:
    if not isinstance(relative, str) or not relative:
        raise PromoGenerationMigrationError("Calea configului generației Promo este invalidă.")
    candidate_relative = Path(relative)
    if candidate_relative.is_absolute() or ".." in candidate_relative.parts:
        raise PromoGenerationMigrationError("Calea configului generației Promo este invalidă.")
    candidate = (root / candidate_relative).resolve()
    if candidate.parent.parent != root.resolve() or not candidate.is_file():
        raise PromoGenerationMigrationError("Configul generației Promo lipsește.")
    return candidate


def verify_recovery_pointer(root: Path, pointer: dict[str, Any]) -> None:
    raw_file = pointer.get("previous_pointer_file")
    expected_sha256 = pointer.get("previous_pointer_sha256")
    if raw_file is None and expected_sha256 is None:
        return
    if not isinstance(raw_file, str) or not isinstance(expected_sha256, str) or len(expected_sha256) != 64:
        raise PromoGenerationMigrationError("Evidence-ul pointerului Promo precedent este invalid.")
    path = within_generation_root(root, raw_file)
    if sha256_bytes(path.read_bytes()) != expected_sha256:
        raise PromoGenerationMigrationError("Evidence-ul pointerului Promo precedent nu corespunde hashului.")


def pointer_manifest(
    pointer: dict[str, Any],
    key: str,
    *,
    required: bool,
) -> list[dict[str, str]]:
    raw_manifest = pointer.get(key)
    if not isinstance(raw_manifest, list) or (required and not raw_manifest):
        raise PromoGenerationMigrationError("Manifestul surselor Promo este invalid.")
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for entry in raw_manifest:
        if not isinstance(entry, dict):
            raise PromoGenerationMigrationError("Manifestul surselor Promo este invalid.")
        raw_path, digest = entry.get("file"), entry.get("sha256")
        if (
            not isinstance(raw_path, str)
            or not raw_path
            or not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
            or raw_path in seen
        ):
            raise PromoGenerationMigrationError("Manifestul surselor Promo este invalid.")
        seen.add(raw_path)
        result.append({"file": raw_path, "sha256": digest})
    return result


def source_manifest(pointer: dict[str, Any]) -> dict[str, str]:
    return {
        entry["file"]: entry["sha256"]
        for entry in pointer_manifest(pointer, "actuals", required=True)
    }


def parse_cutoff(value: object) -> date:
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise PromoGenerationMigrationError("Cutoff-ul unei surse Promo este invalid.") from exc


def source_key(raw_path: str, cutoff: date, sheet_name: str) -> tuple[str, str, str]:
    return raw_path, cutoff.isoformat(), sheet_name


def target_generation_id(
    pointer_bytes: bytes,
    source_plans: list[Any],
    rule_sources: list[Any],
) -> str:
    seed = hashlib.sha256(
        pointer_bytes
        + b"\0promo-v1-to-v2\0"
        + b"".join(
            source.source_sha256.encode("ascii")
            + hashlib.sha256(source.material).hexdigest().encode("ascii")
            for source in source_plans
        )
        + b"\0promo-rule-sources\0"
        + b"".join(source.sha256.encode("ascii") for source in rule_sources)
    ).hexdigest()
    return seed[:32]


def verify_existing_v1_target(target_dir: Path, planned: Any) -> None:
    """Allow a safe retry after an interruption before the pointer switch."""
    config_path = target_dir / "hub_specials.json"
    previous_pointer_path = target_dir / "previous-current-v1.json"
    try:
        if config_path.read_bytes() != _canonical_json_bytes(planned.config):
            raise ValueError
        if previous_pointer_path.read_bytes() != planned.expected_pointer:
            raise ValueError
        for source in planned.sources:
            if (target_dir / source.source_name).read_bytes() != source.content:
                raise ValueError
            if (target_dir / source.material_name).read_bytes() != source.material:
                raise ValueError
        for source in planned.rule_sources:
            if (target_dir / source.name).read_bytes() != source.content:
                raise ValueError
    except (OSError, ValueError) as exc:
        raise PromoGenerationMigrationError(
            "Generația Promo țintă existentă nu corespunde planului validat."
        ) from exc
    target_dir.chmod(0o700)
    config_path.chmod(0o600)
    previous_pointer_path.chmod(0o600)
    for source in planned.sources:
        (target_dir / source.source_name).chmod(0o600)
        (target_dir / source.material_name).chmod(0o600)
    for source in planned.rule_sources:
        (target_dir / source.name).chmod(0o600)


def v2_upgrade_generation_id(pointer_bytes: bytes, rule_sources: list[Any]) -> str:
    seed = hashlib.sha256(
        pointer_bytes
        + b"\0promo-v2-owned-rules\0"
        + b"".join(
            source.sha256.encode("ascii")
            + hashlib.sha256(source.content).hexdigest().encode("ascii")
            for source in rule_sources
        )
    ).hexdigest()
    return seed[:32]


def _verify_v2_manifest_files(manifest: list[dict[str, str]]) -> None:
    for entry in manifest:
        unresolved = Path(entry["file"])
        path = resolve_path(entry["file"], get_repo_root())
        try:
            content = path.read_bytes()
        except OSError as exc:
            raise PromoGenerationMigrationError("O sursă Promo v2 aprobată lipsește.") from exc
        if unresolved.is_symlink() or path.is_symlink() or sha256_bytes(content) != entry["sha256"]:
            raise PromoGenerationMigrationError("O sursă Promo v2 nu corespunde hashului aprobat.")


def _declared_paths(config: dict[str, Any], key: str) -> set[str]:
    return {
        str(promotion[key])
        for promotion in config.get("promotions", [])
        if isinstance(promotion, dict) and promotion.get(key)
    }


def build_v2_upgrade_plan(
    data_dir: Path,
    root: Path,
    pointer: dict[str, Any],
    pointer_bytes: bytes,
    generation_id: str,
) -> V2UpgradePlan:
    if "rule_sources" in pointer or "rule_sources_sha256" in pointer:
        raise PromoGenerationMigrationError("Generația Promo v2 activă este invalidă.")
    config_path = within_generation_root(root, pointer.get("config_file"))
    config, config_bytes = read_json(config_path, "Configul generației Promo")
    if sha256_bytes(config_bytes) != pointer.get("config_sha256"):
        raise PromoGenerationMigrationError("Configul Promo v2 nu corespunde hashului.")
    actuals = pointer_manifest(pointer, "actuals", required=True)
    materials = pointer_manifest(pointer, "actuals_materials", required=False)
    if (
        {entry["file"] for entry in actuals} != _declared_paths(config, "actuals_source_file")
        or {entry["file"] for entry in materials}
        != _declared_paths(config, "actuals_material_file")
    ):
        raise PromoGenerationMigrationError("Manifestul Promo v2 este inconsistent.")
    _verify_v2_manifest_files(actuals)
    _verify_v2_manifest_files(materials)
    try:
        _definitions, material_hash = validate_special_cards_config(config)
        rule_sources = _collect_rule_sources(config)
    except ValueError as exc:
        raise PromoGenerationMigrationError("Masterele Promo v2 nu pot fi deținute de generație.") from exc
    if pointer.get("material_sha256") != material_hash:
        raise PromoGenerationMigrationError("Materializarea Promo v2 este invalidă.")
    target_id = v2_upgrade_generation_id(pointer_bytes, list(rule_sources))
    return V2UpgradePlan(
        data_dir=data_dir,
        pointer_path=root / "current.json",
        expected_pointer=pointer_bytes,
        pointer=pointer,
        previous_generation_id=generation_id,
        generation_id=target_id,
        config=_materialize_rule_config(config, root / target_id, rule_sources),
        rule_sources=rule_sources,
        material_sha256=material_hash,
    )


def already_v2_result(
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
        raise PromoGenerationMigrationError("Generația Promo v2 activă este invalidă.") from exc
    verify_recovery_pointer(root, pointer)
    actuals = pointer.get("actuals", [])
    return PromoGenerationMigrationResult(
        status="already_v2",
        previous_generation_id=generation_id,
        generation_id=generation_id,
        source_count=len(actuals) if isinstance(actuals, list) else 0,
        promotion_count=0,
        pointer_sha256=pointer_hash,
    )
