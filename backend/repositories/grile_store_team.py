"""Replace a store pair atomically, retaining dated history and attendance."""
from datetime import date
from grile.roster_history import home_on
from grile.calendar_projection import project_calendar
from repositories.grile_calendar import CalendarConflict, GrileCalendarRepository


def _validate_team_change(calendar, site, value, candidate_codes):
    roster = {r.agent_code: r for r in calendar.roster}
    selected = set(value.agent_codes)
    for code in selected:
        old = roster.get(code)
        if old and (not old.active or old.home_site_code == 'TL'):
            raise CalendarConflict("Select an active physical-store agent")
        if old is None and code not in candidate_codes:
            raise CalendarConflict("Agent is not in the confirmed candidate catalog")
    if any(t.effective_from > value.effective_from and t.home_site_code == site
           for r in calendar.roster if r.agent_code not in selected for t in r.transfers):
        raise CalendarConflict("A later transfer enters this store; review it before replacing the team")
    outgoing = {r.agent_code for r in calendar.roster if r.active and home_on(r, value.effective_from) == site} - selected
    return roster, selected, outgoing


async def save_store_team(pool, month, site, value, actor, candidate_codes):
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Include inserts and edits in the same fence; normal writes take row locks.
            await conn.execute("LOCK TABLE grile_calendar_roster IN SHARE ROW EXCLUSIVE MODE")
            await conn.fetch("SELECT agent_code FROM grile_calendar_roster WHERE month=$1 ORDER BY agent_code FOR UPDATE", month)
            raw = await GrileCalendarRepository.read_on_connection(conn, month)
            calendar = project_calendar(month, raw)
            if calendar.projection_revision != value.expected_revision:
                raise CalendarConflict("Calendar changed; reload before saving the team")
            await GrileCalendarRepository._store(conn, site)
            roster, selected, outgoing = _validate_team_change(calendar, site, value, candidate_codes)
            for code in sorted(selected | outgoing):
                old = roster.get(code)
                destination = site if code in selected else None
                if old and home_on(old, value.effective_from) == destination:
                    continue
                # A future event at this store could silently create a third home agent.
                if old and any(t.effective_from > value.effective_from for t in old.transfers):
                    raise CalendarConflict("Agent has a later transfer; review that transfer before replacing the team")
                revision = old.revision if old else 1
                if old is None:
                    await conn.execute("""INSERT INTO grile_calendar_roster
                        (month,agent_code,home_site_code,active,revision,updated_by_sub)
                        VALUES ($1,$2,$3,true,1,$4)""", month, code, site, actor)
                    if value.effective_from > date.fromisoformat(month+'-01'):
                        await conn.execute("""INSERT INTO grile_calendar_transfers
                            (month,agent_code,effective_from,home_site_code,roster_revision,updated_by_sub)
                            VALUES ($1,$2,$3,NULL,$4,$5)""", month, code, date.fromisoformat(month+'-01'), revision, actor)
                revision += 1
                await conn.execute("""INSERT INTO grile_calendar_transfers
                    (month,agent_code,effective_from,home_site_code,location_code_active_from,roster_revision,updated_by_sub)
                    VALUES ($1,$2,$3,$4,$5,$6,$7)""", month, code, value.effective_from, destination,
                    value.location_code_active_from if destination else None, revision, actor)
                await conn.execute("""UPDATE grile_calendar_roster SET revision=$3,updated_by_sub=$4,updated_at=now()
                    WHERE month=$1 AND agent_code=$2""", month, code, revision, actor)
            return await GrileCalendarRepository.read_on_connection(conn, month)
