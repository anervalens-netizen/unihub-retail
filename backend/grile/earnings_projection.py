"""Calendar owns attribution; physical store/day sales are credited once."""
from collections import Counter
from datetime import date
from decimal import Decimal
from hashlib import sha256
import json
from typing import Any

from grile.calendar_models import CalendarDay, CalendarMonth, RosterEntry
from grile.earnings_models import AgentEarnings, EarningsDay, EarningsMonth
from grile.earnings_rules import daily_commission, monthly_commission


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
        home_work_days=sum(not day.away for day in days), home_target=target,
        home_sales=sales if has_source else None, home_commission=commission if has_source else None,
        away_commission=away if has_source else None,
        supplemental_pay=supplemental, known_earnings=known, days=days,
        issues=sorted({day.issue for day in days if day.issue and day.issue != "after_cutoff"}),
    )


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
        days = [_day_earnings(day, entry.home_site_code, cutoff, sales, daily_targets)
                for day in work if day.agent_code == entry.agent_code]
        if entry.active or days:
            agents.append(_agent_earnings(entry, days, daily_targets.get(entry.home_site_code, (None, 0)), cutoff is not None))
    assigned = {(day.site_code, day.work_date) for day in work}
    unassigned = [row for row in sources["sales"] if (row["site_code"], row["sale_date"]) not in assigned]
    result = EarningsMonth(
        month=calendar.month, projection_revision="", calendar_revision=calendar.projection_revision,
        cutoff=cutoff, selling_days=selling_days, agents=agents, unassigned_sales=unassigned,
    )
    result.projection_revision = sha256((result.model_dump_json() + json.dumps(sources["targets"], default=str, sort_keys=True)).encode()).hexdigest()
    return result
