"""Projections use calendar-confirmed days; V1 manual values remain explicit."""
from decimal import Decimal
from grile.compensation_models import CompensationEntry
from grile.base_salary import base_salary
from grile.dashboard_models import PerformanceMetrics, SalaryMetrics
from grile.earnings_rules import monthly_commission, whole_ron

D = Decimal

def performance(target, sales, scheduled, elapsed, leave=0, supplemental=0):
    average = sales / elapsed if sales is not None and elapsed else None
    forecast = average * scheduled if average is not None else None
    remaining = scheduled - elapsed
    values = {}
    for name, rate in [('daily_80','0.8'),('daily_90','0.9'),('daily_100','1'),('daily_120','1.2')]:
        values[name] = max(D(0), target * D(rate) - sales) / remaining if target is not None and target > 0 and sales is not None and remaining > 0 else None
    return PerformanceMetrics(target=target, sales=sales, progress=sales / target * 100 if sales is not None and target else None,
        average=average, forecast=forecast, forecast_progress=forecast / target * 100 if forecast is not None and target else None,
        scheduled_days=scheduled, worked_days=elapsed, leave_days=leave, supplemental_days=supplemental, **values)

def salary(agent, inputs, metrics):
    sim = D(inputs.sim_quantity) * 3 if inputs.sim_quantity is not None else None
    epay = D(inputs.epay_under_50) * 5 + D(inputs.epay_over_50) * 12 if inputs.epay_under_50 is not None and inputs.epay_over_50 is not None else None
    parts = [agent.home_commission, agent.away_commission, sim, epay, inputs.incentive]
    commission = sum(parts, D(0)) if all(p is not None for p in parts) else None
    fixed = [inputs.salary_base, inputs.vouchers, sim, epay, inputs.incentive, inputs.adjustment, agent.away_commission, agent.supplemental_pay]
    rest = sum(fixed, D(0)) if all(p is not None for p in fixed) else None
    forecast_commission = monthly_commission(metrics.forecast, metrics.target) if metrics.forecast is not None and metrics.target else None
    potential = monthly_commission(metrics.target * D('1.2'), metrics.target) if metrics.target else None
    return SalaryMetrics(sim_pay=sim, epay_pay=epay, commission_total=commission,
        current_total=whole_ron(rest + agent.home_commission) if rest is not None and agent.home_commission is not None else None,
        forecast_total=whole_ron(rest + forecast_commission) if rest is not None and forecast_commission is not None else None,
        potential_120=whole_ron(rest + potential) if rest is not None and potential is not None else None)

def enrich_dashboard(result, calendar, sources):
    inputs = {row['agent_code']: CompensationEntry.model_validate(row) for row in sources.get('compensation', [])}
    for agent in result.agents:
        home = [d for d in agent.days if not d.away]
        elapsed = [d for d in home if result.cutoff and d.work_date <= result.cutoff]
        leave = sum(d.status == 'leave' and d.agent_code == agent.agent_code for d in calendar.days)
        metrics = performance(agent.home_target, agent.home_sales, len(home), len(elapsed), leave, sum(d.supplemental for d in agent.days))
        agent.performance = metrics
        agent.compensation = inputs.get(agent.agent_code, CompensationEntry(month=result.month, agent_code=agent.agent_code, revision=0))
        if agent.home_site_code != 'TL':
            agent.compensation.salary_base = base_salary(agent.home_site_code)
        if agent.compensation.vouchers is None:
            agent.compensation.vouchers = D(480)
        agent.salary = salary(agent, agent.compensation, metrics)
    targets = {row['site_code']: row['target_value'] for row in sources['targets']}
    for site in targets.keys() | result.selling_days.keys():
        work = [d for d in calendar.days if d.site_code == site and d.status == 'work']
        elapsed = [d for d in work if result.cutoff and d.work_date <= result.cutoff]
        sales_rows = [r for r in sources['sales'] if r['site_code'] == site and result.cutoff and r['sale_date'] <= result.cutoff]
        covered = {r['sale_date'] for r in sales_rows}
        sales = sum((r['sales'] for r in sales_rows), D(0)) if result.cutoff and sales_rows and all(d.work_date in covered for d in elapsed) else None
        result.stores[site] = performance(targets.get(site), sales, len(work), len(elapsed))
