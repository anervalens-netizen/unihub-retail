"""Revision-fenced provisional compensation edits by confirmed agent code."""
import asyncpg
from grile.compensation_models import CompensationInput
from grile.base_salary import base_salary
from repositories.grile_calendar import CalendarConflict

async def save_compensation(pool: asyncpg.Pool, month: str, agent: str, value: CompensationInput, actor: str):
    async with pool.acquire() as conn:
        async with conn.transaction():
            roster = await conn.fetchrow('SELECT active,home_site_code FROM grile_calendar_roster WHERE month=$1 AND agent_code=$2 FOR UPDATE', month, agent)
            if not roster or not roster['active']:
                raise CalendarConflict('Confirm the active agent before editing compensation')
            home = roster['home_site_code'] or 'TL'
            if home != 'TL' and value.salary_base is not None and value.salary_base != base_salary(home):
                raise CalendarConflict('Base salary is fixed by the home store city rule')
            old = await conn.fetchval('SELECT revision FROM grile_calendar_compensation WHERE month=$1 AND agent_code=$2', month, agent)
            if (old or 0) != value.expected_revision:
                raise CalendarConflict('Compensation changed; reload before saving')
            return await conn.fetchrow('''INSERT INTO grile_calendar_compensation
                (month,agent_code,salary_base,vouchers,sim_quantity,epay_under_50,epay_over_50,incentive,adjustment,updated_by_sub)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
                ON CONFLICT (month,agent_code) DO UPDATE SET salary_base=$3,vouchers=$4,sim_quantity=$5,
                epay_under_50=$6,epay_over_50=$7,incentive=$8,adjustment=$9,updated_by_sub=$10,
                revision=grile_calendar_compensation.revision+1,updated_at=now()
                RETURNING month,agent_code,salary_base,vouchers,sim_quantity,epay_under_50,epay_over_50,incentive,adjustment,revision''',
                month,agent,value.salary_base,value.vouchers,value.sim_quantity,value.epay_under_50,value.epay_over_50,value.incentive,value.adjustment,actor)
