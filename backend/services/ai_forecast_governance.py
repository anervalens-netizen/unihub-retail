"""Deterministic candidate-only governance for AI forecast evidence."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path
import random
from typing import Any, Mapping, Sequence


TAUS = (Decimal("0.10"), Decimal("0.50"), Decimal("0.90"))
TAU_NAMES = ("q10", "q50", "q90")
EXPECTED_QUANTILE_INDEXES = {
    "9": {"q10": 0, "q20": 1, "q50": 4, "q80": 7, "q90": 8},
    "10": {"ignored_point_mean": 0, "q10": 1, "q20": 2, "q50": 5, "q80": 8, "q90": 9},
}


class ForecastGovernanceError(ValueError):
    """Governance evidence is malformed or cannot produce a safe decision."""


@dataclass(frozen=True, slots=True)
class GovernancePair:
    site_code: str
    target_month: str
    firma: str
    regional: str
    actual: Decimal
    candidate_point: Decimal
    candidate_quantiles: tuple[Decimal, Decimal, Decimal]
    baselines: Mapping[str, Decimal]


def _decimal(value: object, *, field: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except Exception as exc:
        raise ForecastGovernanceError(f"{field} must be decimal") from exc
    if not result.is_finite() or result < 0:
        raise ForecastGovernanceError(f"{field} must be finite and nonnegative")
    return result


def _canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def load_governance_fixture(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ForecastGovernanceError("governance fixture is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ForecastGovernanceError("governance fixture must be an object")
    expected_hash = payload.get("contract_payload_sha256")
    hashed_payload = {key: value for key, value in payload.items() if key != "contract_payload_sha256"}
    if not isinstance(expected_hash, str) or _canonical_sha256(hashed_payload) != expected_hash:
        raise ForecastGovernanceError("governance fixture payload hash differs")
    if (
        payload.get("version") != 1
        or payload.get("contract") != "ai-governance-golden-v1"
        or payload.get("response_profile") != "point_quantiles_v1"
        or payload.get("quantile_indexes") != EXPECTED_QUANTILE_INDEXES
    ):
        raise ForecastGovernanceError("governance fixture contract is unsupported")
    return payload


def load_locked_json_contract(
    path: Path,
    *,
    contract: str,
    version: int,
) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ForecastGovernanceError("locked contract is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ForecastGovernanceError("locked contract must be an object")
    expected_hash = payload.get("contract_payload_sha256")
    hashed_payload = {key: value for key, value in payload.items() if key != "contract_payload_sha256"}
    if (
        payload.get("contract") != contract
        or payload.get("version") != version
        or not isinstance(expected_hash, str)
        or _canonical_sha256(hashed_payload) != expected_hash
    ):
        raise ForecastGovernanceError("locked contract identity or payload hash differs")
    return payload


def _selected_quantiles(layout: Sequence[object]) -> tuple[Decimal, Decimal, Decimal]:
    if len(layout) == 9:
        indexes = (0, 4, 8)
    elif len(layout) == 10:
        indexes = (1, 5, 9)
    else:
        raise ForecastGovernanceError("quantile layout must contain exactly 9 or 10 values")
    selected = tuple(
        _decimal(layout[index], field=f"quantile[{index}]")
        for index in indexes
    )
    q10, q50, q90 = selected
    if not q10 <= q50 <= q90:
        raise ForecastGovernanceError("selected quantiles are not monotonic")
    return q10, q50, q90


def expand_governance_pairs(fixture: Mapping[str, Any]) -> tuple[GovernancePair, ...]:
    months = fixture.get("months")
    stores = fixture.get("stores")
    if not isinstance(months, list) or len(months) != 12 or len(set(months)) != len(months):
        raise ForecastGovernanceError("fixture needs 12 unique ordered months")
    if not isinstance(stores, list) or not stores:
        raise ForecastGovernanceError("fixture needs stores")
    pairs: list[GovernancePair] = []
    seen_sites: set[str] = set()
    for store in stores:
        if not isinstance(store, dict):
            raise ForecastGovernanceError("store fixture row must be an object")
        site_code = store.get("site_code")
        if not isinstance(site_code, str) or not site_code or site_code in seen_sites:
            raise ForecastGovernanceError("fixture site codes must be unique")
        seen_sites.add(site_code)
        if store.get("is_operating") is not True or store.get("confidence") != "authoritative":
            raise ForecastGovernanceError("fixture cohort authority is incomplete")
        baselines = store.get("baseline_points")
        if not isinstance(baselines, dict) or not baselines:
            raise ForecastGovernanceError("fixture baselines are missing")
        parsed_baselines = {
            str(name): _decimal(value, field=f"baseline.{name}")
            for name, value in baselines.items()
        }
        quantiles = _selected_quantiles(store.get("candidate_quantile_layout", []))
        for month in months:
            if not isinstance(month, str):
                raise ForecastGovernanceError("fixture months must be strings")
            pairs.append(
                GovernancePair(
                    site_code=site_code,
                    target_month=month,
                    firma=str(store.get("firma", "")),
                    regional=str(store.get("regional", "")),
                    actual=_decimal(store.get("actual"), field="actual"),
                    candidate_point=_decimal(store.get("candidate_point"), field="candidate_point"),
                    candidate_quantiles=quantiles,
                    baselines=parsed_baselines,
                )
            )
    return tuple(pairs)


def _ratio(numerator: Decimal, denominator: Decimal, *, reason: str) -> Decimal:
    if denominator <= 0:
        raise ForecastGovernanceError(reason)
    return numerator / denominator


def _point_metrics(pairs: Sequence[GovernancePair], forecast_name: str) -> dict[str, Decimal]:
    actual = sum((pair.actual for pair in pairs), Decimal("0"))
    forecasts = [
        pair.candidate_point if forecast_name == "candidate" else pair.baselines[forecast_name]
        for pair in pairs
    ]
    forecast = sum(forecasts, Decimal("0"))
    absolute_error = sum(
        (abs(value - pair.actual) for pair, value in zip(pairs, forecasts, strict=True)),
        Decimal("0"),
    )
    return {
        "actual_total": actual,
        "forecast_total": forecast,
        "absolute_error_total": absolute_error,
        "wape": _ratio(absolute_error, actual, reason="zero actual denominator"),
        "bias": _ratio(forecast - actual, actual, reason="zero actual denominator"),
    }


def _pinball(actual: Decimal, forecast: Decimal, tau: Decimal) -> Decimal:
    difference = actual - forecast
    return max(tau * difference, (tau - Decimal("1")) * difference)


def _pinball_metrics(
    pairs: Sequence[GovernancePair],
    forecast_name: str,
) -> dict[str, dict[str, Decimal]]:
    denominator = sum((pair.actual for pair in pairs), Decimal("0"))
    result: dict[str, dict[str, Decimal]] = {}
    for index, (tau, tau_name) in enumerate(zip(TAUS, TAU_NAMES, strict=True)):
        loss = Decimal("0")
        for pair in pairs:
            forecast = (
                pair.candidate_quantiles[index]
                if forecast_name == "candidate"
                else pair.baselines[forecast_name]
            )
            loss += _pinball(pair.actual, forecast, tau)
        result[tau_name] = {
            "loss": loss,
            "normalized": _ratio(loss, denominator, reason="zero pinball denominator"),
        }
    return result


def _window_pairs(
    pairs: Sequence[GovernancePair],
    months: Sequence[str],
) -> tuple[GovernancePair, ...]:
    selected = tuple(pair for pair in pairs if pair.target_month in set(months))
    if not selected:
        raise ForecastGovernanceError("governance window is empty")
    return selected


def _nearest_rank(values: Sequence[Decimal], probability: Decimal) -> Decimal:
    rank = math.ceil(float(probability * Decimal(len(values)))) - 1
    return sorted(values)[rank]


def paired_cluster_bootstrap(
    pairs: Sequence[GovernancePair],
    *,
    baseline_name: str,
    seed: int,
    replicates: int = 10_000,
) -> dict[str, Decimal | int | str]:
    site_codes = sorted({pair.site_code for pair in pairs})
    by_site = {
        site_code: tuple(pair for pair in pairs if pair.site_code == site_code)
        for site_code in site_codes
    }
    if not site_codes or replicates <= 0:
        raise ForecastGovernanceError("bootstrap requires sites and replicates")
    rng = random.Random(seed)
    deltas: list[Decimal] = []
    for _replicate in range(replicates):
        for _attempt in range(100):
            sampled = [rng.choice(site_codes) for _site in site_codes]
            sample_pairs = tuple(pair for site in sampled for pair in by_site[site])
            denominator = sum((pair.actual for pair in sample_pairs), Decimal("0"))
            if denominator > 0:
                candidate_error = sum(
                    (abs(pair.candidate_point - pair.actual) for pair in sample_pairs),
                    Decimal("0"),
                )
                baseline_error = sum(
                    (abs(pair.baselines[baseline_name] - pair.actual) for pair in sample_pairs),
                    Decimal("0"),
                )
                deltas.append((candidate_error - baseline_error) / denominator)
                break
        else:
            raise ForecastGovernanceError("bootstrap exhausted zero-denominator redraws")
    return {
        "seed": seed,
        "replicates": replicates,
        "best_point_baseline": baseline_name,
        "ci95_lower": _nearest_rank(deltas, Decimal("0.025")),
        "ci95_upper": _nearest_rank(deltas, Decimal("0.975")),
        "minimum_delta": min(deltas),
        "maximum_delta": max(deltas),
    }


def population_stability_index(
    reference: Sequence[Decimal],
    current: Sequence[Decimal],
    *,
    bins: int = 10,
    epsilon: Decimal = Decimal("0.000001"),
) -> Decimal:
    if len(reference) < 100 or len(current) < 100 or bins != 10:
        raise ForecastGovernanceError("PSI requires at least 100 observations and deciles")
    ordered = sorted(reference)
    cutoffs = [ordered[math.ceil(index * len(ordered) / bins) - 1] for index in range(1, bins)]

    def shares(values: Sequence[Decimal]) -> list[Decimal]:
        counts = [0] * bins
        for value in values:
            position = sum(value > cutoff for cutoff in cutoffs)
            counts[position] += 1
        total = Decimal(len(values))
        return [max(Decimal(count) / total, epsilon) for count in counts]

    reference_shares = shares(reference)
    current_shares = shares(current)
    return sum(
        (
            (current_share - reference_share)
            * Decimal(str(math.log(float(current_share / reference_share))))
            for reference_share, current_share in zip(reference_shares, current_shares, strict=True)
        ),
        Decimal("0"),
    )


def maximum_categorical_share_movement(
    reference: Sequence[str],
    current: Sequence[str],
) -> Decimal:
    if not reference or not current:
        raise ForecastGovernanceError("categorical drift needs two nonempty samples")
    categories = set(reference) | set(current)
    reference_total = Decimal(len(reference))
    current_total = Decimal(len(current))
    return max(
        abs(
            Decimal(reference.count(category)) / reference_total
            - Decimal(current.count(category)) / current_total
        )
        for category in categories
    )


def _six_month_wins(
    pairs: Sequence[GovernancePair],
    months: Sequence[str],
    baseline_name: str,
) -> int:
    wins = 0
    for month in months:
        month_pairs = tuple(pair for pair in pairs if pair.target_month == month)
        if _point_metrics(month_pairs, "candidate")["wape"] < _point_metrics(month_pairs, baseline_name)["wape"]:
            wins += 1
    return wins


def _subgroup_gate(pairs: Sequence[GovernancePair], baseline_name: str) -> bool:
    for regional in {pair.regional for pair in pairs}:
        subgroup = tuple(pair for pair in pairs if pair.regional == regional)
        candidate = _point_metrics(subgroup, "candidate")["wape"]
        baseline = _point_metrics(subgroup, baseline_name)["wape"]
        if candidate > baseline + Decimal("0.10"):
            return False
    return True


def _pinball_gate(
    candidate: Mapping[str, Mapping[str, Mapping[str, Decimal]]],
    baselines: Mapping[str, Mapping[str, Mapping[str, Mapping[str, Decimal]]]],
) -> bool:
    for window, candidate_metrics in candidate.items():
        for tau_name in TAU_NAMES:
            best = min(
                metrics[window][tau_name]["normalized"]
                for metrics in baselines.values()
            )
            if candidate_metrics[tau_name]["normalized"] > best * Decimal("1.05"):
                return False
    return True


def _zero_denominator_evaluation(
    *,
    pairs: Sequence[GovernancePair],
    expected_count: int,
    source_freshness_months: int,
    feature_psi: Mapping[str, Decimal] | None,
    categorical_share_movement: Decimal,
    fixture_payload_sha256: str,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "contract": "ai-governance-candidate-v1",
        "decision": "BLOCKED",
        "reasons": ["zero_actual_denominator"],
        "candidate_only": True,
        "live_promotion_performed": False,
        "expanded_pairs": len(pairs),
        "pair_coverage": Decimal(len(pairs)) / Decimal(expected_count),
        "fallback_ratio": Decimal("0"),
        "invalid_pairs": 0,
        "candidate_point": {
            "actual_total": Decimal("0"),
            "forecast_total": sum((pair.candidate_point for pair in pairs), Decimal("0")),
            "absolute_error_total": sum(
                (abs(pair.candidate_point - pair.actual) for pair in pairs),
                Decimal("0"),
            ),
            "wape": None,
            "bias": None,
        },
        "source_freshness_months": source_freshness_months,
        "feature_psi": feature_psi or {},
        "categorical_share_movement": categorical_share_movement,
        "fixture_payload_sha256": fixture_payload_sha256,
    }


def _pinball_tables(
    pairs: Sequence[GovernancePair],
    windows: Mapping[str, Sequence[str]],
    baseline_names: Sequence[str],
) -> tuple[
    dict[str, Decimal],
    dict[str, dict[str, dict[str, Decimal]]],
    dict[str, dict[str, dict[str, dict[str, Decimal]]]],
]:
    denominators: dict[str, Decimal] = {}
    candidate: dict[str, dict[str, dict[str, Decimal]]] = {}
    baselines: dict[str, dict[str, dict[str, dict[str, Decimal]]]] = {
        name: {} for name in baseline_names
    }
    for window, months in windows.items():
        selected = _window_pairs(pairs, months)
        denominators[window] = sum((pair.actual for pair in selected), Decimal("0"))
        candidate[window] = _pinball_metrics(selected, "candidate")
        for name in baseline_names:
            baselines[name][window] = _pinball_metrics(selected, name)
    return denominators, candidate, baselines


def _monthly_bias_gate(
    pairs: Sequence[GovernancePair],
    months: Sequence[str],
) -> bool:
    return all(
        abs(
            _point_metrics(
                tuple(pair for pair in pairs if pair.target_month == month),
                "candidate",
            )["bias"]
        )
        <= Decimal("0.15")
        for month in months
    )


def _governance_reasons(
    *,
    authority_ready: bool,
    response_profile: str,
    exact_coverage: bool,
    bias_gate: bool,
    relative_improvement: Decimal | None,
    subgroup_gate: bool,
    bootstrap_upper: Decimal,
    six_month_wins: int,
    pinball_gate: bool,
    source_freshness_months: int,
    feature_psi: Mapping[str, Decimal],
    categorical_share_movement: Decimal,
) -> list[str]:
    checks = (
        (not authority_ready, "authority_incomplete"),
        (response_profile != "point_quantiles_v1", "quantiles_required"),
        (not exact_coverage, "pair_coverage_incomplete"),
        (not bias_gate, "bias_gate_failed"),
        (
            relative_improvement is None or relative_improvement < Decimal("0.02"),
            "relative_wape_gate_failed",
        ),
        (not subgroup_gate, "subgroup_wape_gate_failed"),
        (
            bootstrap_upper >= 0 or six_month_wins < 5,
            "paired_significance_gate_failed",
        ),
        (not pinball_gate, "pinball_gate_failed"),
        (source_freshness_months > 1, "source_stale"),
        (
            any(value >= Decimal("0.20") for value in feature_psi.values()),
            "feature_drift",
        ),
        (categorical_share_movement > Decimal("0.20"), "categorical_drift"),
    )
    return [reason for failed, reason in checks if failed]


def evaluate_governance_fixture(
    fixture: Mapping[str, Any],
    *,
    seed: int,
    response_profile: str = "point_quantiles_v1",
    authority_ready: bool = True,
    source_freshness_months: int = 0,
    feature_psi: Mapping[str, Decimal] | None = None,
    categorical_share_movement: Decimal = Decimal("0"),
) -> dict[str, Any]:
    pairs = expand_governance_pairs(fixture)
    expected_count = len(fixture["months"]) * len(fixture["stores"])
    if sum((pair.actual for pair in pairs), Decimal("0")) <= 0:
        return _zero_denominator_evaluation(
            pairs=pairs,
            expected_count=expected_count,
            source_freshness_months=source_freshness_months,
            feature_psi=feature_psi,
            categorical_share_movement=categorical_share_movement,
            fixture_payload_sha256=fixture["contract_payload_sha256"],
        )
    baseline_names = sorted(pairs[0].baselines)
    candidate_point = _point_metrics(pairs, "candidate")
    baseline_point = {name: _point_metrics(pairs, name) for name in baseline_names}
    best_baseline = min(baseline_names, key=lambda name: (baseline_point[name]["wape"], name))
    best_wape = baseline_point[best_baseline]["wape"]
    relative_improvement = (
        None if best_wape == 0 else (best_wape - candidate_point["wape"]) / best_wape
    )
    windows = fixture["windows"]
    denominators, candidate_pinball, baseline_pinball = _pinball_tables(
        pairs, windows, baseline_names
    )
    bootstrap = paired_cluster_bootstrap(
        pairs,
        baseline_name=best_baseline,
        seed=seed,
    )
    wins = _six_month_wins(pairs, list(windows["6"]), best_baseline)
    feature_psi = feature_psi or {
        "log1p_monthly_value": Decimal("0"),
        "context_months": Decimal("0"),
        "months_since_opening": Decimal("0"),
    }
    reasons = _governance_reasons(
        authority_ready=authority_ready,
        response_profile=response_profile,
        exact_coverage=len(pairs) == expected_count,
        bias_gate=(
            abs(candidate_point["bias"]) <= Decimal("0.10")
            and _monthly_bias_gate(pairs, fixture["months"])
        ),
        relative_improvement=relative_improvement,
        subgroup_gate=_subgroup_gate(pairs, best_baseline),
        bootstrap_upper=Decimal(str(bootstrap["ci95_upper"])),
        six_month_wins=wins,
        pinball_gate=_pinball_gate(candidate_pinball, baseline_pinball),
        source_freshness_months=source_freshness_months,
        feature_psi=feature_psi,
        categorical_share_movement=categorical_share_movement,
    )

    decision = "eligible_candidate_only_no_live_promotion" if not reasons else "BLOCKED"
    return {
        "schema_version": 1,
        "contract": "ai-governance-candidate-v1",
        "decision": decision,
        "reasons": reasons,
        "candidate_only": True,
        "live_promotion_performed": False,
        "expanded_pairs": len(pairs),
        "pair_coverage": Decimal(len(pairs)) / Decimal(expected_count),
        "fallback_ratio": Decimal("0"),
        "invalid_pairs": 0,
        "candidate_point": candidate_point,
        "baseline_point": baseline_point,
        "best_point_baseline": best_baseline,
        "relative_wape_improvement": relative_improvement,
        "pinball_actual_denominators": denominators,
        "candidate_pinball": candidate_pinball,
        "baseline_pinball": baseline_pinball,
        "candidate_quantile_coverage": Decimal("1") if response_profile == "point_quantiles_v1" else Decimal("0"),
        "six_month_wins": wins,
        "bootstrap": bootstrap,
        "source_freshness_months": source_freshness_months,
        "feature_psi": feature_psi,
        "categorical_share_movement": categorical_share_movement,
        "fixture_payload_sha256": fixture["contract_payload_sha256"],
    }
