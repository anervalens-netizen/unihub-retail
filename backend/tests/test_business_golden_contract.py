"""Production-facing checks for every locked Retail business golden."""
from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.check_business_golden import canonical_sha256, evaluate_case, verify_contract  # noqa: E402


CONTRACT_PATH = ROOT / "docs/contracts/business-golden-v2.json"
CONTRACT = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", CONTRACT["cases"], ids=lambda case: case["id"])
def test_business_golden_case(case: dict) -> None:
    assert canonical_sha256({"input": case["input"], "expected": case["expected"]}) == case[
        "case_sha256"
    ]
    assert evaluate_case(case) == case["expected"]


def test_business_golden_contract_is_complete_and_read_only(tmp_path: Path) -> None:
    before = CONTRACT_PATH.read_bytes()
    evidence = verify_contract(CONTRACT_PATH)
    assert evidence["result"] == "PASS"
    assert evidence["case_count"] == 29
    assert CONTRACT_PATH.read_bytes() == before
