from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

from schemas.dashboard import DashboardSpecialCard, DashboardSpecialCardMetric
from services.dashboard_specials_config import (
    format_currency,
    format_int,
    month_overlaps_period,
)

def build_promotion_card(
    month: str,
    definition: dict[str, Any] | None,
    stats: dict[str, Any] | None,
    *,
    config_error: str | None = None,
    definition_error: str | None = None,
) -> DashboardSpecialCard:
    if config_error:
        return DashboardSpecialCard(
            key="promotion",
            title="Promotie speciala",
            subtitle="Card promo cu coduri fixe",
            status="missing_config",
            status_label="Config invalid",
            highlight_value="-",
            description=config_error,
        )

    if definition_error:
        return DashboardSpecialCard(
            key="promotion",
            title="Promotie speciala",
            subtitle="Card promo cu coduri fixe",
            status="missing_config",
            status_label="Config incomplet",
            highlight_value="-",
            description=definition_error,
        )

    if definition is None:
        return DashboardSpecialCard(
            key="promotion",
            title="Promotie speciala",
            subtitle="Card promo cu coduri fixe",
            status="missing_config",
            status_label="Config lipsa",
            highlight_value="-",
            description="Lipseste definitia `promotion` din `hub_specials.json`.",
        )

    start_date = definition["start_date"]
    end_date = definition["end_date"]
    if not month_overlaps_period(month, start_date, end_date):
        return DashboardSpecialCard(
            key="promotion",
            title=definition["title"],
            subtitle=definition["subtitle"],
            status="inactive",
            status_label="In afara perioadei",
            highlight_value=f"{start_date.isoformat()} - {end_date.isoformat()}",
            description=definition["description"]
            or f"Promotia este definita pe {format_int(len(definition['item_codes']))} coduri fixe.",
            coverage_note=definition.get("coverage_note"),
            metrics=[
                DashboardSpecialCardMetric(
                    label="Coduri", value=format_int(len(definition["item_codes"]))
                )
            ],
        )

    normalized_stats = stats or {}
    qualifying_bons = int(normalized_stats.get("qualifying_bons") or 0)
    discounted_units = int(normalized_stats.get("discounted_units") or 0)
    discount_value = Decimal(normalized_stats.get("discount_value") or 0)
    active_stores = int(normalized_stats.get("active_stores") or 0)
    active_agents = int(normalized_stats.get("active_agents") or 0)
    status: Literal["ready", "no_data"] = "ready" if qualifying_bons > 0 else "no_data"

    return DashboardSpecialCard(
        key="promotion",
        title=definition["title"],
        subtitle=definition["subtitle"],
        status=status,
        status_label="Bonuri calificate" if status == "ready" else "Fara bonuri calificate",
        highlight_value=format_int(qualifying_bons),
        description=definition["description"]
        or f"Perioada {start_date.isoformat()} - {end_date.isoformat()} pentru {format_int(len(definition['item_codes']))} coduri.",
        coverage_note=definition.get("coverage_note"),
        metrics=[
            DashboardSpecialCardMetric(
                label="Produse reduse", value=format_int(discounted_units)
            ),
            DashboardSpecialCardMetric(
                label="Valoare discount", value=format_currency(discount_value)
            ),
            DashboardSpecialCardMetric(
                label="Magazine", value=format_int(active_stores)
            ),
            DashboardSpecialCardMetric(label="Agenti", value=format_int(active_agents)),
        ],
    )


def _incentive_missing_card(
    definition: dict[str, Any] | None,
    *,
    config_error: str | None,
    definition_error: str | None,
    codes_error: str | None,
) -> DashboardSpecialCard | None:
    if config_error is not None:
        return DashboardSpecialCard(
            key="incentive",
            title="Incentive special",
            subtitle="Bonus pe coduri eligibile",
            status="missing_config",
            status_label="Config invalid",
            highlight_value="-",
            description=config_error,
        )

    if definition_error is not None:
        return DashboardSpecialCard(
            key="incentive",
            title="Incentive special",
            subtitle="Bonus pe coduri eligibile",
            status="missing_config",
            status_label="Config incomplet",
            highlight_value="-",
            description=definition_error,
        )

    if definition is None:
        return DashboardSpecialCard(
            key="incentive",
            title="Incentive special",
            subtitle="Bonus pe coduri eligibile",
            status="missing_config",
            status_label="Config lipsa",
            highlight_value="-",
            description="Lipseste definitia `incentive` din `hub_specials.json`.",
        )

    if codes_error is not None:
        return DashboardSpecialCard(
            key="incentive",
            title=definition["title"],
            subtitle=definition["subtitle"],
            status="missing_source",
            status_label="Fisier lipsa",
            highlight_value=Path(definition["source_file"]).name,
            description=codes_error,
        )
    return None


def _inactive_incentive_card(
    definition: dict[str, Any], reward_per_unit: Any
) -> DashboardSpecialCard:
    metrics = []
    if reward_per_unit is not None:
        metrics = [
            DashboardSpecialCardMetric(
                label="Bonus / buc", value=format_currency(reward_per_unit)
            )
        ]
    return DashboardSpecialCard(
        key="incentive",
        title=definition["title"],
        subtitle=definition["subtitle"],
        status="inactive",
        status_label="Alta luna",
        highlight_value=definition["month"],
        description=definition["description"]
        or f"Incentive-ul este configurat pentru luna {definition['month']}.",
        metrics=metrics,
    )


def _incentive_ready_card(
    definition: dict[str, Any], stats: dict[str, Any]
) -> DashboardSpecialCard:
    reward_per_unit = definition.get("reward_per_unit")
    net_quantity = int(stats.get("net_quantity") or 0)
    positive_quantity = int(stats.get("positive_quantity") or 0)
    return_quantity = abs(int(stats.get("return_quantity") or 0))
    active_stores = int(stats.get("active_stores") or 0)
    active_agents = int(stats.get("active_agents") or 0)
    active_codes = int(stats.get("active_codes") or 0)
    status: Literal["ready", "no_data"] = (
        "ready" if positive_quantity > 0 or return_quantity > 0 else "no_data"
    )
    if reward_per_unit is None:
        estimated_bonus = float(stats.get("incentive_value") or 0)
        coverage = (
            f"Magazine active: {format_int(active_stores)}. "
            "Bonusul este calculat pe cantitate vanduta x valoarea incentive per cod."
        )
        description = definition["description"] or "Bonusul variaza per cod de produs."
    else:
        rpu = float(reward_per_unit)
        estimated_bonus = net_quantity * rpu
        coverage = (
            f"Magazine active: {format_int(active_stores)}. "
            "Bonusul este calculat pe cantitate neta (retururile scad cate "
            f"{format_currency(rpu)} per unitate)."
        )
        description = definition["description"] or (
            f"Fiecare unitate neta eligibila aduce {format_currency(rpu)} agentului."
        )
    metrics = [
        DashboardSpecialCardMetric(label="Unitati nete", value=format_int(net_quantity)),
        DashboardSpecialCardMetric(label="Retururi", value=format_int(return_quantity)),
        DashboardSpecialCardMetric(label="Coduri active", value=format_int(active_codes)),
        DashboardSpecialCardMetric(label="Agenti", value=format_int(active_agents)),
    ]
    return DashboardSpecialCard(
        key="incentive",
        title=definition["title"],
        subtitle=definition["subtitle"],
        status=status,
        status_label="Calcul net" if status == "ready" else "Fara vanzari",
        highlight_value=format_currency(estimated_bonus),
        description=description,
        metrics=metrics,
        coverage_note=coverage,
    )


def build_incentive_card(
    month: str,
    definition: dict[str, Any] | None,
    stats: dict[str, Any] | None,
    *,
    config_error: str | None = None,
    definition_error: str | None = None,
    codes_error: str | None = None,
) -> DashboardSpecialCard:
    missing = _incentive_missing_card(
        definition,
        config_error=config_error,
        definition_error=definition_error,
        codes_error=codes_error,
    )
    if missing is not None:
        return missing
    assert definition is not None

    reward_per_unit = definition.get("reward_per_unit")
    if month != definition["month"]:
        return _inactive_incentive_card(definition, reward_per_unit)
    return _incentive_ready_card(definition, stats or {})
