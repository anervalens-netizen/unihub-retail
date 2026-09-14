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
                          r.site_code, s.regional, s.firma,
                          (SELECT CASE WHEN COUNT(DISTINCT person_id)=1 AND COUNT(DISTINCT salary_full_name)=1
                             THEN MIN(salary_full_name) END FROM agent_salary_links l
                           WHERE l.agent_code=btrim(r.agent) AND l.match_status='confirmed'
                             AND NULLIF(btrim(l.person_id),'') IS NOT NULL
                             AND l.effective_from_month <= $2) AS display_name
                   FROM reporting_agent_month r JOIN stores s USING (site_code)
                   WHERE r.import_month = ANY($1::text[]) AND s.is_active
                     AND btrim(r.agent) NOT IN ('', '-')
                     AND btrim(r.agent) NOT ILIKE 'TR%'
                     AND {distribution_location_clause("s")}
                     AND s.site_code NOT IN ('Cartele', 'TL')
                   ORDER BY agent_code, r.import_month DESC, r.site_code""",
                [source_month, previous_month], source_month,
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
                      CASE WHEN c.agent_code IS NULL THEN COALESCE(l.name, catalog.name) END AS display_name,
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
               LEFT JOIN LATERAL (
                   SELECT CASE WHEN COUNT(DISTINCT name)=1 THEN MIN(name) END AS name
                   FROM eligible WHERE agent_code=r.agent_code
               ) catalog ON TRUE
               LEFT JOIN conflicts c ON c.agent_code=r.agent_code
               WHERE r.month=$1 ORDER BY r.agent_code""", month,
        )
        days = await conn.fetch(
            """SELECT d.* FROM grile_calendar_days d
               JOIN grile_calendar_roster r USING (month, agent_code)
               WHERE d.month=$1 AND (d.status <> 'cancelled' OR d.allocation_site =
                   CASE WHEN r.home_site_code IS NULL THEN COALESCE(d.site_code, 'TL') ELSE '' END)
               ORDER BY d.work_date, d.agent_code, d.site_code""", month,
        )
        hours = await conn.fetch(
            "SELECT * FROM grile_calendar_store_hours WHERE month=$1 ORDER BY site_code", month,
        )
        closures = await conn.fetch(
            "SELECT work_date,site_code,revision FROM grile_calendar_closures WHERE month=$1 ORDER BY work_date,site_code", month,
        )
        transfers = await conn.fetch(
            """SELECT DISTINCT ON (agent_code,effective_from) * FROM grile_calendar_transfers
               WHERE month=$1 ORDER BY agent_code,effective_from,roster_revision DESC""", month,
        )
        return {"roster": [dict(row, home_site_code=row["home_site_code"] or "TL",
                               transfers=[dict(t, home_site_code=t["home_site_code"] or "UNASSIGNED") for t in transfers if t["agent_code"] == row["agent_code"]]) for row in roster],
                "days": [dict(row, site_code=row["site_code"] or "TL") for row in days],
                "store_hours": [dict(row) for row in hours],
                "closures": [dict(row) for row in closures]}

    @staticmethod
    async def _store(conn: asyncpg.Connection, site_code: str) -> asyncpg.Record:
        row = await conn.fetchrow(
            f"""SELECT site_code, regional FROM stores WHERE site_code=$1 AND is_active
               AND {distribution_location_clause()} AND site_code NOT IN ('Cartele', 'TL') FOR SHARE""", site_code,
        )
        if row is None:
            raise CalendarConflict("Store is not active")
        return row

    async def _validate_roster_base(
        self, conn: asyncpg.Connection, home: str, regional: str | None,
        active: bool, old: asyncpg.Record | None,
    ) -> None:
        if home != "TL":
            await self._store(conn, home)
            return
        if not active and old and old["home_site_code"] is None and old["regional"] == regional:
            return
        if not regional or not await conn.fetchval(
            f"""SELECT EXISTS(SELECT 1 FROM stores WHERE is_active AND regional=$1
                AND {distribution_location_clause()} AND site_code NOT IN ('Cartele', 'TL'))""", regional,
        ):
            raise CalendarConflict("Team Leader requires an active regional scope")

    async def save_roster(
        self, month: str, agent_code: str, home_site_code: str, active: bool,
        expected_revision: int, actor: str,
        *, regional: str | None = None,
    ) -> dict[str, Any]:
        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    stored_home = None if home_site_code == "TL" else home_site_code
                    old = await conn.fetchrow(
                        "SELECT * FROM grile_calendar_roster WHERE month=$1 AND agent_code=$2 FOR UPDATE",
                        month, agent_code,
                    )
                    if (old["revision"] if old else 0) != expected_revision:
                        raise CalendarConflict("Roster revision changed; reload the calendar")
                    await self._validate_roster_base(conn, home_site_code, regional, active, old)
                    if old and (old["home_site_code"] != stored_home or old["regional"] != regional or not active):
                        if await conn.fetchval("SELECT EXISTS(SELECT 1 FROM grile_calendar_transfers WHERE month=$1 AND agent_code=$2)", month, agent_code):
                            raise CalendarConflict("Agent has dated transfers; use the team transfer editor")
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

    @staticmethod
    def _validate_cancellation(day: CalendarDayInput, old: asyncpg.Record | None) -> None:
        if old is None:
            raise CalendarConflict("Cannot cancel an unassigned day")
        if (old["site_code"] or "TL") != day.site_code:
            raise CalendarConflict("Cancellation must retain the assigned store")

    async def _validate_day(
        self, conn: asyncpg.Connection, day: CalendarDayInput, roster: asyncpg.Record,
    ) -> None:
        old = await conn.fetchrow(
            """SELECT revision, site_code FROM grile_calendar_days
               WHERE agent_code=$1 AND work_date=$2 AND allocation_site=$3 FOR UPDATE""",
            day.agent_code, day.work_date, day.site_code if roster["home_site_code"] is None else "",
        )
        if (old["revision"] if old else 0) != day.expected_revision:
            raise CalendarConflict("Day revision changed; reload the calendar")
        if day.status == "cancelled":
            self._validate_cancellation(day, old)
            return
        if not roster["active"]:
            raise CalendarConflict("Agent must be confirmed active for this month")
        if day.site_code == "TL":
            if roster["home_site_code"] is not None or day.status not in {"leave", "off"}:
                raise CalendarConflict("Virtual TL base accepts only Team Leader absences")
            return
        worked = await self._store(conn, day.site_code)
        if roster["home_site_code"] is None:
            if day.status != "work" or worked["regional"] != roster["regional"]:
                raise CalendarConflict("Team Leader work must stay in the confirmed region")
            return
        dated_home = await conn.fetchval(
            """SELECT COALESCE(home_site_code, 'UNASSIGNED') FROM grile_calendar_transfers
               WHERE month=$1 AND agent_code=$2 AND effective_from <= $3
               ORDER BY effective_from DESC,roster_revision DESC LIMIT 1""",
            day.work_date.strftime("%Y-%m"), day.agent_code, day.work_date,
        )
        if dated_home == 'UNASSIGNED':
            raise CalendarConflict("Agent has no home allocation on this date; assign a store first")
        home = await self._store(conn, dated_home or roster["home_site_code"])
        if day.site_code != home["site_code"]:
            if day.status != "work":
                raise CalendarConflict("Only work can be assigned at another store")
            if not home["regional"] or home["regional"] != worked["regional"]:
                raise CalendarConflict("Supplemental store must be in the agent's home region")

    async def _save_closures_in_transaction(self, conn, closures, actor: str) -> list[dict[str, Any]]:
        result = []
        for closure in closures:
            await self._store(conn, closure.site_code)
            if closure.closed and await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM grile_calendar_days WHERE work_date=$1 AND site_code=$2 AND status='work')",
                closure.work_date, closure.site_code,
            ):
                raise CalendarConflict("Schimbă mai întâi agentul programat sau închide ziua după anularea alocării")
            if closure.closed:
                row = await conn.fetchrow(
                    """INSERT INTO grile_calendar_closures(month,work_date,site_code,revision,updated_by_sub)
                       VALUES ($1,$2,$3,1,$4)
                       ON CONFLICT (month,work_date,site_code) DO UPDATE SET
                         revision=grile_calendar_closures.revision+1,updated_by_sub=EXCLUDED.updated_by_sub,updated_at=now()
                       WHERE grile_calendar_closures.revision=$5 RETURNING work_date,site_code,revision""",
                    closure.work_date.strftime('%Y-%m'), closure.work_date, closure.site_code,
                    actor, closure.expected_revision,
                )
            else:
                row = await conn.fetchrow(
                    "DELETE FROM grile_calendar_closures WHERE month=$1 AND work_date=$2 AND site_code=$3 AND revision=$4 RETURNING work_date,site_code,revision",
                    closure.work_date.strftime('%Y-%m'), closure.work_date, closure.site_code,
                    closure.expected_revision,
                )
            if row is None:
                raise CalendarConflict("Închiderea zilei s-a schimbat; reîncarcă calendarul")
            result.append(dict(row))
        return result

    async def save_days(self, days: list[CalendarDayInput], actor: str, closures=None) -> list[dict[str, Any]]:
        ordered = sorted(days, key=lambda day: (day.agent_code, day.work_date, day.site_code))
        slots: dict[tuple[str, object, str], str] = {}
        allocation_sites: dict[tuple[str, object, str], str] = {}
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
                        slot = day.site_code if roster["home_site_code"] is None else ""
                        key = (day.agent_code, day.work_date, slot)
                        if key in slots:
                            raise CalendarConflict("Only TL accounts can have several stores on the same day")
                        slots[key] = slot
                        allocation_sites[(day.agent_code, day.work_date, day.site_code)] = slot
                        await self._validate_day(conn, day, roster)
                    # Temporarily release only affected slots inside this transaction.
                    # This permits A/B swaps without exposing an intermediate empty day.
                    for day in ordered:
                        if day.status == "work":
                            await conn.execute("DELETE FROM grile_calendar_closures WHERE month=$1 AND work_date=$2 AND site_code=$3", day.work_date.strftime("%Y-%m"), day.work_date, day.site_code)
                        await conn.execute(
                            """UPDATE grile_calendar_days SET status='cancelled', supplemental=FALSE
                               WHERE agent_code=$1 AND work_date=$2 AND allocation_site=$3""",
                            day.agent_code, day.work_date,
                            allocation_sites[(day.agent_code, day.work_date, day.site_code)],
                        )
                    result = []
                    for day in ordered:
                        row = await conn.fetchrow(
                            """INSERT INTO grile_calendar_days
                               (month,work_date,agent_code,site_code,status,supplemental,revision,updated_by_sub)
                               VALUES ($1,$2,$3,$4,$5,$6,1,$7)
                               ON CONFLICT (agent_code,work_date,allocation_site) DO UPDATE SET
                                 site_code=EXCLUDED.site_code,status=EXCLUDED.status,
                                 supplemental=EXCLUDED.supplemental,
                                 revision=grile_calendar_days.revision+1,
                                 updated_by_sub=EXCLUDED.updated_by_sub,updated_at=now()
                               RETURNING *""",
                            day.work_date.strftime("%Y-%m"), day.work_date, day.agent_code,
                            None if day.site_code == "TL" else day.site_code, day.status, day.supplemental, actor,
                        )
                        result.append(dict(row, site_code=row["site_code"] or "TL"))
                    if closures:
                        await self._save_closures_in_transaction(conn, closures, actor)
                    return result
        except asyncpg.UniqueViolationError as exc:
            raise CalendarConflict("A store already has an assigned agent on that day") from exc

    async def save_closures(self, closures, actor: str) -> list[dict[str, Any]]:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                return await self._save_closures_in_transaction(conn, closures, actor)

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
