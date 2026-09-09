from decimal import Decimal as D
from grile.base_salary import base_salary
from grile.compensation_models import CompensationInput
from test_grile_earnings import sources, project
import pytest

@pytest.mark.parametrize('site,expected', [('PRKLK',2600),('CTCITYPRK',2600),('CJIULMALL',2600),('MCRFBAL',2600),('TMACUH',2400),('ORAUCH',2400)])
def test_owner_city_rule_and_balotesti_exception(site, expected):
    assert base_salary(site) == expected


def test_missing_manual_values_do_not_create_a_complete_salary():
    agent = project(sources()).agents[0]
    assert agent.compensation.salary_base == 2400
    assert agent.compensation.vouchers == 480
    assert agent.salary.current_total is None
    assert agent.salary.sim_pay is None


def test_v1_components_are_counted_once_and_input_changes_change_revision():
    data = sources()
    data['compensation'] = [dict(month='2026-09',agent_code='AG1',salary_base=9999,vouchers=480,
        sim_quantity=2,epay_under_50=1,epay_over_50=2,incentive=100,adjustment=-10,revision=1)]
    result = project(data); agent = result.agents[0]
    assert agent.salary.sim_pay == 6 and agent.salary.epay_pay == 29
    assert agent.salary.commission_total == 207
    assert agent.salary.current_total == 3227
    assert agent.salary.potential_120 == 3651
    data['compensation'][0]['incentive'] = 101
    assert project(data).projection_revision != result.projection_revision


def test_daily_remaining_thresholds_and_forecast_use_scheduled_days():
    data=sources();data['source']['cutoff_date']=data['calendar']['days'][0]['work_date']
    result=project(data);p=result.agents[0].performance
    assert p.worked_days == 1 and p.scheduled_days == 2
    assert p.average == 800 and p.forecast == 1600
    assert p.daily_80 == 800 and p.daily_100 == 1200 and p.daily_120 == 1600

@pytest.mark.parametrize('payload', [{'sim_quantity':-1},{'epay_under_50':1.5},{'salary_base':'NaN'},{'incentive':'0.001'}])
def test_invalid_manual_inputs_are_rejected(payload):
    with pytest.raises(ValueError): CompensationInput(expected_revision=0,**payload)
