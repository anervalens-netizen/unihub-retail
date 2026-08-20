"""Tests for the monotonic direct-DB architecture exception ratchet."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
CHECK_PATH = REPO_ROOT / "scripts" / "check_backend_architecture.py"
CONTRACT_PATH = REPO_ROOT / "backend" / "architecture_contract.json"
BASELINE_PATH = REPO_ROOT / "backend" / "architecture_direct_db_baseline_v1.json"


def _load_check_module():
    spec = importlib.util.spec_from_file_location("_architecture_check", str(CHECK_PATH))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def check():
    return _load_check_module()


@pytest.fixture(scope="module")
def contract():
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def baseline():
    return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))


def test_real_contract_matches_pinned_direct_db_baseline(check, contract, baseline):
    digest = hashlib.sha256(BASELINE_PATH.read_bytes()).hexdigest()
    assert digest == check.DIRECT_DB_BASELINE_SHA256

    result = check.evaluate_data_access_ratchet(contract, baseline)
    assert result["violations"] == []
    assert len(result["baseline_modules"]) == 55
    assert len(result["current_modules"]) == 55
    assert result["retired_modules"] == []


def test_new_exception_is_rejected(check, contract, baseline):
    mutated = copy.deepcopy(contract)
    mutated["service_data_access"]["query_services"].append("services.new_direct_db")

    result = check.evaluate_data_access_ratchet(mutated, baseline)

    assert result["violations"] == [
        "new direct DB architecture exception is not in pinned baseline: services.new_direct_db"
    ]


def test_same_count_cosmetic_swap_is_rejected(check, contract, baseline):
    mutated = copy.deepcopy(contract)
    query_services = mutated["service_data_access"]["query_services"]
    query_services.remove("services.agents")
    query_services.append("services.new_direct_db")

    result = check.evaluate_data_access_ratchet(mutated, baseline)

    assert len(result["current_modules"]) == len(result["baseline_modules"]) == 55
    assert result["retired_modules"] == ["services.agents"]
    assert result["violations"] == [
        "new direct DB architecture exception is not in pinned baseline: services.new_direct_db"
    ]


def test_category_shuffle_is_rejected(check, contract, baseline):
    mutated = copy.deepcopy(contract)
    mutated["service_data_access"]["query_services"].remove("services.agents")
    mutated["service_data_access"]["transaction_scripts"].append("services.agents")

    result = check.evaluate_data_access_ratchet(mutated, baseline)

    assert result["violations"] == [
        "direct DB architecture exception category changed for services.agents: "
        "query_services -> transaction_scripts"
    ]


def test_retiring_existing_exception_is_allowed_by_ratchet(check, contract, baseline):
    mutated = copy.deepcopy(contract)
    mutated["service_data_access"]["query_services"].remove("services.agents")

    result = check.evaluate_data_access_ratchet(
        mutated,
        baseline,
        previous_contract=contract,
    )

    assert result["violations"] == []
    assert len(result["current_modules"]) == 54
    assert result["retired_modules"] == ["services.agents"]
    assert result["retired_since_previous"] == ["services.agents"]


def test_retired_exception_cannot_be_readded_on_later_commit(check, contract, baseline):
    retired = copy.deepcopy(contract)
    retired["service_data_access"]["query_services"].remove("services.agents")

    readded = copy.deepcopy(retired)
    readded["service_data_access"]["query_services"].append("services.agents")

    result = check.evaluate_data_access_ratchet(
        readded,
        baseline,
        previous_contract=retired,
    )

    assert result["violations"] == [
        "direct DB architecture exception added since previous contract: services.agents"
    ]


@pytest.mark.parametrize(
    ("mutator", "expected_fragment"),
    [
        (
            lambda raw: raw["service_data_access"].update({"other": []}),
            "current architecture contract has unknown data-access categories: other",
        ),
        (
            lambda raw: raw["service_data_access"]["query_services"].append("services.agents"),
            "current architecture contract category query_services contains duplicate module entries",
        ),
    ],
)
def test_contract_structure_fails_closed(check, contract, baseline, mutator, expected_fragment):
    mutated = copy.deepcopy(contract)
    mutator(mutated)

    result = check.evaluate_data_access_ratchet(mutated, baseline)

    assert expected_fragment in result["violations"]
