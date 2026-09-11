"""Capture a read-only, reproducible P&L salary reconstruction for review."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from collections import defaultdict
from dataclasses import asdict
from datetime import date
from decimal import Decimal
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
from db.connection import connect_database_url
from scripts.store_pnl_estimator_inputs import load_inputs, normalize_sales
from scripts.estimate_store_pnl import build_estimates, all_missing_targets


def encode(value):
    return json.dumps(value, default=str, sort_keys=True, separators=(',', ':'))


def digest(value):
    return hashlib.sha256(encode(value).encode()).hexdigest()


def metrics(rows):
    values = defaultdict(Decimal)
    for row in rows:
        values[row['category_code']] += Decimal(str(row['amount']))
    revenue = sum((values[k] for k in ('v1', 'v11', 'v2', 'v3')), Decimal(0))
    cogs = sum((values[k] for k in ('c1', 'c11', 'c2')), Decimal(0))
    costs = sum((values[k] for k in ('c3', 'c4', 'c5', 'c6')), Decimal(0))
    return dict(revenue=revenue, gross_margin=revenue-cogs, operating_costs=costs,
                ebitda=revenue-cogs-costs, ebit=revenue-cogs-costs-values['a1'], salary=values['c3'])


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--through', required=True, help='Last month YYYY-MM; review only, no apply action')
    args = parser.parse_args()
    through = date.fromisoformat(args.through + '-01')
    next_month = date(through.year + (through.month == 12), through.month % 12 + 1, 1)
    out = args.output
    out.mkdir(parents=True, mode=0o700, exist_ok=False)
    c = await connect_database_url(dotenv_values(ROOT / '.env')['DATABASE_URL'], application_name='pnl-hr-review')
    try:
        async with c.transaction(isolation='repeatable_read', readonly=True):
            actual, gross, salaries, stores = await load_inputs(c, input_cutoff=through, include_salary_history=True)
            _, _, baseline_salaries, _ = await load_inputs(c, input_cutoff=through)
            old = [dict(r) for r in await c.fetch("SELECT * FROM store_pnl_monthly ORDER BY company_name,period,source_site_code,category_code,data_kind")]
            hr = [dict(r) for r in await c.fetch("""
                SELECT company_name, period, count(*) AS rows, count(distinct site_code) AS stores,
                       sum(total_amount) AS total_net_vouchers,
                       sum(total_amount) filter(where site_code is not null) AS mapped_net_vouchers,
                       count(*) filter(where site_code is null) AS unmapped_rows,
                       coalesce(sum(total_amount) filter(where site_code is null),0) AS unmapped_net_vouchers
                FROM salary_history_estimation_inputs
                WHERE period <= $1 GROUP BY company_name,period ORDER BY company_name,period
            """, args.through)]
            source_hashes = [dict(r) for r in await c.fetch("SELECT DISTINCT source_sha256,batch_sha256 FROM salary_history_rows WHERE selected ORDER BY 1,2")]
        snapshots = dict(actual=[dict(r) for r in actual], gross=[dict(r) for r in gross],
                         salaries=[dict(r) for r in salaries], stores=[dict(r) for r in stores],
                         baseline_salaries=[dict(r) for r in baseline_salaries])
        candidates = {}
        for name, vat in [('baseline_current_inputs', False), ('salary_legacy_vat', False), ('salary_effective_vat_review_only', True)]:
            sales = normalize_sales(gross, effective_vat=vat)
            targets = all_missing_targets(actual, sales, input_cutoff=next_month)
            salary_input = baseline_salaries if name == 'baseline_current_inputs' else salaries
            estimates = [asdict(r) for r in build_estimates(actual, sales, salary_input, stores, targets, causal=False)]
            assert all(r['period'] <= through for r in estimates)
            assert len({(r['company_name'], r['period'], r['source_site_code'],r['category_code']) for r in estimates}) == len(estimates)
            candidates[name] = estimates
        assert [r for r in candidates['baseline_current_inputs'] if r['category_code'] != 'c3'] == [r for r in candidates['salary_legacy_vat'] if r['category_code'] != 'c3']
        periods = sorted({(r['company_name'],r['period']) for r in candidates['salary_legacy_vat']})
        controls = []
        for company, period in periods:
            controls.append(dict(company=company, period=period,
                previous=metrics([r for r in old if r['company_name']==company and r['period']==period and r['data_kind']=='estimated']),
                baseline_current_inputs=metrics([r for r in candidates['baseline_current_inputs'] if r['company_name']==company and r['period']==period]),
                salary_legacy_vat=metrics([r for r in candidates['salary_legacy_vat'] if r['company_name']==company and r['period']==period]),
                salary_effective_vat=metrics([r for r in candidates['salary_effective_vat_review_only'] if r['company_name']==company and r['period']==period])))
        metadata = dict(status='review_only', input_cutoff=through.isoformat(), output_through=args.through,
                        input_sha256=digest(snapshots), preimage_sha256=digest(old),
                        actuals_sha256=digest([r for r in old if r['data_kind']=='actual']),
                        source_hashes=source_hashes, salary_coverage=hr, controls=controls,
                        model_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [ROOT/'backend/scripts/estimate_store_pnl.py',ROOT/'backend/scripts/store_pnl_estimator_inputs.py',ROOT/'backend/scripts/store_pnl_salary_inputs.py']},
                        output_hashes={k:digest(v) for k,v in candidates.items()},
                        counts={k:len(v) for k,v in candidates.items()})
        for name, value in [('inputs', snapshots), ('preimage', old), ('review',metadata), *candidates.items()]:
            p = out / (name+'.json')
            p.write_text(encode(value),encoding='utf-8')
            p.chmod(0o600)
        print(encode(dict(status='review_only', counts=metadata['counts'], last_month=[r for r in controls if r['period']==through],
                          input_sha256=metadata['input_sha256'], directory=str(out))))
    finally:
        await c.close()


if __name__ == '__main__':
    asyncio.run(main())
