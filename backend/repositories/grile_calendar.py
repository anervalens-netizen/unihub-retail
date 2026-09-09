"""Calendar persistence with transactional day replacement and revision fencing."""
from __future__ import annotations

from typing import Any

import asyncpg

from grile.calendar_models import CalendarDayInput, StoreHoursInput
from retail_filters import distribution_location_clause


class CalendarConflict(Exception):
    pass


class GrileCalendarRepository:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def candidates(self, source_month: str, previous_month: str) -> list[dict[str, Any]]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                f"""SELECT DISTINCT r.import_month, btrim(r.agent) AS agent_code,
                          r.site_code, s.regional, s.firma
                   FROM reporting_agent_month r JOIN stores s USING (site_code)
                   WHERE r.import_month = ANY($1::text[]) AND s.is_active
                     AND btrim(r.agent) NOT IN ('', '-')
                     AND btrim(r.agent) NOT ILIKE 'TR%'
                     AND {distribution_location_clause("s")}
                     AND s.site_code <> 'Cartele'
                   ORDER BY agent_code, r.import_month DESC, r.site_code""",
                [source_month, previous_month],
            )
        return [dict(row) for row in rows]

    async def read(self, month: str) -> dict[str, Any]:
        async with self.pool.acquire() as conn:
            async with conn.transaction(isolation="repeatable_read", readonly=True):
                return await self.read_on_connection(conn, month)

    @staticmethod
    async def read_on_connection(conn: asyncpg.Connection, month: str) -> dict[str, Any]:
        roster = await conn.fetch(
            """WITH eligible AS (
                   SELECT agent_code, site_code, person_id, NULLIF(btrim(salary_full_name), '') AS name
                   FROM agent_salary_links
                   WHERE match_status='confirmed' AND effective_from_month <= $1
                     AND NULLIF(btrim(person_id), '') IS NOT NULL
               ), conflicts AS (
                   SELECT agent_code FROM eligible GROUP BY agent_code
                   HAVING COUNT(DISTINCT person_id) > 1
               )
               SELECT r.*,
                      CASE WHEN c.agent_code IS NULL THEN l.name END AS display_name,
                      CASE WHEN c.agent_code IS NOT NULL THEN 'conflicting'
                           WHEN l.name IS NOT NULL THEN 'confirmed'
                           ELSE 'unavailable' END AS identity_status
               FROM grile_calendar_roster r
               LEFT JOIN LATERAL (
                   SELECT CASE WHEN COUNT(DISTINCT name)=1 THEN MIN(name) END AS name
                   FROM eligible
                   WHERE agent_code=r.agent_code
                     AND (r.home_site_code IS NULL OR site_code=r.home_site_code)
               ) l ON TRUE
               LEFT JOIN conflicts c ON c.agent_code=r.agent_code
               WHERE r.month=$1 ORDER BY r.agent_code""", month,
        )
        days = await conn.fetch(
            "SELECT * FROM grile_calendar_days WHERE month=$1 ORDER BY work_date, agent_code", month,
        )
        hours = await conn.fetch(
            "SELECT * FROM grile_calendar_store_hours WHERE month=$1 ORDER BY site_code", month,
        )
        return {"roster": [dict(row, home_site_code=row["home_site_code"] or "TL") for row in roster],
                "days": [dict(row, site_code=row["site_code"] or "TL") for row in days],
                "store_hours": [dict(row) for row in hours]}

    @staticmethod
    async def _store(conn: asyncpg.Connection, site_code: str) -> asyncpg.Record:
        row = await conn.fetchrow(
            f"""SELECT site_code, regional FROM stores WHERE site_code=$1 AND is_active
               AND {distribution_location_clause()} AND site_code <> 'Cartele' FOR SHARE""", site_code,
        )
        if row is None:
            raise CalendarConflict("Store is not active")
        return row

    async def save_roster(
        self, month: str, agent_code: str, home_site_code: str, active: bool,
        expected_revision: int, actor: str,
        *, regional: str | None = None,
    ) -> dict[str, Any]:
        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    if home_site_code == "TL":
                        if not regional or not await conn.fetchval(
                            "SELECT EXISTS(SELECT 1 FROM stores WHERE is_active AND regional=$1)", regional,
                        ):
                            raise CalendarConflict("Team Leader requires an active regional scope")
                    else:
                        await self._store(conn, home_site_code)
                    stored_home = None if home_site_code == "TL" else home_site_code
                    old = await conn.fetchrow(
                        "SELECT * FROM grile_calendar_roster WHERE month=$1 AND agent_code=$2 FOR UPDATE",
                        month, agent_code,
                    )
                    if (old["revision"] if old else 0) != expected_revision:
                        raise CalendarConflict("Roster revision changed; reload the calendar")
                    if old and (not active or old["home_site_code"] != stored_home or old["regional"] != regional):
                        used = await conn.fetchval(
                            """SELECT EXISTS(SELECT 1 FROM grile_calendar_days
                               WHERE month=$1 AND agent_code=$2 AND status <> 'cancelled')""",
                            month, agent_code,
                        )
                        if used:
                            raise CalendarConflict("Cancel scheduled days before changing roster membership")
                    row = await conn.fetchrow(
                        """INSERT INTO grile_calendar_roster
                           (month, agent_code, home_site_code, active, revision, updated_by_sub, regional)
                           VALUES ($1,$2,$3,$4,1,$5,$7)
                           ON CONFLICT (month,agent_code) DO UPDATE SET
                             home_site_code=EXCLUDED.home_site_code, active=EXCLUDED.active, regional=EXCLUDED.regional,
                             revision=grile_calendar_roster.revision+1,
                             updated_by_sub=EXCLUDED.updated_by_sub, updated_at=now()
                           WHERE grile_calendar_roster.revision=$6 RETURNING *""",
                        month, agent_code, stored_home, active, actor, expected_revision, regional,
                    )
                    if row is None:
                        raise CalendarConflict("Roster revision changed; reload the calendar")
                    return dict(row, home_site_code=row["home_site_code"] or "TL")
        except asyncpg.UniqueViolationError as exc:
            raise CalendarConflict("Roster revision changed; reload the calendar") from exc

    async def _validate_day(
        self, conn: asyncpg.Connection, day: CalendarDayInput, roster: asyncpg.Record,
    ) -> None:
        old = await conn.fetchrow(
            "SELECT revision, site_code FROM grile_calendar_days WHERE agent_code=$1 AND work_date=$2 FOR UPDATE",
            day.agent_code, day.work_date,
        )
        if (old["revision"] if old else 0) != day.expected_revision:
            raise CalendarConflict("Day revision changed; reload the calendar")
        if day.status == "cancelled":
            if old is None:
                raise CalendarConflict("Cannot cancel an unassigned day")
            if (old["site_code"] or "TL") != day.site_code:
                raise CalendarConflict("Cancellation must retain the assigned store")
            return
        if not roster["active"]:
            raise CalendarConflict("Agent must be confirmed active for this month")
        if day.site_code == "TL":
            if roster["home_site_code"] is not None or day.status not in {"leave", "off"}:
                raise CalendarConflict("Virtual TL base accepts only Team Leader absences")
            return
        worked = await self._store(conn, day.site_code)
        if roster["home_site_code"] is None:
            if day.status != "work" or not day.supplemental or worked["regional"] != roster["regional"]:
                raise CalendarConflict("Team Leader work must be supplemental in the confirmed region")
            return
        home = await self._store(conn, roster["home_site_code"])
        if day.site_code != home["site_code"]:
            if day.status != "work" or not day.supplemental:
                raise CalendarConflict("Work at another store must be explicitly supplemental")
            if not home["regional"] or home["regional"] != worked["regional"]:
                raise CalendarConflict("Supplemental store must be in the agent's home region")

    async def save_days(self, days: list[CalendarDayInput], actor: str) -> list[dict[str, Any]]:
        ordered = sorted(days, key=lambda day: (day.agent_code, day.work_date))
        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    # Roster locks also serialize concurrent home/active changes.
                    for day in ordered:
                        roster = await conn.fetchrow(
                            """SELECT * FROM grile_calendar_roster
                               WHERE month=$1 AND agent_code=$2 FOR UPDATE""",
                            day.work_date.strftime("%Y-%m"), day.agent_code,
                        )
                        if roster is None:
                            raise CalendarConflict("Confirm the agent's monthly roster first")
                        await self._validate_day(conn, day, roster)
                    # Temporarily release only affected slots inside this transaction.
                    # This permits A/B swaps without exposing an intermediate empty day.
                    for day in ordered:
                        await conn.execute(
                            """UPDATE grile_calendar_days SET status='cancelled', supplemental=FALSE
                               WHERE agent_code=$1 AND work_date=$2""", day.agent_code, day.work_date,
                        )
                    result = []
                    for day in ordered:
                        row = await conn.fetchrow(
                            """INSERT INTO grile_calendar_days
                               (month,work_date,agent_code,site_code,status,supplemental,revision,updated_by_sub)
                               VALUES ($1,$2,$3,$4,$5,$6,1,$7)
                               ON CONFLICT (agent_code,work_date) DO UPDATE SET
                                 site_code=EXCLUDED.site_code,status=EXCLUDED.status,
                                 supplemental=EXCLUDED.supplemental,
                                 revision=grile_calendar_days.revision+1,
                                 updated_by_sub=EXCLUDED.updated_by_sub,updated_at=now()
                               RETURNING *""",
                            day.work_date.strftime("%Y-%m"), day.work_date, day.agent_code,
                            None if day.site_code == "TL" else day.site_code, day.status, day.supplemental, actor,
                        )
                        result.append(dict(row, site_code=row["site_code"] or "TL"))
                    return result
        except asyncpg.UniqueViolationError as exc:
            raise CalendarConflict("A store already has an assigned agent on that day") from exc

    async def save_hours(self, month: str, site_code: str, payload: StoreHoursInput, actor: str) -> dict[str, Any]:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await self._store(conn, site_code)
                old = await conn.fetchval(
                    "SELECT revision FROM grile_calendar_store_hours WHERE month=$1 AND site_code=$2 FOR UPDATE",
                    month, site_code,
                )
                if (old or 0) != payload.expected_revision:
                    raise CalendarConflict("Store hours changed; reload the calendar")
                row = await conn.fetchrow(
                    """INSERT INTO grile_calendar_store_hours
                       (month,site_code,opens,closes,break_minutes,revision,updated_by_sub)
                       VALUES ($1,$2,$3,$4,$5,1,$6)
                       ON CONFLICT (month,site_code) DO UPDATE SET
                         opens=EXCLUDED.opens, closes=EXCLUDED.closes, break_minutes=EXCLUDED.break_minutes,
                         revision=grile_calendar_store_hours.revision+1,
                         updated_by_sub=EXCLUDED.updated_by_sub, updated_at=now()
                       WHERE grile_calendar_store_hours.revision=$7 RETURNING *""",
                    month, site_code, payload.opens, payload.closes, payload.break_minutes,
                    actor, payload.expected_revision,
                )
                if row is None:
                    raise CalendarConflict("Store hours changed; reload the calendar")
                return dict(row)
