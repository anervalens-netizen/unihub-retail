"""Calendar owns attribution; physical store/day sales are credited once."""
from collections import Counter
from datetime import date
from calendar import monthrange
from decimal import Decimal
from hashlib import sha256
import json
from typing import Any

from grile.calendar_models import CalendarDay, CalendarMonth, RosterEntry
from grile.earnings_models import AgentEarnings, EarningsDay, EarningsMonth
from grile.earnings_rules import daily_commission, monthly_commission
from grile.earnings_dashboard import enrich_dashboard
from grile.roster_history import home_on
from grile.target_models import AgentTargetState
from business_clock import business_today


def _day_earnings(
    day: CalendarDay, home: str, cutoff: date | None,
    sales: dict[tuple[str, date], Decimal], targets: dict[str, tuple[Decimal, int]],
) -> EarningsDay:
    target, divisor = targets.get(day.site_code, (None, 0))
    result = EarningsDay(work_date=day.work_date, site_code=day.site_code,
                         agent_code=day.agent_code, supplemental=day.supplemental,
                         away=day.site_code != home, sales=None,
                         daily_target=target / divisor if target is not None and divisor else None)
    if cutoff is None:
        result.issue = "missing_published_source"
        result.supplemental_pay = None
    elif day.work_date > cutoff:
        result.issue = "after_cutoff"
    else:
        result.sales = sales.get((day.site_code, day.work_date))
        result.supplemental_pay = Decimal(150) if day.supplemental else Decimal(0)
        if result.sales is None:
            result.issue = "missing_sales"
        elif result.daily_target is None or result.daily_target <= 0:
            result.issue = "missing_positive_target"
        elif result.away:
            result.commission = daily_commission(result.sales, target, divisor) if target is not None else None
    return result


def _home_components(days: list[EarningsDay], monthly_target: Decimal | None, divisor: int) -> tuple[Decimal | None, Decimal | None, Decimal | None]:
    home = [day for day in days if not day.away]
    if not home:
        return Decimal(0), Decimal(0), Decimal(0)
    target = None
    if monthly_target is not None and monthly_target > 0 and divisor > 0:
        target = monthly_target * len(home) / divisor
    elapsed = [day for day in home if day.issue != "after_cutoff"]
    if any(day.sales is None for day in elapsed):
        return target, None, None
    sales = sum((day.sales for day in elapsed if day.sales is not None), Decimal(0))
    commission = monthly_commission(sales, monthly_target * len(home), divisor) if target is not None and monthly_target is not None else None
    return target, sales, commission


def _agent_earnings(entry: RosterEntry, days: list[EarningsDay], target_basis: tuple[Decimal | None, int], has_source: bool) -> AgentEarnings:
    target, sales, commission = _home_components(days, *target_basis)
    away_days = [day for day in days if day.away and day.issue != "after_cutoff"]
    away = None if any(day.commission is None for day in away_days) else sum(
        (day.commission for day in away_days if day.commission is not None), Decimal(0),
    )
    supplemental = sum((day.supplemental_pay for day in days if day.supplemental_pay is not None), Decimal(0)) if has_source else None
    known = None if commission is None or away is None or supplemental is None else commission + away + supplemental
    return AgentEarnings(
        agent_code=entry.agent_code, home_site_code=entry.home_site_code,
        display_name=entry.display_name, identity_status=entry.identity_status,
        home_work_days=sum(not day.away for day in days), home_target=target,
        home_sales=sales if has_source else None, home_commission=commission if has_source else None,
        away_commission=away if has_source else None,
        supplemental_pay=supplemental, known_earnings=known, days=days,
        issues=sorted({day.issue for day in days if day.issue and day.issue != "after_cutoff"}),
    )


def _apply_transfer_projection(projected, entry, days, daily_targets, cutoff):
    if not entry.transfers:
        return
    parts = [_home_components([d for d in days if d.site_code == site], *daily_targets.get(site, (None, 0)))
             for site in sorted({d.site_code for d in days if not d.away})]
    values = [sum((p[i] for p in parts), Decimal(0)) if all(p[i] is not None for p in parts) else None for i in range(3)]
    projected.home_target, projected.home_sales = values[:2]
    projected.home_commission = monthly_commission(projected.home_sales, projected.home_target) if projected.home_sales is not None and projected.home_target else (Decimal(0) if not parts else None)
    if cutoff is None:
        projected.home_sales = projected.home_commission = None
    components = [projected.home_commission, projected.away_commission, projected.supplemental_pay]
    projected.known_earnings = sum(components, Decimal(0)) if all(c is not None for c in components) else None


def _target_setting_inputs(projected, entry, days, calendar, sources):
    setting: dict[str, Any] = next((r for r in sources.get("target_settings", []) if r["agent_code"] == entry.agent_code and r["month"] == calendar.month), {})
    target_setting = AgentTargetState(
        month=calendar.month, agent_code=entry.agent_code,
        mode=setting.get("mode", "automatic"), manual_target=setting.get("manual_target"),
        revision=setting.get("revision", 0), automatic_target=projected.home_target,
    )
    home_sites = {entry.home_site_code} | {d.site_code for d in days if not d.away}
    resolved = [r for r in sources.get("agent_target_rows", []) if r["agent"] == entry.agent_code and r["import_month"] == calendar.month and r["site_code"] in home_sites]
    return target_setting, resolved


def _refresh_target_earnings(projected):
    projected.home_commission = monthly_commission(projected.home_sales, projected.home_target) if projected.home_sales is not None and projected.home_target else (Decimal(0) if projected.home_target == 0 and projected.home_sales == 0 else None)
    components = [projected.home_commission, projected.away_commission, projected.supplemental_pay]
    projected.known_earnings = sum(components, Decimal(0)) if all(c is not None for c in components) else None


def _apply_target_setting(projected, entry, days, calendar, sources):
    target_setting, resolved = _target_setting_inputs(projected, entry, days, calendar, sources)
    projected.target_setting = target_setting
    if resolved:
        projected.home_target = sum((r["target_value"] for r in resolved), Decimal(0)) if all(r["target_value"] is not None for r in resolved) else None
    elif target_setting.mode == "manual":
        projected.home_target = target_setting.manual_target
    if resolved or target_setting.mode == "manual":
        _refresh_target_earnings(projected)


def _project_agent(entry, calendar, work, daily_targets, cutoff, sales, sources):
    days = [_day_earnings(day, home_on(entry, day.work_date), cutoff, sales, daily_targets)
            for day in work if day.agent_code == entry.agent_code]
    if not (entry.active or days):
        return None
    current_home = home_on(entry, min(max(business_today(), date.fromisoformat(calendar.month + '-01')), date.fromisoformat(calendar.month + '-01').replace(day=monthrange(int(calendar.month[:4]), int(calendar.month[5:]))[1])))
    projected = _agent_earnings(entry, days, daily_targets.get(entry.home_site_code, (None, 0)), cutoff is not None)
    _apply_transfer_projection(projected, entry, days, daily_targets, cutoff)
    _apply_target_setting(projected, entry, days, calendar, sources)
    projected.home_site_code = current_home
    return projected


def project_earnings(calendar: CalendarMonth, sources: dict[str, Any]) -> EarningsMonth:
    work = [day for day in calendar.days if day.status == "work"]
    selling_days = dict(Counter(day.site_code for day in work))
    daily_targets = {
        row["site_code"]: (row["target_value"], selling_days[row["site_code"]])
        for row in sources["targets"] if selling_days.get(row["site_code"])
    }
    source = sources["source"] or {}
    cutoff = source.get("cutoff_date")
    sales = {(row["site_code"], row["sale_date"]): row["sales"] for row in sources["sales"]}
    agents = []
    for entry in calendar.roster:
        projected = _project_agent(entry, calendar, work, daily_targets, cutoff, sales, sources)
        if projected is not None:
            agents.append(projected)
    assigned = {(day.site_code, day.work_date) for day in work}
    unassigned = [row for row in sources["sales"] if (row["site_code"], row["sale_date"]) not in assigned]
    result = EarningsMonth(
        month=calendar.month, projection_revision="", calendar_revision=calendar.projection_revision,
        cutoff=cutoff, selling_days=selling_days, agents=agents, unassigned_sales=unassigned,
    )
    enrich_dashboard(result, calendar, sources)
    result.projection_revision = sha256((result.model_dump_json() + json.dumps(sources["targets"], default=str, sort_keys=True)).encode()).hexdigest()
    return result
