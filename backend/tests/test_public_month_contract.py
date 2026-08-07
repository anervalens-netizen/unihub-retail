from __future__ import annotations

from pathlib import Path
import re

import pytest
from pydantic import TypeAdapter, ValidationError

from schemas.common import MonthStr


PUBLIC_STRING_MONTH_QUERY = re.compile(
    r"\b(?:month|selected_month|start_month|end_month):\s*str(?:\s*\|\s*None)?\s*=\s*Query"
)


def test_month_type_accepts_only_real_calendar_months() -> None:
    adapter = TypeAdapter(MonthStr)
    assert adapter.validate_python("2026-08") == "2026-08"
    for value in ("2026-00", "2026-13", "2026-8", "26-08", "invalid"):
        with pytest.raises(ValidationError):
            adapter.validate_python(value)


def test_public_router_month_queries_use_the_canonical_type() -> None:
    routers = Path(__file__).resolve().parents[1] / "routers"
    violations: list[str] = []
    for path in sorted(routers.glob("*.py")):
        source = path.read_text(encoding="utf-8")
        for match in PUBLIC_STRING_MONTH_QUERY.finditer(source):
            line = source.count("\n", 0, match.start()) + 1
            violations.append(f"{path.name}:{line}: {match.group(0)}")
    assert violations == []
