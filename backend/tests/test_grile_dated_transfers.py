from datetime import date
from decimal import Decimal as D
from unittest.mock import AsyncMock
import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from grile.calendar_models import RosterEntry, TransferInput
from grile.roster_history import home_on
from grile.earnings_projection import project_earnings
from services.grile_calendar import GrileCalendarService

def roster():
    return RosterEntry(month='2026-09', agent_code='A', home_site_code='S1', active=True, revision=2,
        transfers=[dict(effective_from='2026-09-03', home_site_code='S2', location_code_active_from='2026-09-09', roster_revision=2)])

def test_transfer_does_not_wait_for_pos_activation_or_rewrite_history():
    r = roster()
    assert home_on(r, date(2026,9,2)) == 'S1'
    assert home_on(r, date(2026,9,3)) == 'S2'
    assert home_on(r, date(2026,9,8)) == 'S2'

def test_activation_cannot_precede_transfer():
    with pytest.raises(ValidationError):
        TransferInput(home_site_code='S2', effective_from='2026-09-03', location_code_active_from='2026-09-02', expected_revision=2)

@pytest.mark.asyncio
async def test_transfer_rejects_wrong_month_before_any_write():
    with pytest.raises(HTTPException) as exc:
        await GrileCalendarService(AsyncMock()).save_transfer('2026-08', 'A', TransferInput(home_site_code='S2', effective_from='2026-09-03', expected_revision=2), 'manager')
    assert exc.value.status_code == 422

def test_transferred_agent_keeps_both_home_periods_and_receives_tl_sales_once():
    days = [dict(work_date=date(2026,9,n), site_code=s, agent_code='A', status='work', supplemental=extra, revision=1)
        for n,s,extra in [(1,'S1',False),(3,'S2',False),(4,'S1',True)]]
    calendar = GrileCalendarService.project_calendar('2026-09', dict(roster=[roster().model_dump()], days=days))
    sources = dict(source={'cutoff_date':date(2026,9,4)}, targets=[{'site_code':s,'target_value':D(1000)} for s in ['S1','S2']],
        sales=[{'site_code':d['site_code'],'sale_date':d['work_date'],'sales':D(1000)} for d in days],
        sim=[{'site_code':d['site_code'],'sale_date':d['work_date'],'quantity':2} for d in days],
        incentives={'A':D(25)}, incentives_complete=True)
    agent = project_earnings(calendar, sources).agents[0]
    assert [d.away for d in agent.days] == [False,False,True]
    assert agent.home_sales == 2000
    assert agent.home_target == 1500
    assert agent.home_commission == 460  # One monthly threshold bonus across both homes.
    assert agent.supplemental_pay == 150
    assert sum(d.sales for d in agent.days) == 3000
    assert agent.compensation.sim_quantity == 6
    assert agent.salary.sim_pay == 18
    assert agent.compensation.epay_under_50 == agent.compensation.epay_over_50 == 0
    assert agent.compensation.incentive == 25
    assert calendar.attendance[0].worked_minutes == 3 * 660
