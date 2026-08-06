"""Pure validation for manager target edits."""

from __future__ import annotations

from typing import Any


def validate_unique_final_rows(rows: list[dict[str, Any]]) -> None:
    if len({row["site_code"] for row in rows}) != len(rows):
        raise ValueError("Aceeasi locatie apare de mai multe ori in salvare.")
