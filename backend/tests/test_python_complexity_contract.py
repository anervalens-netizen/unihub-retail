from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "python_complexity_contract",
    ROOT / "scripts/check_python_complexity_contract.py",
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)
canonical_sha256 = MODULE.canonical_sha256
evaluate = MODULE.evaluate


def _contract(entries: list[dict] | None = None) -> dict:
    contract = {
        "version": 1,
        "algorithm": {},
        "baseline": {},
        "release_b_gates": {
            "complexity_proxy_gte_20_maximum": 54,
            "complexity_proxy_gte_30_maximum": 0,
            "maximum_complexity_proxy": 29,
            "new_function_complexity_proxy_maximum": 19,
            "wp11_locked_entries_maximum": 19,
        },
        "entries": entries or [],
    }
    contract["contract_payload_sha256"] = canonical_sha256(contract)
    return contract


def _source_root(tmp_path: Path, *, hotspot: bool) -> Path:
    backend = tmp_path / "backend"
    backend.mkdir()
    body = ["def calculate(value):"]
    if hotspot:
        body.extend("    if value:\n        value += 1" for _ in range(19))
    body.append("    return value")
    (backend / "sample.py").write_text("\n".join(body) + "\n", encoding="utf-8")
    return tmp_path


def test_python_complexity_contract_accepts_small_functions(tmp_path: Path) -> None:
    evidence = evaluate(_source_root(tmp_path, hotspot=False), _contract())

    assert evidence["result"] == "PASS"
    assert evidence["metrics"]["new_function_gte_20"] == 0


def test_python_complexity_contract_rejects_new_hotspot(tmp_path: Path) -> None:
    evidence = evaluate(_source_root(tmp_path, hotspot=True), _contract())

    assert evidence["result"] == "FAIL"
    assert evidence["metrics"]["new_function_gte_20"] == 1
    assert any("new function" in item for item in evidence["violations"])


def test_python_complexity_contract_enforces_wp11_identity(tmp_path: Path) -> None:
    entry = {
        "path": "backend/sample.py",
        "function": "calculate",
        "wp11_mandatory_below_20": True,
        "mandatory_below_30": False,
    }
    evidence = evaluate(_source_root(tmp_path, hotspot=True), _contract([entry]))

    assert evidence["result"] == "FAIL"
    assert evidence["metrics"]["wp11_locked_gte_20"] == 1
    assert any("WP-11 entry" in item for item in evidence["violations"])


def test_python_complexity_contract_rejects_payload_tampering(tmp_path: Path) -> None:
    contract = _contract()
    contract["release_b_gates"]["maximum_complexity_proxy"] = 28

    evidence = evaluate(_source_root(tmp_path, hotspot=False), contract)

    assert evidence["result"] == "FAIL"
    assert evidence["violations"] == ["contract payload digest mismatch"]
