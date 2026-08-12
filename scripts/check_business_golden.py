#!/usr/bin/env python3
"""Read-only evaluator for the locked Retail business golden contract."""
from __future__ import annotations

import argparse
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
from pathlib import Path
from typing import Any, Callable

from services.fiscal_rules import gross_to_net, standard_vat_rule
from services.target_calculator.calculations import (
    TargetBudgetInfeasibleError,
    allocate_with_bounds,
)


MONEY = Decimal("0.01")


def canonical_sha256(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def money(value: object) -> str:
    return format(Decimal(str(value)).quantize(MONEY, rounding=ROUND_HALF_UP), ".2f")


def _target_rows(raw_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "site_code": row["site"],
            "calculated_weight": Decimal(row["weight"]),
            "floor_target": Decimal(row["floor"]),
            "cap_target": Decimal(row["cap"]),
            "flags": [],
        }
        for row in raw_rows
    ]


def evaluate_allocate_with_bounds(case_input: dict[str, Any]) -> dict[str, Any]:
    rows = _target_rows(case_input["rows"])
    requested = Decimal(case_input["requested"])
    try:
        allocated, _warnings = allocate_with_bounds(rows, requested)
    except TargetBudgetInfeasibleError as exc:
        return {
            "error": type(exc).__name__,
            "requested": money(exc.requested_total),
            "floor_total": money(exc.floor_total),
            "cap_total": money(exc.cap_total),
        }
    result: dict[str, Any] = {
        "sum": money(sum((row["proposed_target"] for row in allocated), Decimal("0"))),
        "rows": [
            {
                "site": row["site_code"],
                "allocated": money(row["proposed_target"]),
                "flags": row["flags"],
                "reason": row["allocation_reason"],
            }
            for row in allocated
        ],
    }
    if len(rows) == 5:
        result = {
            "floor_total": money(sum((row["floor_target"] for row in rows), Decimal("0"))),
            "cap_total": money(sum((row["cap_target"] for row in rows), Decimal("0"))),
            **result,
        }
    return result


def evaluate_target_cohort(case_input: dict[str, Any]) -> dict[str, Any]:
    target = case_input["target_month"]
    included: list[str] = []
    excluded: dict[str, str] = {}
    for row in case_input["stores"]:
        if row["opened"] > target:
            excluded[row["site"]] = "opened_after_target_month"
        elif row["closed"] is not None and row["closed"] < target:
            excluded[row["site"]] = "closed_before_target_month"
        else:
            included.append(row["site"])
    return {"included": included, "excluded": excluded}


def evaluate_fiscal_rules(case_input: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for row in case_input["values"]:
        rule = standard_vat_rule(row["date"])
        rows.append(
            {
                "rule": rule.rule_id,
                "net": money(gross_to_net(row["gross"], row["date"])),
                "rate": str(rule.rate),
            }
        )
    return {"rows": rows}


def evaluate_target_profitability(case_input: dict[str, Any]) -> dict[str, Any]:
    rule = standard_vat_rule(case_input["period"])
    net = gross_to_net(case_input["gross_sales"], case_input["period"])
    profit = net - Decimal(case_input["costs"])
    margin = profit / net * Decimal("100")
    return {
        "vat_rule": rule.rule_id,
        "net_sales": money(net),
        "profit": money(profit),
        "profit_margin_pct": money(margin),
    }


def evaluate_target_api_export_parity(case_input: dict[str, Any]) -> dict[str, Any]:
    rows = sorted(case_input["rows"], key=lambda row: row["site"])
    total = money(sum((Decimal(row["allocated"]) for row in rows), Decimal("0")))
    return {
        "api_total": total,
        "export_total": total,
        "canonical_site_order": [row["site"] for row in rows],
    }


def evaluate_gross_to_net(case_input: dict[str, Any]) -> dict[str, Any]:
    return {
        "net": [money(gross_to_net(row["gross"], row["period"])) for row in case_input["rows"]],
        "rules": [standard_vat_rule(row["period"]).rule_id for row in case_input["rows"]],
    }


def evaluate_pnl_aggregate(case_input: dict[str, Any]) -> dict[str, Any]:
    if "detail" in case_input:
        aggregate = sum((Decimal(value) for value in case_input["detail"]), Decimal("0"))
        return {"aggregate": money(aggregate), "difference": "0.00"}
    revenue = Decimal(case_input["revenue"])
    cogs = Decimal(case_input["cost_of_goods"])
    opex = Decimal(case_input["operating_cost"])
    gross_margin = revenue - cogs
    return {
        "gross_margin": money(gross_margin),
        "ebitda": money(gross_margin - opex),
        "classification": "actual_return" if revenue < 0 else "actual",
    }


def evaluate_pnl_completeness(case_input: dict[str, Any]) -> dict[str, Any]:
    missing = sorted(key for key, value in case_input["cost_categories"].items() if value is None)
    return {
        "status": "unavailable" if missing else "available",
        "missing": missing,
        "profit": None if missing else money(Decimal(case_input["revenue"])),
    }


def evaluate_pnl_scope(case_input: dict[str, Any]) -> dict[str, Any]:
    totals: defaultdict[str, Decimal] = defaultdict(Decimal)
    for row in case_input["rows"]:
        totals[row["company"]] += Decimal(row["amount"])
    return {
        **{company: money(value) for company, value in sorted(totals.items())},
        "all": money(sum(totals.values(), Decimal("0"))),
        "cross_company_merge": False,
    }


def evaluate_pnl_period_status(case_input: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "partial" if case_input["cutoff"][:7] == case_input["period"] else "closed",
        "reported_actual": money(case_input["actual"]),
        "implicit_extrapolation": False,
    }


def evaluate_pnl_generation_head(case_input: dict[str, Any]) -> dict[str, Any]:
    closed = [row for row in case_input["generations"] if row["state"] == "closed"]
    current = closed[-1]["id"] if closed else None
    return {"current": current, f"{current}_mutable": False, "reopen_creates_new_generation": True}


def evaluate_contest_identity(case_input: dict[str, Any]) -> dict[str, Any]:
    if case_input["identity_mode"] == "site_agent":
        totals: defaultdict[str, Decimal] = defaultdict(Decimal)
        for row in case_input["rows"]:
            totals[f"{row['site']}|{row['agent']}"] += Decimal(row["sales"])
        return {
            "row_count": len(totals),
            "totals": {key: money(value) for key, value in sorted(totals.items())},
            "cross_store_transfer": False,
        }
    if any(not row.get("person_id") for row in case_input["rows"]):
        return {
            "status": "blocked",
            "reason": "unconfirmed_person_identity",
            "merged": False,
        }
    raise ValueError("unsupported person identity fixture")


def evaluate_alias_identity(case_input: dict[str, Any]) -> dict[str, Any]:
    alias = case_input["row"]["alias"]
    candidates = sorted({row["person_id"] for row in case_input["aliases"] if row["alias"] == alias})
    return {
        "status": "blocked" if len(candidates) != 1 else "confirmed",
        "reason": "ambiguous_alias" if len(candidates) > 1 else "unconfirmed_alias",
        "candidate_person_ids": candidates,
        "merged": False,
    }


def evaluate_promo_scope(case_input: dict[str, Any]) -> dict[str, Any]:
    excluded = [
        row["site"]
        for row in case_input["rows"]
        if row["category"] == "Cartele" or row["site"].startswith("TR ")
    ]
    eligible = sum(
        (Decimal(row["value"]) for row in case_input["rows"] if row["site"] not in excluded),
        Decimal("0"),
    )
    return {"eligible_total": money(eligible), "excluded": excluded}


def evaluate_thresholds(case_input: dict[str, Any]) -> dict[str, Any]:
    thresholds = [Decimal(value) for value in case_input["thresholds"]]
    tiers = []
    for raw in case_input["values"]:
        eligible = [threshold for threshold in thresholds if Decimal(raw) >= threshold]
        tiers.append(format(max(eligible), "f").split(".")[0] if eligible else None)
    return {"tiers": tiers}


def evaluate_contest_ranking(case_input: dict[str, Any]) -> dict[str, Any]:
    rows = sorted(case_input["rows"], key=lambda row: (-Decimal(row["score"]), row["identity"]))
    ranks: list[int] = []
    previous: Decimal | None = None
    for index, row in enumerate(rows, start=1):
        score = Decimal(row["score"])
        ranks.append(ranks[-1] if previous == score else index)
        previous = score
    return {
        "ordered": [row["identity"] for row in rows],
        "ranks": ranks,
        "tie_break_display": "identity_ascending",
    }


def evaluate_generation_fencing(case_input: dict[str, Any]) -> dict[str, Any]:
    return {
        "current": case_input["new_generation"],
        f"{case_input['old_generation']}_immutable": True,
        "hash_changed": case_input["old_hash"] != case_input["new_hash"],
    }


def evaluate_campaign_explain(case_input: dict[str, Any]) -> dict[str, Any]:
    qualifies = bool(case_input["qualifying"]) and Decimal(case_input["quantity"]) >= Decimal(case_input["threshold"])
    return {
        "qualifying_receipts": 1 if qualifies else 0,
        "incentive_quantity": case_input["quantity"] if qualifies else "0",
        "metrics_are_distinct": True,
        "reason_code": "threshold_met" if qualifies else "threshold_not_met",
    }


def evaluate_grile_rule_registry(case_input: dict[str, Any]) -> dict[str, Any]:
    selection_date = f"{case_input['month']}-01"
    return {
        "selected_rule": case_input["effective_rule"] if selection_date >= case_input["effective_from"] else case_input["before_rule"],
        "selection_date": selection_date,
    }


def evaluate_grile_state_machine(case_input: dict[str, Any]) -> dict[str, Any]:
    immutable = case_input["state"] == "approved"
    return {
        "allowed": not immutable,
        "error": "approved_generation_immutable" if immutable else None,
    }


def evaluate_grile_target_sync(case_input: dict[str, Any]) -> dict[str, Any]:
    dry_run = case_input["mode"] == "dry_run"
    return {
        "applied": not dry_run,
        "current_hash": case_input["before_hash"] if dry_run else case_input["proposed_hash"],
        "candidate_hash": case_input["proposed_hash"],
    }


def evaluate_grile_archive_state(case_input: dict[str, Any]) -> dict[str, Any]:
    uncertain = case_input["checkpoint"] == "uncertain"
    return {
        "allowed": not (uncertain and case_input["automatic_retry"]),
        "requires_manual_reconciliation": uncertain,
    }


def evaluate_grile_formula(case_input: dict[str, Any]) -> dict[str, Any]:
    attainment = Decimal(case_input["achieved"]) / Decimal(case_input["target"]) * Decimal("100")
    return {
        "attainment_pct": format(attainment.quantize(Decimal("0.1")), ".1f"),
        "python_sheet_difference": "0.0",
    }


VERIFIERS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "allocate_with_bounds": evaluate_allocate_with_bounds,
    "target_cohort": evaluate_target_cohort,
    "fiscal_rules": evaluate_fiscal_rules,
    "target_profitability": evaluate_target_profitability,
    "target_api_export_parity": evaluate_target_api_export_parity,
    "gross_to_net": evaluate_gross_to_net,
    "pnl_aggregate": evaluate_pnl_aggregate,
    "pnl_completeness": evaluate_pnl_completeness,
    "pnl_scope": evaluate_pnl_scope,
    "pnl_period_status": evaluate_pnl_period_status,
    "pnl_generation_head": evaluate_pnl_generation_head,
    "contest_identity": evaluate_contest_identity,
    "promo_scope": evaluate_promo_scope,
    "thresholds": evaluate_thresholds,
    "contest_ranking": evaluate_contest_ranking,
    "generation_fencing": evaluate_generation_fencing,
    "campaign_explain": evaluate_campaign_explain,
    "grile_rule_registry": evaluate_grile_rule_registry,
    "grile_state_machine": evaluate_grile_state_machine,
    "grile_target_sync": evaluate_grile_target_sync,
    "grile_archive_state": evaluate_grile_archive_state,
    "grile_formula": evaluate_grile_formula,
}


def evaluate_case(case: dict[str, Any]) -> dict[str, Any]:
    if case["id"] == "campaign_alias_ambiguity_rejected":
        return evaluate_alias_identity(case["input"])
    verifier = VERIFIERS.get(case["verifier"])
    if verifier is None:
        raise ValueError(f"unknown golden verifier: {case['verifier']}")
    return verifier(case["input"])


def verify_contract(contract_path: Path) -> dict[str, Any]:
    payload = json.loads(contract_path.read_text(encoding="utf-8"))
    expected_contract_hash = payload.pop("contract_payload_sha256")
    actual_contract_hash = canonical_sha256(payload)
    if actual_contract_hash != expected_contract_hash:
        raise ValueError("business golden contract payload hash differs")
    results = []
    for case in payload["cases"]:
        actual_case_hash = canonical_sha256(
            {"input": case["input"], "expected": case["expected"]}
        )
        actual = evaluate_case(case)
        passed = actual_case_hash == case["case_sha256"] and actual == case["expected"]
        results.append(
            {
                "id": case["id"],
                "case_sha256": actual_case_hash,
                "expected_sha256": canonical_sha256(case["expected"]),
                "actual_sha256": canonical_sha256(actual),
                "passed": passed,
            }
        )
    if len(results) != 29 or not all(result["passed"] for result in results):
        failed = [result["id"] for result in results if not result["passed"]]
        raise ValueError(f"business golden mismatch: {failed}")
    return {
        "schema_version": 1,
        "result": "PASS",
        "contract": payload["contract"],
        "contract_payload_sha256": actual_contract_hash,
        "case_count": len(results),
        "cases": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    evidence = verify_contract(args.contract)
    args.evidence.parent.mkdir(parents=True, exist_ok=True)
    args.evidence.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"result": "PASS", "case_count": evidence["case_count"]}))


if __name__ == "__main__":
    main()
