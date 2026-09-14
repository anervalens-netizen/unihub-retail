from unittest.mock import AsyncMock, patch
from types import SimpleNamespace
from datetime import date
import pytest
from pydantic import ValidationError
from grile.calendar_models import StoreTeamInput, RosterEntry, TransferEntry
from grile.roster_history import home_on
from repositories.grile_store_team import save_store_team
from repositories.grile_calendar import CalendarConflict
from test_grile_manager_writes import Connection, Pool

def payload(revision='a'*64):
    return StoreTeamInput(agent_codes=['A1','B1'],effective_from='2026-09-12',expected_revision=revision)

def roster(code,home):
    return RosterEntry(month='2026-09',agent_code=code,home_site_code=home,active=True,revision=3)

@pytest.mark.asyncio
async def test_pair_keeps_history_and_releases_outgoing_atomically():
    conn=Connection(); conn.fetch=AsyncMock(return_value=[])
    calendar=SimpleNamespace(projection_revision='a'*64,roster=[roster('A1','A'),roster('A2','A'),roster('B1','B')])
    with patch('repositories.grile_store_team.GrileCalendarRepository.read_on_connection',new=AsyncMock(return_value={})), patch('repositories.grile_store_team.GrileCalendarRepository._store',new=AsyncMock()), patch('services.grile_calendar.GrileCalendarService.project_calendar',return_value=calendar):
        await save_store_team(Pool(conn),'2026-09','A',payload(),'manager',set())
    events=[c.args for c in conn.execute.await_args_list if 'INSERT INTO grile_calendar_transfers' in c.args[0]]
    assert [(c[2],c[4]) for c in events] == [('A2',None),('B1','A')]
    assert all('grile_calendar_days' not in c.args[0] for c in conn.execute.await_args_list)
    old=calendar.roster[1]
    old.transfers=[TransferEntry(effective_from='2026-09-12',home_site_code='UNASSIGNED',roster_revision=4)]
    assert home_on(old,date(2026,9,11))=='A'
    assert home_on(old,date(2026,9,12))=='UNASSIGNED'

@pytest.mark.asyncio
async def test_stale_pair_rolls_back_without_any_assignment_write():
    conn=Connection();conn.fetch=AsyncMock(return_value=[])
    with patch('repositories.grile_store_team.GrileCalendarRepository.read_on_connection',new=AsyncMock(return_value={})), patch('services.grile_calendar.GrileCalendarService.project_calendar',return_value=SimpleNamespace(projection_revision='b'*64)):
        with pytest.raises(CalendarConflict):
            await save_store_team(Pool(conn),'2026-09','A',payload(),'manager',set())
    assert conn.rollback
    assert len(conn.execute.await_args_list)==1  # lock only

def test_pair_rejects_duplicate_agent():
    with pytest.raises(ValidationError):
        StoreTeamInput(agent_codes=['A','A'],effective_from='2026-09-12',expected_revision='a'*64)
