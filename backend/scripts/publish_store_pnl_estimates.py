"""Publish a sealed, owner-reviewed estimated-only P&L generation through DB guards."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path
from uuid import UUID

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
from db.connection import connect_database_url, verify_database_connection_authority
from scripts.store_pnl_estimator_inputs import load_inputs, normalize_sales
from scripts.estimate_store_pnl import build_estimates, all_missing_targets


def encode(value):
    return json.dumps(value, default=str, sort_keys=True, separators=(',', ':'))


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def semantic_inputs(value):
    return {key: sorted(encode(dict(row)) for row in rows) for key, rows in value.items()}


def load_review(directory: Path):
    def read(name):
        path = directory / (name + '.json')
        if path.is_symlink() or not path.is_file():
            raise ValueError('Review requires regular, nonsymlink evidence files')
        return path.read_bytes()

    raw_review = read('review')
    review = json.loads(raw_review)
    if review['status'] != 'review_only':
        raise ValueError('Expected readonly review evidence')
    name = 'salary_effective_vat_review_only'
    candidate_raw = read(name)
    input_raw = read('inputs')
    if sha(candidate_raw) != review['output_hashes'][name] or sha(input_raw) != review['input_sha256']:
        raise ValueError('Reviewed input/output checksum mismatch')
    if sha(read('preimage')) != review['preimage_sha256']:
        raise ValueError('Reviewed preimage checksum mismatch')
    for filename, expected in review['model_sha256'].items():
        path = (ROOT / filename).resolve()
        if not path.is_relative_to(ROOT.resolve()) or path.is_symlink() or sha(path.read_bytes()) != expected:
            raise ValueError('Estimator source changed after review')
    rows = json.loads(candidate_raw)
    scopes = [dict(company=c, period=p) for c, p in sorted({(r['company_name'], r['period']) for r in rows})]
    models = dict(review['model_sha256'])
    for filename in ('backend/services/fiscal_rules.py', 'backend/scripts/import_salary_records.py'):
        models[filename] = sha((ROOT / filename).read_bytes())
    manifest = dict(
        version=1, ruleset='effective-vat-hr-v1', scopes=scopes,
        through_month=review['input_cutoff'], input_sha256=review['input_sha256'],
        output_sha256=sha(candidate_raw), review_sha256=sha(raw_review),
        review_preimage_sha256=review['preimage_sha256'], model_sha256=models,
        source_hashes=review['source_hashes'], salary_coverage=review['salary_coverage'],
        limitations=['HR is net plus vouchers; c3 is modeled employer cost',
                     'Unmapped HR is not arbitrarily allocated; TL remains separate'],
    )
    return review, manifest, candidate_raw.decode(), json.loads(input_raw)


async def protected_hashes(c):
    result = {}
    for name, query in {
        'finance_actual': "SELECT to_jsonb(p) AS v FROM store_pnl_monthly p WHERE data_kind='actual'",
        'target_scenarios': 'SELECT to_jsonb(t) AS v FROM target_scenarios t',
        'target_rows': 'SELECT to_jsonb(t) AS v FROM target_scenario_rows t',
    }.items():
        # Names/queries are a fixed internal allowlist, never caller-controlled.
        result[name] = await c.fetchval("SELECT encode(sha256(convert_to(coalesce(jsonb_agg(v ORDER BY v::text),'[]'::jsonb)::text,'UTF8')),'hex') FROM (" + query + ') q')
    return result


async def publish(connection, args):
    if args.expected_manifest_sha is None or args.expected_revision is None or not args.approval_reference:
        raise ValueError('Publication requires exact manifest hash, revision and approval reference')
    web = await connect_database_url(dotenv_values(ROOT / '.env')['DATABASE_URL'], application_name='pnl-publication-verification')
    try:
        before = await protected_hashes(web)
        result = json.loads(await connection.fetchval(
            'SELECT publish_store_pnl_estimate($1,$2,$3,$4,$5)',
            args.publish or args.rollback, args.expected_manifest_sha,
            args.expected_revision, args.approval_reference, bool(args.rollback),
        ))
        after = await protected_hashes(web)
        result.update(protected_before=before, protected_after=after, protected_unchanged=before == after)
        if before != after:
            result['attention'] = 'Protected data changed concurrently; inspect before any further action'
        return result
    finally:
        await web.close()


async def run(args):
    worker = dotenv_values(ROOT / '.env.worker')
    connection = await connect_database_url(worker['DATABASE_URL'], application_name='pnl-estimate-publication')
    try:
        await verify_database_connection_authority(connection, 'operations')
        if args.publish or args.rollback:
            return await publish(connection, args)
        if not args.review_dir:
            raise ValueError('--review-dir is required for readonly verification or staging')
        review, manifest, candidate, saved_inputs = load_review(args.review_dir)
        scopes = encode(manifest['scopes'])
        cutoff = date.fromisoformat(manifest['through_month'])
        before = json.loads(await connection.fetchval('SELECT inspect_store_pnl_estimate_context($1::jsonb,$2)', scopes, cutoff))
        web = await connect_database_url(dotenv_values(ROOT / '.env')['DATABASE_URL'], application_name='pnl-review-input-revalidation')
        try:
            async with web.transaction(isolation='repeatable_read', readonly=True):
                actual, gross, salaries, stores = await load_inputs(web, input_cutoff=cutoff, include_salary_history=True)
                _, _, baseline, _ = await load_inputs(web, input_cutoff=cutoff)
                current = dict(actual=actual, gross=gross, salaries=salaries, stores=stores, baseline_salaries=baseline)
                if semantic_inputs(current) != semantic_inputs(saved_inputs):
                    raise ValueError('Model inputs changed after review; produce a fresh reviewed generation')
                preimage = [dict(r) for r in await web.fetch('SELECT * FROM store_pnl_monthly ORDER BY company_name,period,source_site_code,category_code,data_kind')]
                if sha(encode(preimage).encode()) != review['preimage_sha256']:
                    raise ValueError('Published P&L changed after review; refresh comparison before staging')
                source_hashes = [dict(r) for r in await web.fetch('SELECT DISTINCT source_sha256,batch_sha256 FROM salary_history_rows WHERE selected ORDER BY 1,2')]
                if source_hashes != review['source_hashes']:
                    raise ValueError('Selected HR source hashes changed after review')
            sales = normalize_sales(gross, effective_vat=True)
            next_month = date(cutoff.year + (cutoff.month == 12), cutoff.month % 12 + 1, 1)
            rebuilt = build_estimates(actual, sales, salaries, stores,
                all_missing_targets(actual, sales, input_cutoff=next_month), causal=False)
            if sorted(encode(asdict(r)) for r in rebuilt) != sorted(encode(r) for r in json.loads(candidate)):
                raise ValueError('Current estimator does not reproduce the reviewed candidate')
        finally:
            await web.close()
        after = json.loads(await connection.fetchval('SELECT inspect_store_pnl_estimate_context($1::jsonb,$2)', scopes, cutoff))
        if before != after:
            raise ValueError('Publication context changed during readonly verification')
        if not args.stage:
            return dict(status='verified_readonly', **after, scopes=len(manifest['scopes']), output_sha256=manifest['output_sha256'])
        manifest['approval_reference'] = args.approval_reference
        if not args.approval_reference or len(args.approval_reference.strip()) < 8:
            raise ValueError('Staging requires an owner approval reference')
        result = json.loads(await connection.fetchval('SELECT stage_store_pnl_estimate($1::jsonb,$2,$3,$4)',
            encode(manifest), candidate, after['context_sha256'], after['revision']))
        return dict(status='staged_not_published', **result)
    finally:
        await connection.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--review-dir', type=Path)
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument('--stage', action='store_true')
    actions.add_argument('--publish', type=UUID)
    actions.add_argument('--rollback', type=UUID)
    parser.add_argument('--expected-manifest-sha')
    parser.add_argument('--expected-revision', type=int)
    parser.add_argument('--approval-reference')
    parser.add_argument('--receipt', type=Path, required=True, help='New JSON evidence file; never overwritten')
    args = parser.parse_args()
    # Reserve receipt before any write, and preserve failure evidence.
    with args.receipt.open('x', encoding='utf-8') as receipt:
        args.receipt.chmod(0o600)
        try:
            result = asyncio.run(run(args))
        except Exception as exc:
            receipt.write(encode(dict(status='failed', error_type=type(exc).__name__)))
            raise
        receipt.write(encode(result))
    print(encode(result))


if __name__ == '__main__':
    main()
