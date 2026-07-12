from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_public_salary_surface_has_no_raw_identity_terms() -> None:
    paths = [
        ROOT / "src/api/salarii.ts",
        ROOT / "src/components/SalariiSubtab.tsx",
        ROOT / "src/components/SalaryDrawer.tsx",
        ROOT / "backend/routers/salarii.py",
    ]
    forbidden = ("cnp", "salary_cnp", "maskCnp", "/agents/history/")
    for path in paths:
        source = path.read_text(encoding="utf-8").lower()
        assert not any(term.lower() in source for term in forbidden), path


def test_public_response_keys_are_opaque() -> None:
    source = (ROOT / "backend/services/salarii.py").read_text(encoding="utf-8")
    assert '"person_id"' in source
    assert '"salary_cnp"' not in source
