"""Credit eligible incentive products to the calendar worker, including TL POS sales."""
from collections import defaultdict
from decimal import Decimal
from services.campaigns.loader import load_campaign_configuration
from services.campaigns.summary import get_store_incentive_multipliers
from services.promotion_evaluation import evaluate_promotion, scope_promotion_definition_to_interval

async def read_incentives(conn, month, calendar, cutoff):
    if cutoff is None:
        return {}, False
    workers = {(d['site_code'], d['work_date']): d['agent_code'] for d in calendar['days'] if d['status'] == 'work' and d['work_date'] <= cutoff}
    rows = await conn.fetch("""SELECT r.site_code,r.sale_date,r.item_code,ip.valid_from,ip.valid_to,
        ip.reward_value,SUM(r.net_quantity)::int AS quantity
        FROM reporting_item_day r
        JOIN incentive_campaigns c ON c.month=r.import_month
        JOIN incentive_products ip ON ip.campaign_id=c.id AND ip.item_code=r.item_code
            AND r.sale_date BETWEEN ip.valid_from AND ip.valid_to
        WHERE r.import_month=$1 AND r.sale_date <= $2
        GROUP BY r.site_code,r.sale_date,r.item_code,ip.valid_from,ip.valid_to,ip.reward_value""", month, cutoff)
    if not rows:
        return {}, True
    _config, config_error, definitions, definitions_error, _selected, _error = load_campaign_configuration(month, promotion_key=None)
    if config_error or definitions_error:
        return {}, False
    excluded = defaultdict(int)
    # One evaluation per relevant date, not per agent/store. The canonical
    # interval evaluator handles receipt rules and avoids splitting cumulative POS actuals.
    for day in sorted({r['sale_date'] for r in rows if (r['site_code'], r['sale_date']) in workers}):
        for definition in definitions:
            if not definition['start_date'] <= day <= definition['end_date']:
                continue
            evaluation = await evaluate_promotion(conn, month=month,
                definition=scope_promotion_definition_to_interval(definition, day, day),
                firma=None, regional=None, asm=None, site_code=None, agent=None,
                current_scope=False, include_closed_stores=True)
            if not evaluation.is_complete:
                return {}, False
            if evaluation.result:
                for (site, _pos_agent, item), units in evaluation.result.excluded_units.items():
                    excluded[(site, day, item)] += units
    multipliers, _achievements = await get_store_incentive_multipliers(conn, month, None, None, None, None,
        include_closed_stores=True, cutoff_date=cutoff)
    quantities = defaultdict(int)
    for row in rows:
        agent = workers.get((row['site_code'], row['sale_date']))
        if not agent:
            continue
        key = (agent, row['site_code'], row['item_code'], row['valid_from'], row['valid_to'], row['reward_value'])
        quantities[key] += row['quantity'] - excluded[(row['site_code'], row['sale_date'], row['item_code'])]
    totals = defaultdict(Decimal)
    for (agent, site, _item, _start, _end, reward), quantity in quantities.items():
        totals[agent] += max(0, quantity) * reward * Decimal(str(multipliers.get(site, 0)))
    return dict(totals), True
