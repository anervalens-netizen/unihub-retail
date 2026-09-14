from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch
from decimal import Decimal
import pytest
from grile.calendar_models import TransferInput
from grile.compensation_models import EpayInput
from repositories.grile_calendar import CalendarConflict
from repositories.grile_compensation import save_epay
from repositories.grile_transfers import save_transfer

class Connection:
    def __init__(self):
        self.fetchval = AsyncMock(side_effect=[True, 4])
        self.fetchrow = AsyncMock(return_value={'active':True,'home_site_code':'A','revision':4})
        self.execute = AsyncMock()
        self.rollback = False
    @asynccontextmanager
    async def transaction(self):
        try:
            yield
        except Exception:
            self.rollback = True
            raise

class Pool:
    def __init__(self, conn): self.conn=conn
    @asynccontextmanager
    async def acquire(self): yield self.conn

@pytest.mark.asyncio
async def test_epay_preserves_other_components_and_fences_conflicts():
    conn=Connection()
    await save_epay(Pool(conn),'2026-09','AG',EpayInput(epay_under_50=15,epay_over_50=0,expected_revision=4),'manager')
    query,*args=conn.fetchrow.await_args.args
    update=query.split('DO UPDATE SET')[1]
    assert all(field not in update for field in ['salary_base','vouchers','sim_quantity','incentive','adjustment'])
    assert args == ['2026-09','AG',15,0,'manager']
    conn=Connection()
    with pytest.raises(CalendarConflict):
        await save_epay(Pool(conn),'2026-09','AG',EpayInput(expected_revision=3),'manager')
    conn.fetchrow.assert_not_awaited()
    assert conn.rollback

@pytest.mark.asyncio
async def test_transfer_appends_history_without_rewriting_attendance_or_base():
    conn=Connection()
    value=TransferInput(home_site_code='B',effective_from='2026-09-10',location_code_active_from='2026-09-15',expected_revision=4)
    with patch('repositories.grile_transfers.GrileCalendarRepository._store',new=AsyncMock()), patch('repositories.grile_transfers.GrileCalendarRepository.read_on_connection',new=AsyncMock(return_value={})):
        await save_transfer(Pool(conn),'2026-09','AG',value,'manager')
    queries=[c.args[0] for c in conn.execute.await_args_list]
    assert 'INSERT INTO grile_calendar_transfers' in queries[0]
    assert 'grile_calendar_days' not in ''.join(queries)
    assert 'home_site_code' not in queries[1]
    assert conn.execute.await_args_list[0].args[-2:] == (5,'manager')

@pytest.mark.asyncio
async def test_stale_transfer_stops_before_writing():
    conn=Connection()
    with pytest.raises(CalendarConflict):
        await save_transfer(Pool(conn),'2026-09','AG',TransferInput(home_site_code='B',effective_from='2026-09-10',expected_revision=3),'manager')
    conn.execute.assert_not_awaited()
    assert conn.rollback
