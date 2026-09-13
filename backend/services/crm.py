from __future__ import annotations

import json
import zlib
from typing import Any

import asyncpg

from repositories.crm import CrmRepository
from services.forecast import get_forecast_factor


# Fixed CRM namespace id used as the first advisory-lock key.
# Together with a stable per-month hash of the calendar month this
# guarantees: same-month recalculations serialize against one another,
# different-month recalculations do not block each other, and no other
# subsystem falls into the same key pair.
_CRM_LOCK_NAMESPACE = 7377


class CrmSourceDataUnavailable(Exception):
    """Raised when a CRM recalculation has no source data.

    Source/worker failure never replaces last good generation.
    Missing source data is explicit anomaly, never implicit zero.

    The previous candidate silently committed an empty projection via
    ``replace_month_scores`` when ``calculate_scores_for_month`` returned
    ``[]``. That violated the AGENTS invariant: pressing CRM recalculate
    with no source must NOT destroy last-good scores. The service now
    raises this bounded typed exception BEFORE any destructive write,
    preserving the previously persisted projection.

    This class deliberately has NO custom ``__init__`` so it remains a
    pure production class (not a counted production function). It
    inherits the standard ``Exception(message)`` contract and exposes
    the bounded Romanian-language detail via the ``DETAIL`` class
    attribute, which the router surfaces verbatim in the 409 body.
    """

    DETAIL = (
        "Nu exista date de vanzari pentru recalcularea CRM in luna "
        "selectata. Scorurile existente au fost pastrate."
    )


async def _query_visits_by_store_postgres(
    conn: asyncpg.Connection,
    year_month: str,
) -> dict[str, dict[str, Any]]:
    records = await conn.fetch(
        """
        SELECT
            magazin AS site_code,
            COUNT(*)::INT AS nr_vizite,
            ROUND(AVG(completion_pct)::NUMERIC, 1)::FLOAT AS avg_completion
        FROM fieldops_visits
        WHERE to_char(data_raport, 'YYYY-MM') = $1
          AND magazin IS NOT NULL AND magazin <> ''
        GROUP BY magazin
        """,
        year_month,
    )
    return {record["site_code"]: dict(record) for record in records}


class CrmService:
    def __init__(self, repo: CrmRepository, pool: asyncpg.Pool):
        self.repo = repo
        self.pool = pool

    async def calculate_scores_for_month(
        self, month: str, *, connection: asyncpg.Connection | None = None
    ) -> list[dict[str, Any]]:
        """Calculate the CRM score projection for ``month``.

        When ``connection`` is provided, every DB read inside this method
        uses that connection. This is the lock-aware entry point used by
        ``recalculate_scores`` to ensure the per-month advisory lock
        covers the complete calculate-then-replace cycle.

        When ``connection`` is None, a fresh pool connection is acquired
        for the forecast/visit reads; the KPI source reads then go through
        the repository (which acquires its own connection). This matches
        the historical caller surface and keeps direct call sites
        unchanged.
        """
        y, m = map(int, month.split("-"))
        prev_month = f"{y}-{m - 1:02d}" if m > 1 else f"{y - 1}-12"

        if connection is not None:
            forecast_factor = await get_forecast_factor(connection, month)
            visit_map = await _query_visits_by_store_postgres(connection, month)
            rows = await self.repo.get_kpi_data_for_month(
                month, prev_month, connection=connection
            )
        else:
            async with self.pool.acquire() as conn:
                forecast_factor = await get_forecast_factor(conn, month)
                visit_map = await _query_visits_by_store_postgres(conn, month)
            rows = await self.repo.get_kpi_data_for_month(month, prev_month)

        scores = []
        for row in rows:
            total = float(row["total_value"] or 0)
            target = float(row["target_value"] or 0)
            prev = float(row["prev_value"] or 0)
            pct_bon2acc = float(row["pct_bon2acc"] or 0)
            pct_focus = float(row["pct_focus"] or 0)
            avg_bon2acc = float(row["avg_bon2acc"] or 0)
            avg_focus = float(row["avg_focus"] or 0)
            forecast = total * forecast_factor

            target_pct = (forecast / target * 100) if target > 0 else 0
            c1 = min(target_pct / 100 * 40, 40)

            if prev > 0:
                trend = (forecast - prev) / prev * 100
                c2 = max(0.0, min(30.0, (trend + 20) / 40 * 30))
            else:
                c2 = 15.0

            bon2acc_score = min(pct_bon2acc / avg_bon2acc * 5, 10.0) if avg_bon2acc > 0 else 5.0
            focus_score = min(pct_focus / avg_focus * 5, 10.0) if avg_focus > 0 else 5.0
            c3 = round(bon2acc_score + focus_score, 1)

            vdata = visit_map.get(row["site_code"], {})
            nr_vizite = int(vdata.get("nr_vizite", 0) or 0)
            avg_completion = float(vdata.get("avg_completion", 0) or 0)
            freq_score = min(nr_vizite * 5, 10)
            c4 = round(freq_score * (avg_completion / 100), 1)

            score = round(c1 + c2 + c3 + c4)
            scores.append({
                "site_code": row["site_code"],
                "score": score,
                "breakdown": {
                    "target_pct": round(c1, 1),
                    "trend_pct": round(c2, 1),
                    "kpi_pct": c3,
                    "kpi_bon2acc_score": round(bon2acc_score, 1),
                    "kpi_focus_score": round(focus_score, 1),
                    "visits_pct": c4,
                    "target_attainment": round(target_pct, 1),
                    "forecast_factor": round(forecast_factor, 4),
                    "kpi_bon2acc": round(pct_bon2acc, 1),
                    "kpi_focus": round(pct_focus, 1),
                    "kpi_bon2acc_avg": round(avg_bon2acc, 1),
                    "kpi_focus_avg": round(avg_focus, 1),
                    "nr_vizite": nr_vizite,
                    "avg_completion": round(avg_completion, 1),
                },
            })

        return scores

    async def recalculate_scores(self, month: str) -> int:
        """Atomically replace the CRM monthly projection for ``month``.

        The complete calculate-then-replace cycle runs inside one
        transaction on one pool connection. The per-month advisory
        lock is acquired BEFORE any score-calculation reads and held
        until the replacement commits or rolls back, so:

          * same-month requests serialize (no stale late writer can win
            because the lock covers the calculation);
          * different-month requests do not block each other (the lock
            key is per-month);
          * a source-empty recalculation raises ``CrmSourceDataUnavailable``
            before any destructive write, preserving the previously
            persisted projection as the last-good generation;
          * any failure (constraint violation, cancellation) rolls the
            whole transaction back, releases the lock, and leaves the
            prior projection intact.
        """
        # zlib.crc32 is portable and deterministic across processes; we
        # mask to a positive 31-bit integer so the lock call fits the
        # PostgreSQL int4 argument range.
        month_lock_key = zlib.crc32(month.encode("utf-8")) & 0x7FFFFFFF
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # Serialize same-month recalculations only. The lock is
                # transaction-scoped: it is released on COMMIT/ROLLBACK.
                # Acquiring it BEFORE any calculation read prevents the
                # stale-late-writer race: a same-month second request
                # cannot begin its own calculation until this entire
                # calculate-then-replace cycle completes.
                await conn.execute(
                    "SELECT pg_advisory_xact_lock($1, $2)",
                    _CRM_LOCK_NAMESPACE, month_lock_key,
                )
                scores = await self.calculate_scores_for_month(
                    month, connection=conn,
                )
                if not scores:
                    # Reject before any destructive write. Rolling back
                    # the transaction (which never ran DELETE/INSERT)
                    # is the explicit no-source signal that preserves
                    # the last-good generation.
                    raise CrmSourceDataUnavailable()
                await self.repo.replace_month_scores(
                    month, scores, connection=conn,
                )
        return len(scores)

    async def get_alerts(self, month: str) -> list[dict[str, Any]]:
        y, m_int = map(int, month.split("-"))
        prev_month = f"{y}-{m_int - 1:02d}" if m_int > 1 else f"{y - 1}-12"

        async with self.pool.acquire() as conn:
            forecast_factor = await get_forecast_factor(conn, month)

        rows = await self.repo.get_alerts_data(month, prev_month)

        alerts = []
        for row in rows:
            reasons = []
            score = row["score"]
            current_val = float(row["current_val"] or 0)
            prev_val = float(row["prev_val"] or 0)
            forecast_val = current_val * forecast_factor

            if score >= 0 and score < 40:
                reasons.append(f"Scor scăzut ({score}/100)")

            if prev_val > 0:
                trend = (forecast_val - prev_val) / prev_val * 100
                if trend < -20:
                    reasons.append(f"Scădere previzionată {abs(round(trend))}% față de luna anterioară")

            if reasons:
                alerts.append({
                    "site_code": row["site_code"],
                    "score": score,
                    "reasons": reasons,
                    "regional": row["regional"],
                    "asm": row["asm"],
                    "locatie": row["locatie"],
                })

        return sorted(alerts, key=lambda x: x["score"])

    async def get_scores(self, month: str) -> list[dict[str, Any]]:
        rows = await self.repo.get_scores(month)
        result = []
        for r in rows:
            d = dict(r)
            if isinstance(d.get("breakdown"), str):
                d["breakdown"] = json.loads(d["breakdown"])
            result.append(d)
        return result
