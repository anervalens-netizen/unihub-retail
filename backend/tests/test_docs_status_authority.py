from __future__ import annotations

import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).parents[2] / "scripts/check_docs_status_authority.py"
SPEC = importlib.util.spec_from_file_location("check_docs_status_authority", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
status_authority = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(status_authority)


def valid_catalog() -> dict[str, object]:
    return {
        "version": status_authority.CATALOG_VERSION,
        "status_authority": status_authority.STATUS_AUTHORITY.copy(),
        "entries": [
            {
                "path": "docs/exec-plans/completed/UR-CLOSE-20260812.md",
                "status": "historical",
            },
            {
                "path": "docs/operations/RETAIL_9_5_FINAL_HANDOFF.md",
                "status": "historical",
            },
            {
                "path": "docs/operations/retail-slo-readiness.md",
                "status": "active",
            },
        ],
    }


def write_contract_files(root: Path) -> None:
    for relative in status_authority.HISTORICAL_STATUS_SNAPSHOTS:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            f"> **{status_authority.HISTORICAL_STATUS_MARKER}**\n",
            encoding="utf-8",
        )

    readiness = root / status_authority.READINESS_CONTRACT
    readiness.parent.mkdir(parents=True, exist_ok=True)
    readiness.write_text(
        f"> **{status_authority.READINESS_CONTRACT_MARKER}**\n",
        encoding="utf-8",
    )

    index = root / status_authority.INDEX
    index.parent.mkdir(parents=True, exist_ok=True)
    index.write_text(
        "catalog.json entries[].status /readyz Prometheus RELEASE_MANIFEST.json Issue #159\n",
        encoding="utf-8",
    )


def test_valid_status_authority_passes(tmp_path: Path) -> None:
    write_contract_files(tmp_path)
    assert status_authority.status_authority_errors(tmp_path, valid_catalog()) == []


def test_missing_or_changed_authority_contract_fails(tmp_path: Path) -> None:
    write_contract_files(tmp_path)
    catalog = valid_catalog()
    catalog.pop("status_authority")
    errors = status_authority.status_authority_errors(tmp_path, catalog)
    assert "status_authority contract is missing or invalid" in errors[0]


def test_exec_plan_path_and_catalog_state_must_agree(tmp_path: Path) -> None:
    write_contract_files(tmp_path)
    catalog = valid_catalog()
    entries = catalog["entries"]
    assert isinstance(entries, list)
    entries.append({"path": "docs/exec-plans/active/example.md", "status": "historical"})
    entries.append({"path": "docs/exec-plans/completed/example.md", "status": "active"})
    errors = status_authority.status_authority_errors(tmp_path, catalog)
    assert any("active exec-plan path must have status=active" in error for error in errors)
    assert any("completed exec-plan path must be historical/superseded" in error for error in errors)


def test_historical_status_snapshot_cannot_be_active(tmp_path: Path) -> None:
    write_contract_files(tmp_path)
    catalog = valid_catalog()
    entries = catalog["entries"]
    assert isinstance(entries, list)
    entries[0]["status"] = "active"
    errors = status_authority.status_authority_errors(tmp_path, catalog)
    assert any("status snapshot must not be active" in error for error in errors)


def test_historical_snapshot_requires_explicit_marker(tmp_path: Path) -> None:
    write_contract_files(tmp_path)
    path = tmp_path / status_authority.HISTORICAL_STATUS_SNAPSHOTS[0]
    path.write_text("# stale status\nStatus: DONE\n", encoding="utf-8")
    errors = status_authority.status_authority_errors(tmp_path, valid_catalog())
    assert any("historical status marker is missing" in error for error in errors)


def test_readiness_contract_does_not_become_static_health_status(tmp_path: Path) -> None:
    write_contract_files(tmp_path)
    readiness = tmp_path / status_authority.READINESS_CONTRACT
    readiness.write_text("# readiness\n", encoding="utf-8")
    errors = status_authority.status_authority_errors(tmp_path, valid_catalog())
    assert any("live-health boundary marker is missing" in error for error in errors)


def test_canonical_index_must_name_all_three_authority_boundaries(tmp_path: Path) -> None:
    write_contract_files(tmp_path)
    index = tmp_path / status_authority.INDEX
    index.write_text("catalog.json entries[].status\n", encoding="utf-8")
    errors = status_authority.status_authority_errors(tmp_path, valid_catalog())
    assert any("/readyz" in error for error in errors)
    assert any("RELEASE_MANIFEST.json" in error for error in errors)
    assert any("Issue #159" in error for error in errors)
