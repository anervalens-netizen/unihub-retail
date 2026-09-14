"""Revision-fenced manager targets, with an append-only change history."""
from repositories.grile_calendar import CalendarConflict


async def save_target(pool, month, agent, value, actor):
    async with pool.acquire() as conn:
        async with conn.transaction():
            roster = await conn.fetchrow(
                'SELECT active, home_site_code FROM grile_calendar_roster WHERE month=$1 AND agent_code=$2 FOR UPDATE',
                month, agent,
            )
            if not roster or not roster['active']:
                raise CalendarConflict('Confirmă agentul activ înainte de modificarea targetului.')
            # TL shared accounts do not carry an individual monthly target.
            if not roster['home_site_code']:
                raise CalendarConflict('Conturile TL nu au target individual de magazin.')
            old = await conn.fetchrow(
                'SELECT mode, manual_target, revision FROM grile_agent_target_settings WHERE month=$1 AND agent_code=$2',
                month, agent,
            )
            if (old['revision'] if old else 0) != value.expected_revision:
                raise CalendarConflict('Targetul a fost modificat. Reîncarcă grila înainte de salvare.')
            row = await conn.fetchrow('''INSERT INTO grile_agent_target_settings
                (month, agent_code, mode, manual_target, updated_by_sub)
                VALUES ($1,$2,$3,$4,$5)
                ON CONFLICT (month,agent_code) DO UPDATE SET mode=$3, manual_target=$4,
                    revision=grile_agent_target_settings.revision+1, updated_by_sub=$5, updated_at=now()
                RETURNING month,agent_code,mode,manual_target,revision''',
                month, agent, value.mode, value.manual_target, actor,
            )
            await conn.execute('''INSERT INTO grile_agent_target_events
                (month,agent_code,revision,old_mode,old_target,new_mode,new_target,actor)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8)''',
                month, agent, row['revision'], old['mode'] if old else 'automatic',
                old['manual_target'] if old else None, value.mode, value.manual_target, actor,
            )
            return dict(row)
