"""Append-only dated transfers fenced by the monthly roster revision."""
from repositories.grile_calendar import CalendarConflict, GrileCalendarRepository

async def save_transfer(pool, month, code, value, actor):
    async with pool.acquire() as conn:
        async with conn.transaction():
            old = await conn.fetchrow("SELECT * FROM grile_calendar_roster WHERE month=$1 AND agent_code=$2 FOR UPDATE", month, code)
            if not old or not old['active'] or not old['home_site_code']:
                raise CalendarConflict('Select an active store agent before transferring')
            if old['revision'] != value.expected_revision:
                raise CalendarConflict('Roster changed; reload before saving the transfer')
            await GrileCalendarRepository._store(conn, value.home_site_code)
            revision = old['revision'] + 1
            await conn.execute("""INSERT INTO grile_calendar_transfers
                (month,agent_code,effective_from,home_site_code,location_code_active_from,roster_revision,updated_by_sub)
                VALUES ($1,$2,$3,$4,$5,$6,$7)""", month, code, value.effective_from,
                value.home_site_code, value.location_code_active_from, revision, actor)
            await conn.execute("""UPDATE grile_calendar_roster SET revision=$3,updated_by_sub=$4,updated_at=now()
                WHERE month=$1 AND agent_code=$2""", month, code, revision, actor)
            # Existing physical attendance is evidence and remains unchanged.
            # Future edits validate against the home effective on that day.
            return await GrileCalendarRepository.read_on_connection(conn, month)
