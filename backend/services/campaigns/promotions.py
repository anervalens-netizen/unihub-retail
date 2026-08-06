"""Promotion evaluation boundary for the Campaigns service."""

from __future__ import annotations

from typing import Any

import asyncpg

from services.promotion_evaluation import PromotionEvaluation, evaluate_promotion


async def compute_promotion_result(
    conn: asyncpg.Connection,
    *,
    month: str,
    definition: dict[str, Any],
    firma: str | None,
    regional: str | None,
    asm: str | None,
    site_code: str | None,
    agent: str | None,
    current_scope: bool = False,
    include_closed_stores: bool = False,
) -> PromotionEvaluation:
    return await evaluate_promotion(
        conn,
        month=month,
        definition=definition,
        firma=firma,
        regional=regional,
        asm=asm,
        site_code=site_code,
        agent=agent,
        current_scope=current_scope,
        include_closed_stores=include_closed_stores,
    )
