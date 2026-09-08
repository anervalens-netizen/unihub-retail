"""Exercise the actual release gate's final-ledger assertion."""
import ast
import hashlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _gate():
    source = (ROOT / 'scripts/run_release_a_schema_gate.sh').read_text()
    embedded = source.rsplit('"$PYTHON" - <<\'PY\'\n', 1)[1].rsplit('\nPY', 1)[0]
    tree = ast.parse(embedded)
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'verify_final_ledger')
    migrations = json.loads((ROOT / 'backend/db/migrations/manifest.json').read_text())['migrations']
    ledger = [{'filename': name, 'checksum': checksum} for name, checksum in sorted(migrations.items())]
    digest = hashlib.sha256(json.dumps(ledger, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    namespace = {'expected_ledger': ledger, 'expected_ledger_sha256': digest}
    exec(compile(ast.Module(body=[function], type_ignores=[]), '<actual release gate>', 'exec'), namespace)
    return namespace['verify_final_ledger'], {'migration_count': len(ledger), 'last_migration': ledger[-1]['filename'], 'ledger_sha256': digest}


def test_accepts_complete_candidate_ledger():
    verify, state = _gate()
    verify(state)


@pytest.mark.parametrize('field,value', [
    ('migration_count', 69),
    ('last_migration', '069_ai_cohort_and_transactional_outbox.sql'),
    ('ledger_sha256', '0' * 64),
])
def test_rejects_incomplete_or_modified_ledger(field, value):
    verify, state = _gate()
    state[field] = value
    with pytest.raises(SystemExit, match='differs from candidate manifest'):
        verify(state)
