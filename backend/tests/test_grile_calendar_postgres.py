"""Real database proof of calendar replacement, absence and identity fencing."""
from __future__ import annotations

import asyncio
from hashlib import sha256
import os
from datetime import date

import asyncpg
import pytest
import pytest_asyncio

from db.connection import validate_test_database_url
from grile.calendar_models import CalendarChanges, CalendarDayInput, RosterInput
from repositories.grile_calendar import CalendarConflict, GrileCalendarRepository
from services.grile_calendar import GrileCalendarService

pytestmark = [pytest.mark.asyncio, pytest.mark.skipif(
    os.getenv("UNIHUB_TEST_DATABASE") != "1", reason="requires isolated PostgreSQL",
)]
MONTH = "2196-09"
A, B, C, CLOSED = ("CAL-R1-" + value for value in ("A", "B", "C", "CLOSED"))
AG1, AG2 = "CAL-R1-AG1", "CAL-R1-AG2"


@pytest_asyncio.fixture
async def repo():
    url = os.environ["DATABASE_URL"]
    validate_test_database_url(url)
    pool = await asyncpg.create_pool(url, min_size=1, max_size=4, server_settings={
        "statement_timeout": "5000", "lock_timeout": "2000", "idle_in_transaction_session_timeout": "10000",
    })
    async with pool.acquire() as conn:
        for site, region in [(A, "R1"), (B, "R1"), (C, "R2"), (CLOSED, "R1")]:
            await conn.execute(
                """INSERT INTO stores(site_code,locatie,firma,regional,asm,first_seen_month,last_seen_month,is_active)
                   VALUES($1,$1,'SYNTHETIC',$2,'TL',$3,$3,$4)""", site, region, MONTH, site != CLOSED,
            )
    repository = GrileCalendarRepository(pool)
    try:
        yield repository
    finally:
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM grile_calendar_days WHERE agent_code LIKE 'CAL-R1-%'")
            await conn.execute("DELETE FROM grile_calendar_roster WHERE agent_code LIKE 'CAL-R1-%'")
            await conn.execute("DELETE FROM reporting_agent_day WHERE site_code LIKE 'CAL-R1-%'")
            await conn.execute("DELETE FROM store_targets WHERE site_code LIKE 'CAL-R1-%'")
            await conn.execute("DELETE FROM reporting_agent_month WHERE site_code LIKE 'CAL-R1-%'")
            await conn.execute("DELETE FROM stores WHERE site_code LIKE 'CAL-R1-%'")
            await conn.execute("DELETE FROM salary_private.people WHERE normalized_name='CAL-R4-SYNTHETIC-IDENTITY'")
        await pool.close()


def day(agent=AG1, site=A, status="work", revision=0, number=1, supplemental=False):
    return CalendarDayInput(work_date=date(2196, 9, number), agent_code=agent, site_code=site,
                            status=status, expected_revision=revision, supplemental=supplemental)


async def confirm(repo, code=AG1, home=A):
    return await repo.save_roster(MONTH, code, home, True, 0, "synthetic-manager")


async def test_atomic_replacement_leave_and_reassignment_keep_revisions(repo):
    await confirm(repo)
    await confirm(repo, AG2)
    service = GrileCalendarService(repo)
    first = await service.save_days(MONTH, CalendarChanges(days=[day()]), "manager")
    assert first[0].revision == 1
    # Person 1 takes leave; person 2 covers that exact store/day atomically.
    replaced = await service.save_days(MONTH, CalendarChanges(days=[
        day(status="leave", revision=1), day(agent=AG2, supplemental=True),
    ]), "manager")
    assert {row.agent_code: row.status for row in replaced} == {AG1: "leave", AG2: "work"}
    report = await service.read(MONTH)
    counts = {row.agent_code: row for row in report.attendance}
    assert counts[AG1].work_days == 0 and counts[AG1].leave_days == 1
    assert counts[AG2].work_days_by_site == {A: 1}
    await repo.save_days([day(status="cancelled", revision=2)], "manager")
    with pytest.raises(CalendarConflict, match="revision"):
        await repo.save_days([day(site=B, supplemental=True)], "stale-client")
    updated = await repo.save_days([day(site=B, supplemental=True, revision=3)], "manager")
    assert updated[0]["revision"] == 4
    counts = {row.agent_code: row for row in (await service.read(MONTH)).attendance}
    assert counts[AG1].work_days_by_site == {B: 1}
    assert counts[AG1].leave_days == 0


async def test_conflicting_batch_rolls_back_original_schedule(repo):
    await confirm(repo)
    await confirm(repo, AG2)
    await repo.save_days([day()], "manager")
    with pytest.raises(CalendarConflict, match="already has"):
        await repo.save_days([day(revision=1), day(agent=AG2)], "manager")
    rows = (await repo.read(MONTH))["days"]
    assert len(rows) == 1 and rows[0]["revision"] == 1 and rows[0]["status"] == "work"
    with pytest.raises(CalendarConflict, match="revision"):
        await repo.save_days([day(status="leave", revision=1), day(agent=AG2, revision=4)], "manager")
    assert (await repo.read(MONTH))["days"][0]["status"] == "work"


async def test_virtual_leader_preserves_store_scope_and_revision_fencing(repo):
    await repo.save_roster(MONTH, AG1, "TL", True, 0, "manager", regional="R1")
    assert (await repo.read(MONTH))["roster"][0]["home_site_code"] == "TL"
    with pytest.raises(CalendarConflict, match="confirmed region"):
        await repo.save_days([day(site=C, supplemental=True)], "manager")
    await repo.save_days([day()], "manager")
    with pytest.raises(CalendarConflict, match="Cancel scheduled"):
        await repo.save_roster(MONTH, AG1, "TL", True, 1, "manager", regional="R2")
    calendar = await GrileCalendarService(repo).read(MONTH)
    assert calendar.attendance[0].work_days_by_site == {A: 1}
    assert "TL" not in calendar.attendance_by_store
    await repo.save_days([day(status="cancelled", revision=1)], "manager")
    assert (await repo.read(MONTH))["days"][0]["status"] == "cancelled"


async def test_virtual_leader_identity_uses_unique_confirmed_person_without_home_join(repo, web_repo):
    await repo.save_roster(MONTH, AG1, "TL", True, 0, "manager", regional="R1")
    person = 'sp1_' + sha256(b'synthetic-tl').hexdigest()
    async with repo.pool.acquire() as conn:
        await conn.execute("INSERT INTO salary_private.people(person_id,normalized_name,identity_source) VALUES($1,'CAL-R4-SYNTHETIC-IDENTITY','name')", person)
        for site in (A, B):
            await conn.execute("INSERT INTO agent_salary_links(agent_code,site_code,salary_full_name,person_id,effective_from_month,match_status) VALUES($1,$2,'Synthetic TL',$3,'2196-08','confirmed')", AG1, site, person)
    calendar = await GrileCalendarService(web_repo).read(MONTH)
    assert len(calendar.roster) == 1
    assert calendar.roster[0].display_name == 'Synthetic TL'
    assert calendar.roster[0].identity_status == 'confirmed'
    assert 'person_id' not in calendar.model_dump_json()


async def test_virtual_leader_absence_has_no_physical_store_hours_or_sales(repo):
    await repo.save_roster(MONTH, AG1, "TL", True, 0, "manager", regional="R1")
    with pytest.raises(CalendarConflict, match="only Team Leader absences"):
        await repo.save_days([day(site="TL", supplemental=True)], "manager")
    created = await repo.save_days([day(site="TL", status="leave")], "manager")
    assert created[0]['site_code'] == 'TL'
    calendar = await GrileCalendarService(repo).read(MONTH)
    assert calendar.attendance[0].worked_minutes == 0
    assert calendar.attendance[0].leave_days == 1
    assert A not in calendar.attendance_by_store
    async with repo.pool.acquire() as conn:
        assert await conn.fetchval('SELECT site_code IS NULL FROM grile_calendar_days WHERE agent_code=$1', AG1)
    await repo.save_days([day(site="TL", status="off", revision=1)], "manager")
    await repo.save_days([day(site="TL", status="cancelled", revision=2)], "manager")
    await confirm(repo, AG2)
    with pytest.raises(CalendarConflict, match="only Team Leader absences"):
        await repo.save_days([day(agent=AG2, site="TL", status="leave")], "manager")


async def test_retired_tl_region_allows_deactivation_but_not_reactivation(repo):
    await repo.save_roster(MONTH, AG1, "TL", True, 0, "manager", regional="R1")
    async with repo.pool.acquire() as conn:
        await conn.execute("UPDATE stores SET is_active=FALSE WHERE site_code=ANY($1::text[])", [A, B, CLOSED])
    result = await repo.save_roster(MONTH, AG1, "TL", False, 1, "manager", regional="R1")
    assert not result['active'] and result['regional'] == 'R1'
    with pytest.raises(CalendarConflict, match="active regional scope"):
        await repo.save_roster(MONTH, AG1, "TL", True, 2, "manager", regional="R1")


async def test_distribution_only_region_cannot_create_team_leader(repo):
    async with repo.pool.acquire() as conn:
        await conn.execute("UPDATE stores SET locatie='TR Synthetic' WHERE site_code=$1", C)
    with pytest.raises(CalendarConflict, match="active regional scope"):
        await repo.save_roster(MONTH, AG1, "TL", True, 0, "manager", regional="R2")


async def test_two_simultaneous_agents_cannot_occupy_one_store_day(repo):
    await confirm(repo)
    await confirm(repo, AG2)
    outcomes = await asyncio.gather(
        repo.save_days([day()], "manager1"),
        repo.save_days([day(agent=AG2)], "manager2"), return_exceptions=True,
    )
    assert sum(isinstance(item, CalendarConflict) for item in outcomes) == 1
    assert len((await repo.read(MONTH))["days"]) == 1


async def test_two_managers_creating_same_agent_day_cannot_overwrite_winner(repo):
    await confirm(repo)
    outcomes = await asyncio.gather(
        repo.save_days([day()], "manager1"),
        repo.save_days([day(site=B, supplemental=True)], "manager2"),
        return_exceptions=True,
    )
    conflicts = [item for item in outcomes if isinstance(item, CalendarConflict)]
    assert len(conflicts) == 1 and "revision" in str(conflicts[0])
    winner = next(item for item in outcomes if isinstance(item, list))[0]
    saved = (await repo.read(MONTH))["days"]
    assert len(saved) == 1
    assert saved[0]["revision"] == winner["revision"] == 1
    assert saved[0]["site_code"] == winner["site_code"]
    assert saved[0]["updated_by_sub"] == winner["updated_by_sub"]


async def test_roster_creation_and_update_are_fenced(repo):
    outcomes = await asyncio.gather(confirm(repo), confirm(repo), return_exceptions=True)
    assert sum(isinstance(item, CalendarConflict) for item in outcomes) == 1
    row = await repo.save_roster(MONTH, AG1, A, False, 1, "manager")
    assert not row["active"] and row["revision"] == 2
    with pytest.raises(CalendarConflict, match="confirmed active"):
        await repo.save_days([day()], "manager")
    with pytest.raises(CalendarConflict, match="revision"):
        await repo.save_roster(MONTH, AG1, A, True, 1, "manager")
    await repo.save_roster(MONTH, AG1, A, True, 2, "manager")
    await repo.save_days([day()], "manager")
    for home, active in [(A, False), (B, True)]:
        with pytest.raises(CalendarConflict, match="Cancel scheduled"):
            await repo.save_roster(MONTH, AG1, home, active, 3, "manager")
    await repo.save_days([day(status="cancelled", revision=1)], "manager")
    moved = await repo.save_roster(MONTH, AG1, B, True, 3, "manager")
    assert moved["home_site_code"] == B


async def test_missing_identity_store_scope_and_leave_conflicts(repo):
    with pytest.raises(CalendarConflict, match="roster first"):
        await repo.save_days([day()], "manager")
    with pytest.raises(CalendarConflict, match="not active"):
        await confirm(repo, home=CLOSED)
    with pytest.raises(CalendarConflict, match="revision"):
        await repo.save_roster(MONTH, AG1, A, True, 5, "manager")
    await confirm(repo)
    with pytest.raises(CalendarConflict, match="unassigned"):
        await repo.save_days([day(status="cancelled")], "manager")
    for change, error in [
        (day(site=CLOSED, supplemental=True), "not active"),
        (day(site=B, status="leave"), "Only work"),
        (day(site=C, supplemental=True), "home region"),
    ]:
        with pytest.raises(CalendarConflict, match=error):
            await repo.save_days([change], "manager")
    await repo.save_days([day(status="leave")], "manager")
    with pytest.raises(CalendarConflict, match="retain"):
        await repo.save_days([day(status="cancelled", site=B, revision=1)], "manager")
    with pytest.raises(CalendarConflict, match="revision"):
        await repo.save_days([day(site=B, supplemental=True)], "manager")


async def test_database_constraints_and_minimal_authority(repo):
    await confirm(repo)
    await repo.save_days([day()], "manager")
    async with repo.pool.acquire() as conn:
        assert await conn.fetchval("SELECT has_table_privilege('unihub_business_write','grile_calendar_days','UPDATE')")
        assert not await conn.fetchval("SELECT has_table_privilege('unihub_web_read','grile_calendar_days','INSERT')")
        assert not await conn.fetchval("SELECT has_table_privilege('unihub_business_write','grile_calendar_days','DELETE')")
        for sql in [
            "UPDATE grile_calendar_days SET month='2196-10' WHERE agent_code=$1",
            "UPDATE grile_calendar_days SET status='leave', supplemental=TRUE WHERE agent_code=$1",
        ]:
            with pytest.raises(asyncpg.IntegrityConstraintViolationError):
                await conn.execute(sql, AG1)


async def test_real_candidates_allow_explicit_confirmation_without_current_sales(repo, monkeypatch):
    monkeypatch.setattr("services.grile_calendar.business_today", lambda: date(2196, 9, 20))
    async with repo.pool.acquire() as conn:
        for code, month, site in [(AG1, MONTH, A), (AG1, "2196-08", B), (AG2, "2196-08", A)]:
            await conn.execute(
                """INSERT INTO reporting_agent_month(import_month,site_code,locatie,firma,regional,asm,agent)
                   VALUES($1,$2,$2,'SYNTHETIC','R1','TL',$3)""", month, site, code,
            )
    service = GrileCalendarService(repo)
    candidates = {row.agent_code: row for row in await service.candidates(MONTH)}
    assert candidates[AG1].site_codes == [A]
    assert candidates[AG2].needs_active_confirmation
    assert (await repo.read(MONTH))["roster"] == []
    row = await service.save_roster(MONTH, AG2, RosterInput(home_site_code=A, expected_revision=0), "manager")
    assert row.active and row.agent_code == AG2
    changed = await service.save_roster(MONTH, AG2, RosterInput(home_site_code=A, expected_revision=1, active=False), "manager")
    assert not changed.active


async def test_distribution_locations_and_nonretail_codes_cannot_enter_calendar(repo, monkeypatch):
    monkeypatch.setattr("services.grile_calendar.business_today", lambda: date(2196, 9, 20))
    async with repo.pool.acquire() as conn:
        # Opaque site code: eligibility must use the canonical location field.
        await conn.execute("UPDATE stores SET locatie='tr Distribution', regional='R1' WHERE site_code=$1", C)
        for code, site in [(AG1, A), (AG2, C), ('-', A), (' - ', A), (' tr123 ', A)]:
            await conn.execute(
                """INSERT INTO reporting_agent_month(import_month,site_code,locatie,firma,regional,asm,agent)
                   VALUES($1,$2,$2,'SYNTHETIC','R1','TL',$3)""", MONTH, site, code,
            )
    service = GrileCalendarService(repo)
    assert [row.agent_code for row in await service.candidates(MONTH)] == [AG1]
    from fastapi import HTTPException
    for code in ['-', 'tr123', AG2]:
        with pytest.raises(HTTPException) as error:
            await service.save_roster(MONTH, code, RosterInput(home_site_code=A, expected_revision=0), 'manager')
        assert error.value.status_code == 422
    with pytest.raises(CalendarConflict, match='not active'):
        await confirm(repo, home=C)
    await confirm(repo)
    with pytest.raises(CalendarConflict, match='not active'):
        await repo.save_days([day(site=C, supplemental=True)], 'manager')
    assert (await repo.read(MONTH))['days'] == []


async def test_store_hours_cas_and_month_isolation(repo):
    from grile.calendar_models import StoreHoursInput
    await confirm(repo)
    await repo.save_days([day()], 'manager')
    try:
        created = await repo.save_hours(MONTH, A, StoreHoursInput(opens='09:00', expected_revision=0), 'manager')
        assert created['revision'] == 1
        with pytest.raises(CalendarConflict, match='hours changed'):
            await repo.save_hours(MONTH, A, StoreHoursInput(expected_revision=0), 'stale')
        report = await GrileCalendarService(repo).read(MONTH)
        assert report.attendance[0].worked_minutes == 720
        assert (await repo.read('2196-10'))['store_hours'] == []
        updated = await repo.save_hours(MONTH, A, StoreHoursInput(expected_revision=1), 'manager')
        assert updated['revision'] == 2
        assert (await GrileCalendarService(repo).read(MONTH)).attendance[0].worked_minutes == 660
    finally:
        async with repo.pool.acquire() as conn:
            await conn.execute('DELETE FROM grile_calendar_store_hours WHERE site_code=$1', A)


async def test_earnings_db_credits_tl_sales_to_calendar_person(repo, web_repo):
    from decimal import Decimal
    await confirm(repo)
    await confirm(repo, AG2, B)
    await repo.save_days([day(), day(site=B, number=2, supplemental=True), day(agent=AG2, site=B)], "manager")
    async with repo.pool.acquire() as conn:
        for site in (A, B):
            await conn.execute("INSERT INTO store_targets(import_month,site_code,target_value) VALUES($1,$2,2000)", MONTH, site)
        for site, number, amount in [(A, 1, 1600), (B, 1, 1000), (B, 2, 790)]:
            await conn.execute(
                """INSERT INTO reporting_agent_day(import_month,sale_date,site_code,locatie,firma,regional,asm,agent,total_sales)
                   VALUES($1,$2,$3,$3,'SYNTHETIC','R1','TL','LEADER-POS',$4)""",
                MONTH, date(2196, 9, number), site, amount,
            )
        await publish_earnings_fixture(conn)

    try:
        result = await GrileCalendarService(web_repo).earnings(MONTH)
        assert result.cutoff == date(2196, 9, 2)
        assert [agent.agent_code for agent in result.agents] == [AG1, AG2]
        agent = result.agents[0]
        assert (agent.home_commission, agent.away_commission, agent.supplemental_pay) == (48, 24, 150)
        assert agent.known_earnings == Decimal(222)
        assert sum(day.sales for agent in result.agents for day in agent.days) == Decimal(3390)
        assert result.unassigned_sales == []
    finally:
        async with repo.pool.acquire() as conn:
            await conn.execute("DELETE FROM sales_generation_heads WHERE import_month=$1", MONTH)
            # Published staging is append-only; the isolated runner drops this DB.
            # Keep its synthetic audit rows instead of disabling retention guards.


async def publish_earnings_fixture(conn):
    snapshot = await conn.fetchval(
        """INSERT INTO import_snapshots(import_month,filename,status,cutoff_date)
           VALUES($1,'synthetic-r4','processing',$2) RETURNING id""", MONTH, date(2196, 9, 2),
    )
    await conn.execute(
        """INSERT INTO sales_import_stage_rows
           (snapshot_id,row_number,import_month,sale_date,site_code,locatie,firma,regional,asm,
            bon_nr,item_code,item_name,quantity,unit_price,total_value,agent,is_cartela,is_return)
           SELECT $1, row_number() OVER (ORDER BY site_code,sale_date),import_month,sale_date,
                  site_code,locatie,firma,regional,asm,'synthetic','ACC','Accessory',1,
                  total_sales,total_sales,agent,FALSE,FALSE
           FROM reporting_agent_day WHERE import_month=$2""", snapshot, MONTH,
    )
    await conn.execute(
        """WITH payload AS (
               SELECT jsonb_build_object('generation_state','promoted',
                      'stage_rows_sha256',sales_stage_rows_sha256($1),
                      'rows_imported',COUNT(*), 'store_count',COUNT(DISTINCT site_code),
                      'total_quantity',SUM(quantity), 'total_value',SUM(total_value),
                      'max_sale_date',MAX(sale_date)::text) AS manifest
               FROM sales_import_stage_rows WHERE snapshot_id=$1)
           UPDATE import_snapshots SET manifest=payload.manifest,
                  manifest_sha256=encode(sha256(convert_to(payload.manifest::text,'UTF8')),'hex'),
                  status='completed'
           FROM payload WHERE id=$1""", snapshot,
    )
    await conn.execute("INSERT INTO sales_generation_heads(import_month,snapshot_id,revision) VALUES($1,$2,1)", MONTH, snapshot)
    return snapshot


@pytest_asyncio.fixture
async def web_repo(repo):
    """Authenticate as a non-superuser with the same memberships as web runtime."""
    from secrets import token_hex
    principal = "r4_web_" + token_hex(6)
    password = token_hex(24)
    async with repo.pool.acquire() as conn:
        await conn.execute(f"CREATE ROLE {principal} LOGIN PASSWORD '{password}'")
        await conn.execute(f"GRANT unihub_web_read, unihub_business_write TO {principal}")
    pool = await asyncpg.create_pool(os.environ["DATABASE_URL"], user=principal, password=password,
                                    min_size=1, max_size=2, server_settings={
        "statement_timeout": "5000", "lock_timeout": "2000", "idle_in_transaction_session_timeout": "10000",
    })
    try:
        async with pool.acquire() as conn:
            assert await conn.fetchval("SELECT current_user") == principal
            with pytest.raises(asyncpg.InsufficientPrivilegeError):
                await conn.fetch("SELECT * FROM sales_generation_heads")
        yield GrileCalendarRepository(pool)
    finally:
        await pool.close()
        async with repo.pool.acquire() as conn:
            await conn.execute(f"DROP ROLE {principal}")


@pytest.mark.parametrize('start,person,name,other_person,expected', [
    ('2196-09', 'synthetic-1', 'Synthetic Name', None, 'confirmed'),
    ('2196-10', 'synthetic-1', 'Synthetic Name', None, 'unavailable'),
    (None, 'synthetic-1', 'Synthetic Name', None, 'unavailable'),
    ('2196-08', None, None, None, 'unavailable'),
    ('2196-08', 'synthetic-1', '   ', None, 'unavailable'),
    ('2196-08', 'synthetic-1', 'Synthetic Name', 'synthetic-2', 'conflicting'),
    ('2196-08', 'synthetic-1', 'Synthetic Name', 'synthetic-1', 'confirmed'),
])
async def test_calendar_identity_is_effective_scoped_and_web_readable(repo, web_repo, start, person, name, other_person, expected):
    await confirm(repo)
    person = 'sp1_' + sha256(person.encode()).hexdigest() if person else None
    other_person = 'sp1_' + sha256(other_person.encode()).hexdigest() if other_person else None
    async with repo.pool.acquire() as conn:
        for identity in {person, other_person} - {None}:
            await conn.execute(
                """INSERT INTO salary_private.people(person_id,normalized_name,identity_source)
                   VALUES($1,'CAL-R4-SYNTHETIC-IDENTITY','name')""", identity,
            )
        await conn.execute(
            """INSERT INTO agent_salary_links(agent_code,site_code,salary_full_name,person_id,effective_from_month,match_status)
               VALUES($1,$2,$3,$4,$5,$6)""", AG1, A, name, person, start, "confirmed" if person else "unknown",
        )
        if other_person:
            await conn.execute(
                """INSERT INTO agent_salary_links(agent_code,site_code,salary_full_name,person_id,effective_from_month)
                   VALUES($1,$2,'Other store name',$3,'2196-08')""", AG1, B, other_person,
            )
    service = GrileCalendarService(web_repo)
    first = await service.read(MONTH)
    assert first.roster[0].identity_status == expected
    assert first.roster[0].display_name == ('Synthetic Name' if expected == 'confirmed' else None)
    assert 'person_id' not in first.model_dump_json()
    if expected == 'confirmed':
        async with repo.pool.acquire() as conn:
            await conn.execute("UPDATE agent_salary_links SET salary_full_name='Corrected name' WHERE agent_code=$1 AND site_code=$2", AG1, A)
        changed = await service.read(MONTH)
        assert changed.projection_revision != first.projection_revision
        assert changed.roster[0].display_name == 'Corrected name'
    earnings = await service.earnings(MONTH)
    assert earnings.agents[0].display_name == (await service.read(MONTH)).roster[0].display_name
    if other_person == person and expected == 'confirmed':
        async with repo.pool.acquire() as conn:
            await conn.execute("DELETE FROM agent_salary_links WHERE agent_code=$1 AND site_code=$2", AG1, A)
        known_person = (await service.read(MONTH)).roster[0]
        # The name is known; home salary identity remains unconfirmed.
        assert (known_person.display_name, known_person.identity_status) == ('Other store name', 'unavailable')


async def test_normal_shift_swap_preserves_store_hours_without_supplement(repo):
    await confirm(repo)
    await repo.save_days([day(site=B)], "manager")
    calendar = await GrileCalendarService(repo).read(MONTH)
    assert calendar.days[0].site_code == B and not calendar.days[0].supplemental
    assert calendar.attendance[0].work_days_by_site == {B: 1}
    assert calendar.attendance[0].worked_minutes == 660


async def test_compensation_is_revision_fenced_and_requires_active_roster(repo):
    from grile.compensation_models import CompensationInput
    from repositories.grile_compensation import save_compensation
    with pytest.raises(CalendarConflict, match='active agent'):
        await save_compensation(repo.pool, MONTH, AG1, CompensationInput(expected_revision=0), 'manager')
    await confirm(repo)
    try:
        values = CompensationInput(expected_revision=0, vouchers=480, sim_quantity=2,
            epay_under_50=0, epay_over_50=1, incentive=0, adjustment=0)
        outcomes = await asyncio.gather(
            save_compensation(repo.pool, MONTH, AG1, values, 'first-manager'),
            save_compensation(repo.pool, MONTH, AG1, values, 'second-manager'), return_exceptions=True)
        assert sum(isinstance(row, CalendarConflict) for row in outcomes) == 1
        saved = next(row for row in outcomes if not isinstance(row, Exception))
        assert saved['revision'] == 1 and saved['sim_quantity'] == 2
        service = GrileCalendarService(repo)
        data = await service.earnings(MONTH)
        assert data.agents[0].compensation.revision == 1
        assert data.agents[0].salary.sim_pay == 6
    finally:
        async with repo.pool.acquire() as conn:
            await conn.execute('DELETE FROM grile_calendar_compensation WHERE month=$1 AND agent_code=$2', MONTH, AG1)
