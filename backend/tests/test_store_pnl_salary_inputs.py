from datetime import date
from decimal import Decimal

from scripts.store_pnl_salary_inputs import salary_inputs_by_source_location, prefer_reconciled_hr_allocations

PERIOD = date(2026, 4, 1)


def row(company, location, amount, site='WRONG'):
    return dict(company_name=company, location=location, period=PERIOD,
                site_code=site, amount=Decimal(amount))


def test_payroll_source_location_overrides_contaminated_site_without_changing_amounts():
    rows = [row('Mobiup', 'SUN PLAZA', '4371', 'CRFARENA'),
            row('Mobiup', 'SUN PLAZA', '8533', 'SUNPLZ'),
            row('Mobiup', 'PARK LAKE', '9654', 'CTCITYPRK')]
    result = salary_inputs_by_source_location(rows, [])
    assert {(r['site_code'], r['amount']) for r in result} == {
        ('SUNPLZ', Decimal('12904')), ('PRKLK', Decimal('9654'))}
    assert sum(r['amount'] for r in result) == sum(r['amount'] for r in rows)
    assert rows[0]['site_code'] == 'CRFARENA'


def test_same_location_label_is_resolved_within_each_company():
    result = salary_inputs_by_source_location([
        row('Mobiup', 'MEGA MALL', '100'), row('Mobicell', 'MEGA MALL', '200')], [])
    assert {(r['company_name'], r['site_code'], r['amount']) for r in result} == {
        ('Mobiup', 'MEGAMALL', Decimal('100')),
        ('Mobicell', 'MC-MEGAMALL', Decimal('200'))}


def test_unknown_ambiguous_and_team_leader_locations_are_not_guessed_or_allocated():
    stores = [dict(site_code='A', locatie='Location', firma='Mobiup'),
              dict(site_code='B', locatie='Location', firma='Mobiup')]
    assert salary_inputs_by_source_location([
        row('Mobiup', 'Unknown', '10', 'A'), row('Mobiup', 'Location', '20', 'B'),
        row('Mobiup', 'TEAM LEADER', '30', 'A')], stores) == []


def test_unique_exact_location_preserves_period_and_cents():
    stores = [dict(site_code='NEW', locatie='New Store', firma='Mobiup')]
    assert salary_inputs_by_source_location([row('Mobiup', 'New Store', '100.01'),
                                             row('Mobiup', 'New Store', '20.02')], stores) == [
        dict(company_name='Mobiup', period=PERIOD, site_code='NEW', amount=Decimal('120.03'))]


def test_reconciled_original_distribution_keeps_official_total_and_company_boundary():
    original = [dict(row('Mobiup', 'SUN PLAZA', '300'), row_count=2)]
    inputs = [dict(company_name='Mobiup', period=PERIOD, site_code='SUNPLZ', amount=Decimal('300')),
              dict(company_name='Mobicell', period=PERIOD, site_code='OTHER', amount=Decimal('20'))]
    archive = [dict(company_name='Mobiup', period=PERIOD, site_code='SUNPLZ', amount=Decimal('100'), row_count=1, source_count=1),
               dict(company_name='Mobiup', period=PERIOD, site_code='PRKLK', amount=Decimal('200'), row_count=1, source_count=1)]
    result = prefer_reconciled_hr_allocations(original, inputs, archive)
    assert sum(r['amount'] for r in result) == Decimal('320')
    assert next(r for r in result if r['site_code']=='SUNPLZ')['amount'] == Decimal('100')
    assert inputs[0]['amount'] == Decimal('300')


def test_partial_different_amount_or_multiple_source_history_never_replaces_official_input():
    original = [dict(row('Mobiup', 'SUN PLAZA', '300'), row_count=2)]
    inputs = [dict(company_name='Mobiup', period=PERIOD, site_code='SUNPLZ', amount=Decimal('300'))]
    for amount, count, sources in [('299.99', 2, 1), ('300', 1, 1), ('300', 2, 2)]:
        archive = [dict(company_name='Mobiup', period=PERIOD, site_code='PRKLK',
                        amount=Decimal(amount), row_count=count, source_count=sources)]
        assert prefer_reconciled_hr_allocations(original, inputs, archive) == inputs


def test_unallocated_hr_is_in_total_reconciliation_but_not_in_store_estimates():
    original = [dict(row('Mobiup', 'SUN PLAZA', '300'), row_count=2)]
    inputs = [dict(company_name='Mobiup', period=PERIOD, site_code='SUNPLZ', amount=Decimal('300'))]
    archive = [dict(company_name='Mobiup', period=PERIOD, site_code='SUNPLZ', amount=Decimal('200'), row_count=1, source_count=1),
               dict(company_name='Mobiup', period=PERIOD, site_code=None, amount=Decimal('100'), row_count=1, source_count=1)]
    assert prefer_reconciled_hr_allocations(original, inputs, archive) == [
        dict(company_name='Mobiup', period=PERIOD, site_code='SUNPLZ', amount=Decimal('200'))]
