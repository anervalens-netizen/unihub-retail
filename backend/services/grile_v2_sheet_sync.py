"""Single-writer, hash-based native Sheets publication for the September V2 pilot."""
from __future__ import annotations
import asyncio
import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from repositories.grile_earnings import read_earnings_sources
from services.grile_calendar import GrileCalendarService
from grile.earnings_projection import project_earnings
from services.grile_monthly import build_google_services
from services.grile_v2_sheet_render import render_requests

logger = logging.getLogger(__name__)
LOCK_KEY = 84620260914
FORMAT_VERSION = 'grile-v2-approved-20260914.1'
TEMPLATE_PATH = Path(__file__).with_name('grile_v2_sheet_template.json')


async def snapshots(pool, month, sites):
    source = await read_earnings_sources(pool, month)
    if not source.get('source') or not source['source'].get('cutoff_date'):
        raise ValueError('published_sales_cutoff_missing')
    calendar = GrileCalendarService.project_calendar(month, source['calendar'])
    earnings = project_earnings(calendar, source)
    async with pool.acquire() as conn:
        stores = {r['site_code']: dict(r) for r in await conn.fetch(
            'SELECT site_code,locatie,firma,regional FROM stores WHERE site_code=ANY($1::text[])', sites)}
    result = {}
    for site in sites:
        if site not in stores or site not in earnings.stores:
            raise ValueError('pilot_source_store_missing')
        agents = [a for a in earnings.agents if a.home_site_code == site]
        codes = {a.agent_code for a in agents}
        related = codes | {d.agent_code for d in calendar.days if d.site_code == site}
        result[site] = {
            'store': stores[site], 'month': month, 'cutoff': str(earnings.cutoff),
            'store_performance': earnings.stores[site].model_dump(mode='json'),
            'agents': [a.model_dump(mode='json') for a in agents],
            'calendar': {
                'roster': [r.model_dump(mode='json') for r in calendar.roster if r.agent_code in related],
                'days': [d.model_dump(mode='json') for d in calendar.days if d.site_code == site or d.agent_code in codes],
                'closures': [d.model_dump(mode='json') for d in calendar.closures if d.site_code == site],
                'store_hours': [d.model_dump(mode='json') for d in calendar.store_hours if d.site_code == site],
                'attendance_days': [d.model_dump(mode='json') for d in calendar.attendance_days if d.site_code == site],
                'attendance_by_store': [d.model_dump(mode='json') for d in calendar.attendance_by_store.get(site, [])],
            },
        }
    return result


def content_hash(snapshot):
    raw = json.dumps({'format': FORMAT_VERSION, 'source': snapshot}, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    return hashlib.sha256(raw.encode()).hexdigest()


async def _google(fn):
    # Shield an in-flight write: the advisory lock must remain held until it ends.
    job = asyncio.create_task(asyncio.to_thread(fn))
    try:
        return await asyncio.shield(job)
    except asyncio.CancelledError:
        await job
        raise


async def sync_pilot(pool):
    template = json.loads(TEMPLATE_PATH.read_text(encoding='utf-8'))
    result = {'updated': 0, 'unchanged': 0, 'failed': 0}
    async with pool.acquire() as fence:
        if not await fence.fetchval('SELECT pg_try_advisory_lock($1)', LOCK_KEY):
            return {'skipped': 'writer_active'}
        try:
            exports = [dict(r) for r in await fence.fetch('SELECT * FROM grile_v2_sheet_exports ORDER BY run_month,site_code')]
            if not exports:
                return result
            sheets, _drive = await _google(build_google_services)
            for month in sorted({r['run_month'] for r in exports}):
                mappings = [r for r in exports if r['run_month'] == month]
                try:
                    data = await snapshots(pool, month, [r['site_code'] for r in mappings])
                except Exception:
                    await fence.execute("UPDATE grile_v2_sheet_exports SET status='failed',last_error_at=now(),last_error_code='source_unavailable',last_error_message='Datele sursă nu au putut fi citite; ultima grilă validă se păstrează.',updated_at=now() WHERE run_month=$1", month)
                    raise
                for mapping in mappings:
                    site, file_id = mapping['site_code'], mapping['file_id']
                    snapshot = data[site]
                    digest = content_hash(snapshot)
                    if digest == mapping['published_hash']:
                        result['unchanged'] += 1
                        if mapping['status'] != 'succeeded':
                            await fence.execute("UPDATE grile_v2_sheet_exports SET status='succeeded',last_error_code=NULL,last_error_message=NULL,updated_at=now() WHERE id=$1", mapping['id'])
                        continue
                    await fence.execute("UPDATE grile_v2_sheet_exports SET source_hash=$2,status='running',last_attempt_at=now(),updated_at=now() WHERE id=$1", mapping['id'], digest)
                    try:
                        meta = await _google(lambda: sheets.spreadsheets().get(spreadsheetId=file_id, fields='sheets(properties,conditionalFormats,protectedRanges,merges)').execute())
                        at = datetime.now(ZoneInfo('Europe/Bucharest')).strftime('%d.%m.%Y %H:%M')
                        requests = render_requests(snapshot, template, meta, at)
                        # Verify DB connection/fence is still alive immediately before remote write.
                        await fence.fetchval('SELECT 1')
                        await _google(lambda: sheets.spreadsheets().batchUpdate(spreadsheetId=file_id, body={'requests':requests}).execute())
                        await fence.execute("UPDATE grile_v2_sheet_exports SET published_hash=$2,status='succeeded',last_success_at=now(),last_error_code=NULL,last_error_message=NULL,updated_at=now() WHERE id=$1 AND source_hash=$2", mapping['id'], digest)
                        result['updated'] += 1
                        logger.info('Grile V2 published month=%s site=%s', month, site)
                    except Exception as exc:
                        code = 'google_rate_limited' if getattr(getattr(exc,'resp',None),'status',None) == 429 else 'publication_failed'
                        await fence.execute("UPDATE grile_v2_sheet_exports SET status='failed',last_error_at=now(),last_error_code=$2,last_error_message='Publicare nereușită; se reîncearcă automat.',updated_at=now() WHERE id=$1", mapping['id'], code)
                        logger.error('Grile V2 publication failed month=%s site=%s type=%s',month,site,type(exc).__name__)
                        result['failed'] += 1
                        if code == 'google_rate_limited':
                            return result
                    # Keep comfortably below Sheets per-user write limits, also during first publication.
                    await asyncio.sleep(2)
            return result
        finally:
            await fence.execute('SELECT pg_advisory_unlock($1)', LOCK_KEY)


async def _main():
    from db.connection import init_db_pool, get_pool, close_db_pool
    await init_db_pool()
    try:
        print(json.dumps(await sync_pilot(await get_pool())), flush=True)
    finally:
        await close_db_pool()


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(_main())

