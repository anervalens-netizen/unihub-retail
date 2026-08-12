from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
from uuid import uuid4

from services.product_lists import get_repo_root, resolve_path


class PromoGenerationConflictError(RuntimeError):
    """Raised when another writer moves the promo pointer during validation."""


class PromoGenerationPointerIntegrityError(PromoGenerationConflictError):
    """Raised when the current promo pointer cannot preserve rollback lineage."""


@dataclass(frozen=True, slots=True)
class _GenerationFiles:
    generation_root: Path
    generation_id: str
    generation_dir: Path
    actual_name: str
    material_name: str
    config_name: str
    actual_path: Path
    material_path: Path
    config_bytes: bytes
    config_sha256: str
    source_sha256: str
    material_sha256: str
    actuals_material_sha256: str
    actuals_manifest: list[dict[str, str]]
    materials_manifest: list[dict[str, str]]


def _canonical_json_bytes(payload: dict) -> bytes:
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_durable_private_file(path: Path, content: bytes) -> None:
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
        0o660,
    )
    try:
        view = memoryview(content)
        while view:
            written = os.write(descriptor, view)
            view = view[written:]
        os.fchmod(descriptor, 0o660)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _promo_pointer_sha256(data_dir: Path) -> str | None:
    pointer_path = data_dir / "promo_generations" / "current.json"
    return (
        hashlib.sha256(pointer_path.read_bytes()).hexdigest()
        if pointer_path.exists()
        else None
    )


def _previous_promo_generation_id(pointer_path: Path) -> str | None:
    if not pointer_path.exists():
        return None
    try:
        pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PromoGenerationPointerIntegrityError(
            "Pointerul promo activ este invalid"
        ) from exc
    if not isinstance(pointer, dict):
        raise PromoGenerationPointerIntegrityError(
            "Pointerul promo activ este invalid"
        )
    generation_id = pointer.get("generation_id")
    if (
        not isinstance(generation_id, str)
        or len(generation_id) != 32
        or any(
            character not in "0123456789abcdef"
            for character in generation_id
        )
    ):
        raise PromoGenerationPointerIntegrityError(
            "Pointerul promo activ este invalid"
        )
    return generation_id


def _canonical_promo_actuals_material(
    actuals_material: bytes | None,
    source_sha256: str,
) -> bytes:
    if actuals_material is not None:
        return actuals_material
    return _canonical_json_bytes(
        {
            "version": 1,
            "source_sha256": source_sha256,
            "import_month": "",
            "cutoff_date": "",
            "report_rows": 0,
            "promo_units": 0,
            "rows": [],
        }
    )


def _source_manifest(
    config: dict,
    *,
    key: str,
    final_path: Path,
    final_sha256: str,
    missing_message: str,
) -> list[dict[str, str]]:
    manifest: list[dict[str, str]] = []
    source_files = sorted(
        {
            str(promotion[key])
            for promotion in config["promotions"]
            if promotion.get(key)
        }
    )
    for source_file in source_files:
        path = resolve_path(source_file, get_repo_root())
        if path == final_path:
            digest = final_sha256
        elif path.is_file():
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        else:
            raise ValueError(missing_message)
        manifest.append({"file": source_file, "sha256": digest})
    return manifest


def _prepare_generation_files(
    *,
    data_dir: Path,
    config: dict,
    content: bytes,
    suffix: str,
    material_sha256: str,
    actuals_material: bytes,
) -> _GenerationFiles:
    generation_root = data_dir / "promo_generations"
    source_sha256 = hashlib.sha256(content).hexdigest()
    actuals_material_sha256 = hashlib.sha256(actuals_material).hexdigest()
    seed = hashlib.sha256(
        _canonical_json_bytes(config)
        + source_sha256.encode("ascii")
        + material_sha256.encode("ascii")
        + actuals_material_sha256.encode("ascii")
    ).hexdigest()
    generation_id = seed[:32]
    generation_dir = generation_root / generation_id
    actual_name = f"promo_actuals{suffix}"
    material_name = "promo_actuals.json"
    config_name = "hub_specials.json"
    actual_path = generation_dir / actual_name
    material_path = generation_dir / material_name
    for promotion in config["promotions"]:
        if promotion.get("actuals_source_file") == "@GENERATION_ACTUALS@":
            promotion["actuals_source_file"] = str(actual_path)
            promotion["actuals_source_sha256"] = source_sha256
            promotion["actuals_material_file"] = str(material_path)
            promotion["actuals_material_sha256"] = actuals_material_sha256
    config_bytes = _canonical_json_bytes(config)
    config_sha256 = hashlib.sha256(config_bytes).hexdigest()
    return _GenerationFiles(
        generation_root=generation_root,
        generation_id=generation_id,
        generation_dir=generation_dir,
        actual_name=actual_name,
        material_name=material_name,
        config_name=config_name,
        actual_path=actual_path,
        material_path=material_path,
        config_bytes=config_bytes,
        config_sha256=config_sha256,
        source_sha256=source_sha256,
        material_sha256=material_sha256,
        actuals_material_sha256=actuals_material_sha256,
        actuals_manifest=_source_manifest(
            config,
            key="actuals_source_file",
            final_path=actual_path,
            final_sha256=source_sha256,
            missing_message="Sursa actuals promo lipsește",
        ),
        materials_manifest=_source_manifest(
            config,
            key="actuals_material_file",
            final_path=material_path,
            final_sha256=actuals_material_sha256,
            missing_message="Materializarea actuals promo lipsește",
        ),
    )


def _verify_existing_generation(files: _GenerationFiles) -> None:
    config_path = files.generation_dir / files.config_name
    expected = (
        (files.actual_path, files.source_sha256),
        (files.material_path, files.actuals_material_sha256),
        (config_path, files.config_sha256),
    )
    if any(
        not path.is_file()
        or hashlib.sha256(path.read_bytes()).hexdigest() != digest
        for path, digest in expected
    ):
        raise RuntimeError("Coliziune de generație promo")
    for path, _ in expected:
        path.chmod(0o660)


def _write_generation(
    files: _GenerationFiles,
    staging: Path,
    *,
    content: bytes,
    actuals_material: bytes,
) -> None:
    staging.mkdir(mode=0o770)
    _write_durable_private_file(
        staging / files.actual_name,
        content,
    )
    _write_durable_private_file(
        staging / files.material_name,
        actuals_material,
    )
    _write_durable_private_file(
        staging / files.config_name,
        files.config_bytes,
    )
    _fsync_directory(staging)
    _fsync_directory(files.generation_root)
    staging.replace(files.generation_dir)
    _fsync_directory(files.generation_root)


def _pointer_hashes(files: _GenerationFiles) -> dict:
    return {
        "version": 2,
        "generation_id": files.generation_id,
        "config_file": (
            f"{files.generation_id}/{files.config_name}"
        ),
        "config_sha256": files.config_sha256,
        "actuals_sha256": files.source_sha256,
        "actuals": files.actuals_manifest,
        "actuals_material_sha256": files.actuals_material_sha256,
        "actuals_materials": files.materials_manifest,
        "material_sha256": files.material_sha256,
    }


def _validate_exact_retry(
    current_pointer: object,
    *,
    files: _GenerationFiles,
    expected_hashes: dict,
) -> bool:
    if not (
        isinstance(current_pointer, dict)
        and current_pointer.get("generation_id") == files.generation_id
    ):
        return False
    inconsistent = any(
        current_pointer.get(key) != value
        for key, value in expected_hashes.items()
    )
    if (
        inconsistent
        or current_pointer.get("previous_generation_id")
        == files.generation_id
    ):
        raise PromoGenerationPointerIntegrityError(
            "Pointerul generației promo identice este inconsistent"
        )
    return True


def _publish_locked(
    files: _GenerationFiles,
    *,
    staging: Path,
    content: bytes,
    actuals_material: bytes,
    parser_resources: dict[str, int | float | str | None],
    expected_pointer_sha256: str | None,
) -> tuple[str, str, str]:
    pointer_path = files.generation_root / "current.json"
    pointer_bytes = (
        pointer_path.read_bytes() if pointer_path.exists() else None
    )
    if pointer_bytes is not None:
        pointer_path.chmod(0o660)
    current_hash = (
        hashlib.sha256(pointer_bytes).hexdigest()
        if pointer_bytes is not None
        else None
    )
    if current_hash != expected_pointer_sha256:
        raise PromoGenerationConflictError(
            "Pointerul promo a fost schimbat de alt worker"
        )
    previous_generation_id = _previous_promo_generation_id(pointer_path)
    current_pointer = (
        json.loads(pointer_bytes) if pointer_bytes is not None else None
    )
    if files.generation_dir.exists():
        _verify_existing_generation(files)
    else:
        _write_generation(
            files,
            staging,
            content=content,
            actuals_material=actuals_material,
        )
    hashes = _pointer_hashes(files)
    if _validate_exact_retry(
        current_pointer,
        files=files,
        expected_hashes=hashes,
    ):
        return (
            files.generation_id,
            files.config_sha256,
            files.source_sha256,
        )
    pointer = {
        **hashes,
        "previous_generation_id": previous_generation_id,
        "parser_resources": parser_resources,
        "promoted_at": datetime.now(timezone.utc).isoformat(),
    }
    pointer_tmp = files.generation_root / f".current-{uuid4()}.tmp"
    _write_durable_private_file(
        pointer_tmp,
        _canonical_json_bytes(pointer),
    )
    _fsync_directory(files.generation_root)
    pointer_tmp.replace(pointer_path)
    _fsync_directory(files.generation_root)
    return (
        files.generation_id,
        files.config_sha256,
        files.source_sha256,
    )


def _publish_promo_generation(
    *,
    data_dir: Path,
    config: dict,
    content: bytes,
    suffix: str,
    material_sha256: str,
    actuals_material: bytes | None = None,
    parser_resources: dict[str, int | float | str | None] | None = None,
    expected_pointer_sha256: str | None = None,
) -> tuple[str, str, str]:
    source_sha256 = hashlib.sha256(content).hexdigest()
    material = _canonical_promo_actuals_material(
        actuals_material,
        source_sha256,
    )
    resources = dict(parser_resources or {})
    files = _prepare_generation_files(
        data_dir=data_dir,
        config=config,
        content=content,
        suffix=suffix,
        material_sha256=material_sha256,
        actuals_material=material,
    )
    files.generation_root.mkdir(parents=True, exist_ok=True, mode=0o770)
    staging = files.generation_root / f".staging-{uuid4()}"
    lock_path = files.generation_root / ".promotion.lock"
    try:
        with lock_path.open("a+b") as lock_file:
            os.fchmod(lock_file.fileno(), 0o660)
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            return _publish_locked(
                files,
                staging=staging,
                content=content,
                actuals_material=material,
                parser_resources=resources,
                expected_pointer_sha256=expected_pointer_sha256,
            )
    finally:
        if staging.exists():
            shutil.rmtree(staging)

