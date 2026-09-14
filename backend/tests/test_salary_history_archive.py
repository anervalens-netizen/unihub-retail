import copy
import hashlib
import json
from decimal import Decimal
import pytest
from scripts.import_salary_history import prepare_row, load_plan


def source():
    return dict(schema_version=1,source_row_key='row1',period='2024-01',company='Mobiup',
        salary_amount='3000.00',meal_vouchers='300.00',total_amount='3300.00',
        value_status='valid',candidate_person_id=None,identity_status='missing_identifier',
        is_selected=True,pnl_eligible=True,already_recorded=False,existing_official_coverage=False,
        period_status='confirmed',version_status='unique_or_equivalent',scope='retail',
        value_issues=[],identity_issues=[],inclusion_status='selected',full_name='Test Person',
        source_sha256='a'*64,source_row=2,source_file='test.xls',source_sheet='January')


def test_unresolved_identity_preserves_value_without_person_assignment():
    row=prepare_row(source(),'b'*64)
    assert row['candidate_person_id'] is None
    assert row['total_amount']==Decimal('3300.00')
    assert row['pnl_eligible']


@pytest.mark.parametrize('change',[{'scope':'channel_vodafone'}, {'period_status':'conflict'},
    {'version_status':'conflicting_versions'}, {'existing_official_coverage':True},
    {'is_selected':False}, {'company':None}])
def test_ambiguous_or_existing_month_never_enters_estimates(change):
    row=source();row.update(change)
    with pytest.raises(ValueError):
        prepare_row(row,'b'*64)


def test_conflicting_identity_cannot_be_linked_even_with_valid_opaque_id():
    row=source();row['candidate_person_id']='sp1_'+'c'*64
    with pytest.raises(ValueError,match='Unverified person'):
        prepare_row(row,'b'*64)


@pytest.mark.parametrize('value',['NaN','Infinity','3300.001','3301.00'])
def test_invalid_or_inconsistent_amounts_rejected(value):
    row=source();row['total_amount']=value
    with pytest.raises(ValueError):prepare_row(row,'b'*64)


def test_source_duplicates_fail_before_database(tmp_path):
    row=source();path=tmp_path/'plan.jsonl'
    path.write_text(json.dumps(row)+'\n'+json.dumps(row)+'\n')
    with pytest.raises(ValueError,match='Duplicate source row'):
        load_plan(path,hashlib.sha256(path.read_bytes()).hexdigest())


def test_changed_manifest_fails_before_database(tmp_path):
    path=tmp_path/'plan.jsonl';path.write_text('{}\n')
    with pytest.raises(ValueError,match='hash changed'):
        load_plan(path,'d'*64)
