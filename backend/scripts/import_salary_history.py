#!/usr/bin/env python3
"""Archive reviewed historical evidence; never writes official payroll or identity.

The source plan is private, immutable and hash-pinned. Replays are idempotent;
a changed classification of an existing source row requires a future review flow.
"""
from __future__ import annotations
import argparse
import asyncio
import hashlib
import json
import os
import re
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv
from db.connection import connect_database_url, verify_database_connection_authority

COLUMNS = ('source_row_key','batch_sha256','payload_sha256','period','company_name',
 'full_name','location','site_code','salary_amount','meal_vouchers','total_amount',
 'candidate_person_id','identity_status','review_reasons','selected','pnl_eligible',
 'already_recorded','source_file','source_sha256','source_sheet','source_row')

def money(value):
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError('Amounts must be decimal strings')
    try:
        number = Decimal(value)
    except InvalidOperation:
        raise ValueError('Invalid amount') from None
    if not number.is_finite() or abs(number) > Decimal('100000000') or number != number.quantize(Decimal('.01')):
        raise ValueError('Invalid amount precision/range')
    return number

def prepare_row(row, batch_hash):
    if row.get('schema_version') != 1:
        raise ValueError('Unsupported row schema')
    period = row.get('period')
    if period is not None and not re.fullmatch(r'(19|20)\d{2}-(0[1-9]|1[0-2])',period):
        raise ValueError('Invalid period')
    company = row.get('company')
    if company not in (None,'Mobiup','Mobicell'):
        raise ValueError('Invalid company')
    amounts = [money(row.get(k)) for k in ('salary_amount','meal_vouchers','total_amount')]
    if row.get('value_status') == 'valid' and (None in amounts or amounts[0]+amounts[1] != amounts[2]):
        raise ValueError('Amount control mismatch')
    person = row.get('candidate_person_id')
    if person and (row.get('identity_status') != 'verified_existing_identity' or not re.fullmatch(r'sp1_[0-9a-f]{64}',person)):
        raise ValueError('Unverified person link')
    selected = row.get('is_selected') is True
    eligible = row.get('pnl_eligible') is True
    already = bool(row.get('already_recorded') or row.get('existing_official_coverage'))
    if eligible and not (selected and row.get('period_status') == 'confirmed' and company
        and row.get('value_status') == 'valid' and row.get('version_status') == 'unique_or_equivalent'
        and row.get('scope') == 'retail' and not already):
        raise ValueError('Unsafe estimation eligibility')
    reasons = [str(x) for k in ('value_issues','identity_issues') for x in row.get(k,[])]
    if row.get('inclusion_status') != 'selected':
        reasons.append(str(row.get('inclusion_status')))
    if row.get('scope') != 'retail':
        reasons.append(str(row.get('scope')))
    name = row.get('full_name')
    if not isinstance(name,str) or not name.strip() or len(name)>500:
        raise ValueError('Missing/oversized name')
    source_sha = row.get('source_sha256','')
    if not re.fullmatch('[0-9a-f]{64}',source_sha):
        raise ValueError('Invalid source hash')
    if not isinstance(row.get('source_row'),int) or row['source_row']<1:
        raise ValueError('Invalid source row')
    result = dict(zip(COLUMNS, [row['source_row_key'],batch_hash,'',period,company,
        name,row.get('location'),row.get('site_code'),*amounts,person,
        'verified_existing' if person else row['identity_status'],reasons,selected,
        eligible,already,Path(row['source_file']).name,source_sha,row['source_sheet'],row['source_row']]))
    result['payload_sha256'] = hashlib.sha256(json.dumps(result,sort_keys=True,default=str).encode()).hexdigest()
    return result

def load_plan(path, expected):
    payload=path.read_bytes()
    digest=hashlib.sha256(payload).hexdigest()
    if digest != expected:
        raise ValueError('Plan hash changed')
    raw=[json.loads(line) for line in payload.decode().splitlines() if line.strip()]
    if not 0<len(raw)<=100000:
        raise ValueError('Invalid plan size')
    rows=[prepare_row(r,digest) for r in raw]
    if len({r['source_row_key'] for r in rows})!=len(rows):
        raise ValueError('Duplicate source row key')
    if len({(r['source_sha256'],r['source_sheet'],r['source_row']) for r in rows})!=len(rows):
        raise ValueError('Duplicate source provenance')
    for src,sha in {(r['source_path'],r['source_sha256']) for r in raw}:
        resolved=Path(src).resolve()
        if not resolved.is_relative_to(Path('/opt/Mobiup/docs/comisioane').resolve()):
            raise ValueError('Source outside private archive')
        if hashlib.sha256(resolved.read_bytes()).hexdigest()!=sha:
            raise ValueError('Source hash changed')
    return digest,rows

async def run(args):
    digest,rows=load_plan(args.plan,args.expected_sha256)
    root=Path(__file__).resolve().parents[2]
    load_dotenv(root/'.env.migrations')
    conn=await connect_database_url(os.environ['MIGRATION_DATABASE_URL'],application_name='salary-history-archive')
    try:
        await verify_database_connection_authority(conn, 'migrate')
        async with conn.transaction():
            await conn.execute('SET LOCAL ROLE unihub_schema_owner')
            await conn.execute("SELECT pg_advisory_xact_lock(hashtextextended('salary-history-archive',0))")
            # No names or private identifiers are printed. Match existing opaque identities only.
            existing=await conn.fetch('SELECT DISTINCT person_id,full_name FROM salary_records')
            import unicodedata
            def norm(s):
                return re.sub(r'[^A-Z0-9]+',' ',unicodedata.normalize('NFKD',s).encode('ascii','ignore').decode().upper()).strip()
            names={}
            for entry in existing:
                names.setdefault(entry['person_id'],set()).add(norm(entry['full_name']))
            for row in rows:
                pid=row['candidate_person_id']
                if pid and names.get(pid)!={norm(row['full_name'])}:
                    raise ValueError('Existing identity no longer matches uniquely')
            old=await conn.fetch('SELECT source_row_key,payload_sha256 FROM salary_history_rows')
            hashes={r['source_row_key']:r['payload_sha256'] for r in old}
            if any(r['source_row_key'] in hashes and hashes[r['source_row_key']]!=r['payload_sha256'] for r in rows):
                raise ValueError('Existing history conflicts; explicit new review required')
            new=[r for r in rows if r['source_row_key'] not in hashes]
            if args.apply:
                await conn.execute('INSERT INTO salary_history_batches(manifest_sha256,row_count,applied_by) VALUES($1,$2,$3) ON CONFLICT DO NOTHING',digest,len(rows),args.applied_by)
                sql='INSERT INTO salary_history_rows('+','.join(COLUMNS)+') VALUES('+','.join('$'+str(i) for i in range(1,len(COLUMNS)+1))+')'
                await conn.executemany(sql,[tuple(r[k] for k in COLUMNS) for r in new])
            print(json.dumps({'mode':'applied' if args.apply else 'dry_run','plan_sha256':digest,'rows':len(rows),'new_rows':len(new),'existing_rows':len(rows)-len(new),'linked_rows':sum(bool(r['candidate_person_id']) for r in rows),'eligible_rows':sum(r['pnl_eligible'] for r in rows)}))
    finally:
        await conn.close()

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--plan',type=Path,required=True)
    p.add_argument('--expected-sha256',required=True)
    p.add_argument('--applied-by',required=True)
    p.add_argument('--apply',action='store_true')
    asyncio.run(run(p.parse_args()))
