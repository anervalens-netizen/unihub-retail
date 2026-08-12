"""Release-A contract for the inert cohort/outbox schema."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import importlib
import json
import os

import asyncpg
import httpx
import pytest


pytestmark = pytest.mark.skipif(
    os.getenv("UNIHUB_TEST_DATABASE") != "1",
    reason="requires isolated PostgreSQL",
)

EVENT_TYPE = "retail.sales_generation_promoted.v1"
GENERATION_HASH = "a" * 64
SOURCE_HASH = "d" * 64
ACTOR_HASH = "c" * 64
OCCURRED_AT = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)
EMITTER_SIGNATURE = "(text,text,text,timestamp with time zone,text,bigint,timestamp with time zone)"
EMITTER_ROLES = {
    "emit_retail_sales_generation_promoted": "unihub_sales_import",
    "emit_retail_pnl_generation_promoted": "unihub_finance_import",
    "emit_retail_salary_import_completed": "unihub_migrate",
    "emit_retail_planning_forecast_promoted": "unihub_operations",
    "emit_retail_grile_manifest_approved": "unihub_business_write",
}


def _payload(
    *,
    event_type: str = EVENT_TYPE,
    aggregate_type: str = "sales_generation",
    aggregate_id: str,
    revision: int,
    extra: dict[str, object] | None = None,
) -> str:
    payload: dict[str, object] = {
        "event_schema": event_type,
        "aggregate_type": aggregate_type,
        "aggregate_id": aggregate_id,
        "generation_hash": GENERATION_HASH,
        "source_hash": SOURCE_HASH,
        "month": "2026-07",
        "revision": revision,
        "occurred_at": "2026-08-12T12:00:00Z",
    }
    payload.update(extra or {})
    return json.dumps(payload, sort_keys=True)


async def _direct_event(
    connection: asyncpg.Connection,
    *,
    aggregate_id: str,
    revision: int,
    sequence: int,
    extra: dict[str, object] | None = None,
) -> asyncpg.Record:
    payload = _payload(aggregate_id=aggregate_id, revision=revision, extra=extra)
    return await connection.fetchrow(
        """
        WITH prepared AS (SELECT $7::jsonb AS payload)
        INSERT INTO retail_outbox_events (
            event_type, aggregate_type, aggregate_id, generation_hash,
            revision, aggregate_sequence, event_key, payload,
            payload_sha256, occurred_at
        )
        SELECT $1, 'sales_generation', $2, $3, $4::bigint, $5,
               $1 || ':' || $2 || ':' || $3 || ':' || ($4::bigint)::text,
               prepared.payload,
               encode(digest(convert_to(prepared.payload::text, 'UTF8'), 'sha256'), 'hex'),
               $6
        FROM prepared
        RETURNING id, state, attempt_count, claim_epoch, replay_count
        """,
        EVENT_TYPE,
        aggregate_id,
        GENERATION_HASH,
        revision,
        sequence,
        OCCURRED_AT,
        payload,
    )


async def _emit(
    connection: asyncpg.Connection,
    function_name: str,
    *,
    aggregate_id: str,
    revision: int = 1,
) -> str:
    assert function_name in EMITTER_ROLES
    return str(
        await connection.fetchval(
            f"""
            SELECT public.{function_name}(
                $1, $2, $3, $4, $5, $6, $7
            )
            """,
            aggregate_id,
            GENERATION_HASH,
            SOURCE_HASH,
            OCCURRED_AT,
            "2026-07",
            revision,
            OCCURRED_AT,
        )
    )


async def _insert_lineaged_run(
    connection: asyncpg.Connection,
    snapshot_id: str | None,
    *,
    status: str = "completed",
    expected: int = 1,
    model: int | None = 1,
    fallback: int | None = 0,
    precision_loss: int | None = 0,
    raw_response_sha256: str | None = "7" * 64,
    response_sha256: str | None = "8" * 64,
    response_profile: str = "point_quantiles_v1",
) -> int:
    return int(
        await connection.fetchval(
            """
            INSERT INTO ai_forecast_runs (
                forecast_month, source_month, model_name, model_mode, variant,
                status, generated_at, metadata, metric, horizon,
                cohort_snapshot_id, request_sha256, raw_response_sha256,
                response_sha256, expected_pair_count, model_pair_count,
                fallback_pair_count, precision_loss_count, coverage_mode,
                response_profile
            ) VALUES (
                '2026-08', '2026-07', 'contract-model', 'operational', 'release-a',
                $2, $3, '{}'::jsonb, 'sales_value', 'current_month',
                $1, $4, $5, $6, $7, $8, $9, $10, 'fail_closed', $11
            )
            RETURNING id
            """,
            snapshot_id,
            status,
            OCCURRED_AT,
            "6" * 64,
            raw_response_sha256,
            response_sha256,
            expected,
            model,
            fallback,
            precision_loss,
            response_profile,
        )
    )


@pytest.mark.asyncio
async def test_069_is_additive_empty_and_old_ai_insert_remains_compatible() -> None:
    connection = await asyncpg.connect(os.environ["DATABASE_URL"])
    transaction = connection.transaction()
    await transaction.start()
    try:
        tables = {
            str(row["table_name"])
            for row in await connection.fetch(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = ANY($1::text[])
                """,
                [
                    "ai_forecast_cohort_snapshots",
                    "ai_forecast_cohort_rows",
                    "retail_outbox_events",
                    "retail_outbox_consumer_receipts",
                    "retail_outbox_replay_audit",
                ],
            )
        }
        assert tables == {
            "ai_forecast_cohort_snapshots",
            "ai_forecast_cohort_rows",
            "retail_outbox_events",
            "retail_outbox_consumer_receipts",
            "retail_outbox_replay_audit",
        }
        assert await connection.fetchval("SELECT count(*) FROM retail_outbox_events") == 0

        # Exact pre-069 insert shape used by the old importer stays valid.
        run_id = await connection.fetchval(
            """
            INSERT INTO ai_forecast_runs (
                forecast_month, source_month, model_name, model_mode, variant,
                status, generated_at, metadata, metric, horizon
            ) VALUES (
                '2026-09', '2026-08', 'compat-model', 'operational', 'release-a',
                'completed', $1, '{}'::jsonb, 'sales_value', 'current_month'
            )
            RETURNING id
            """,
            OCCURRED_AT,
        )
        lineage = await connection.fetchrow(
            """
            SELECT cohort_snapshot_id, request_sha256, raw_response_sha256,
                   response_sha256, expected_pair_count, model_pair_count,
                   fallback_pair_count, precision_loss_count, coverage_mode,
                   response_profile
            FROM ai_forecast_runs WHERE id = $1
            """,
            run_id,
        )
        assert lineage is not None
        assert all(value is None for value in lineage.values())
    finally:
        await transaction.rollback()
        await connection.close()


@pytest.mark.asyncio
async def test_069_seals_cohort_and_requires_exact_completed_run_lineage() -> None:
    connection = await asyncpg.connect(os.environ["DATABASE_URL"])
    transaction = connection.transaction()
    await transaction.start()
    try:
        await connection.execute("SET LOCAL ROLE unihub_operations")
        with pytest.raises(asyncpg.CheckViolationError):
            async with connection.transaction():
                await _insert_lineaged_run(connection, None)
        snapshot_id = str(
            await connection.fetchval(
                """
                INSERT INTO ai_forecast_cohort_snapshots (
                    source_month, target_month, cutoff_at, source_generation,
                    source_generation_sha256, authority_version,
                    row_count, expected_pair_count
                ) VALUES (
                    '2026-07', '2026-08', $1, 'sales-gen-1', $2,
                    'asof-v1', 1, 1
                )
                RETURNING id
                """,
                OCCURRED_AT,
                "e" * 64,
            )
        )
        await connection.execute(
            """
            INSERT INTO ai_forecast_cohort_rows (
                snapshot_id, site_code, source_month, is_operating, firma,
                regional, asm, authority_source, confidence, source_generation,
                source_row_sha256, first_seen_month, last_seen_month
            ) VALUES (
                $1, 'TEST-01', '2026-07', TRUE, 'A', 'R', 'M',
                'activity_event+org_assignment', 'confirmed', 'sales-gen-1',
                $2, '2025-01', '2026-07'
            )
            """,
            snapshot_id,
            "1" * 64,
        )

        with pytest.raises(asyncpg.RaiseError, match="sealed cohort"):
            async with connection.transaction():
                await _insert_lineaged_run(connection, snapshot_id)

        sealed = await connection.fetchrow(
            "SELECT state, cohort_sha256, sealed_at FROM seal_ai_forecast_cohort_snapshot($1)",
            snapshot_id,
        )
        assert sealed is not None
        assert sealed["state"] == "sealed"
        assert len(str(sealed["cohort_sha256"])) == 64
        assert sealed["sealed_at"] is not None

        with pytest.raises(asyncpg.RaiseError, match="building snapshot"):
            async with connection.transaction():
                await connection.execute(
                    """
                    INSERT INTO ai_forecast_cohort_rows (
                        snapshot_id, site_code, source_month, authority_source,
                        confidence, source_generation, source_row_sha256,
                        first_seen_month, last_seen_month
                    ) VALUES (
                        $1, 'TEST-02', '2026-07', 'reporting_row', 'unknown',
                        'sales-gen-1', $2, '2026-07', '2026-07'
                    )
                    """,
                    snapshot_id,
                    "2" * 64,
                )

        await connection.execute("RESET ROLE")
        with pytest.raises(asyncpg.RaiseError, match="append-only"):
            async with connection.transaction():
                await connection.execute(
                    "UPDATE ai_forecast_cohort_rows SET firma = 'B' WHERE snapshot_id = $1",
                    snapshot_id,
                )
        with pytest.raises(asyncpg.RaiseError, match="verified seal"):
            async with connection.transaction():
                await connection.execute(
                    "UPDATE ai_forecast_cohort_snapshots SET row_count = 2 WHERE id = $1",
                    snapshot_id,
                )

        await connection.execute("SET LOCAL ROLE unihub_operations")
        valid_run_id = await _insert_lineaged_run(connection, snapshot_id)
        assert valid_run_id > 0

        with pytest.raises(asyncpg.CheckViolationError):
            async with connection.transaction():
                await _insert_lineaged_run(
                    connection, snapshot_id, response_profile="quantiles_v1"
                )
        with pytest.raises(asyncpg.CheckViolationError):
            async with connection.transaction():
                await _insert_lineaged_run(
                    connection, snapshot_id, model=0, fallback=0
                )
        with pytest.raises(asyncpg.CheckViolationError):
            async with connection.transaction():
                await _insert_lineaged_run(
                    connection, snapshot_id, raw_response_sha256=None
                )
        with pytest.raises(asyncpg.RaiseError, match="pair count differs"):
            async with connection.transaction():
                await _insert_lineaged_run(
                    connection, snapshot_id, expected=2, model=2
                )

        queued_id = await _insert_lineaged_run(
            connection,
            snapshot_id,
            status="queued",
            model=None,
            fallback=None,
            precision_loss=None,
            raw_response_sha256=None,
            response_sha256=None,
        )
        with pytest.raises(asyncpg.CheckViolationError):
            async with connection.transaction():
                await connection.execute(
                    "UPDATE ai_forecast_runs SET status = 'completed' WHERE id = $1",
                    queued_id,
                )
    finally:
        await transaction.rollback()
        await connection.close()


@pytest.mark.asyncio
async def test_069_outbox_is_canonical_private_ordered_and_replayable() -> None:
    connection = await asyncpg.connect(os.environ["DATABASE_URL"])
    transaction = connection.transaction()
    await transaction.start()
    try:
        transition_at = await connection.fetchval("SELECT now()")
        await connection.execute("SET LOCAL ROLE unihub_sales_import")
        event_id = await _emit(
            connection,
            "emit_retail_sales_generation_promoted",
            aggregate_id="sales-gen-1",
        )
        assert await _emit(
            connection,
            "emit_retail_sales_generation_promoted",
            aggregate_id="sales-gen-1",
        ) == event_id
        second_id = await _emit(
            connection,
            "emit_retail_sales_generation_promoted",
            aggregate_id="sales-gen-1",
            revision=2,
        )
        assert second_id != event_id

        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            async with connection.transaction():
                await _direct_event(
                    connection, aggregate_id="direct-denied", revision=1, sequence=1
                )
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            async with connection.transaction():
                await _emit(
                    connection,
                    "emit_retail_pnl_generation_promoted",
                    aggregate_id="wrong-role",
                )
        for forbidden_id in (
            "1234567890123",
            "a1234567-89ab-4def-8abc-1234567890ab",
            "sp1_" + "a" * 64,
            "sales_1234567890123",
            "sales_a1234567-89ab-4def-8abc-1234567890ab",
            "sales_sp1_" + "a" * 64,
        ):
            with pytest.raises(asyncpg.CheckViolationError):
                async with connection.transaction():
                    await _emit(
                        connection,
                        "emit_retail_sales_generation_promoted",
                        aggregate_id=forbidden_id,
                    )

        await connection.execute("RESET ROLE")
        with pytest.raises(asyncpg.CheckViolationError):
            async with connection.transaction():
                await _direct_event(
                    connection,
                    aggregate_id="bad-cutoff",
                    revision=1,
                    sequence=1,
                    extra={"cutoff": "https://example.invalid/private"},
                )
        rows = await connection.fetch(
            """
            SELECT id, aggregate_sequence, payload_sha256,
                   encode(digest(convert_to(payload::text, 'UTF8'), 'sha256'), 'hex') AS actual_sha
            FROM retail_outbox_events
            WHERE aggregate_type = 'sales_generation' AND aggregate_id = 'sales-gen-1'
            ORDER BY aggregate_sequence
            """
        )
        assert [row["aggregate_sequence"] for row in rows] == [1, 2]
        assert all(row["payload_sha256"] == row["actual_sha"] for row in rows)

        await connection.execute("SET LOCAL ROLE unihub_operations")
        await connection.execute(
            """
            UPDATE retail_outbox_events
            SET state = 'processing', attempt_count = 1,
                claim_owner = 'worker-1', claim_epoch = 1,
                lease_until = $2, claimed_at = $1, updated_at = $1
            WHERE id = $3
            """,
            transition_at,
            transition_at + timedelta(seconds=60),
            event_id,
        )
        for forbidden_key in (
            "sales:1234567890123",
            "sales:a1234567-89ab-4def-8abc-1234567890ab",
            "sales:sp1_" + "a" * 64,
        ):
            with pytest.raises(asyncpg.CheckViolationError):
                async with connection.transaction():
                    await connection.execute(
                        """
                        INSERT INTO retail_outbox_consumer_receipts (
                            event_id, consumer, domain_generation_key, effect_sha256
                        ) VALUES ($1, 'grile_v2', $2, $3)
                        """,
                        event_id,
                        forbidden_key,
                        "8" * 64,
                    )
        await connection.execute(
            """
            INSERT INTO retail_outbox_consumer_receipts (
                event_id, consumer, domain_generation_key, effect_sha256
            ) VALUES ($1, 'grile_v2', 'sales:sales-gen-1', $2)
            """,
            event_id,
            "8" * 64,
        )

        await connection.execute("RESET ROLE")
        with pytest.raises(asyncpg.RaiseError, match="identity and payload"):
            async with connection.transaction():
                await connection.execute(
                    "UPDATE retail_outbox_events SET payload_sha256 = $1 WHERE id = $2",
                    "9" * 64,
                    event_id,
                )
        with pytest.raises(asyncpg.RaiseError, match="append-only"):
            async with connection.transaction():
                await connection.execute(
                    """
                    UPDATE retail_outbox_consumer_receipts
                    SET effect_sha256 = $1
                    WHERE event_id = $2 AND consumer = 'grile_v2'
                    """,
                    "7" * 64,
                    event_id,
                )

        await connection.execute("SET LOCAL ROLE unihub_operations")
        await connection.execute(
            """
            UPDATE retail_outbox_events
            SET state = 'completed', claim_owner = NULL, lease_until = NULL,
                completed_at = $1, updated_at = $1
            WHERE id = $2
            """,
            transition_at + timedelta(seconds=1),
            event_id,
        )
        with pytest.raises(asyncpg.RaiseError, match="completed"):
            async with connection.transaction():
                await connection.execute(
                    "UPDATE retail_outbox_events SET updated_at = $1 WHERE id = $2",
                    transition_at + timedelta(seconds=2),
                    event_id,
                )

        await connection.execute("RESET ROLE")
        dead_payload = _payload(aggregate_id="sales-gen-dead", revision=1)
        dead_event_id = await connection.fetchval(
            """
            WITH prepared AS (SELECT $4::jsonb AS payload)
            INSERT INTO retail_outbox_events (
                event_type, aggregate_type, aggregate_id, generation_hash,
                revision, aggregate_sequence, event_key, payload,
                payload_sha256, state, attempt_count, occurred_at,
                last_error_code, last_error_at, dead_at
            )
            SELECT $1, 'sales_generation', 'sales-gen-dead', $2, 1, 1,
                   $1 || ':sales-gen-dead:' || $2 || ':1', prepared.payload,
                   encode(digest(convert_to(prepared.payload::text, 'UTF8'), 'sha256'), 'hex'),
                   'dead', 8, $3, 'handler_failed', $3, $3
            FROM prepared
            RETURNING id
            """,
            EVENT_TYPE,
            GENERATION_HASH,
            OCCURRED_AT,
            dead_payload,
        )
        await connection.execute("SET LOCAL ROLE unihub_operations")
        with pytest.raises(asyncpg.RaiseError, match="exact dead event"):
            async with connection.transaction():
                await connection.execute(
                    """
                    INSERT INTO retail_outbox_replay_audit (
                        event_id, replay_number, previous_attempt_count,
                        previous_dead_at, reason, requested_by_sub_sha256
                    ) VALUES ($1, 2, 8, $2, 'operator_retry', $3)
                    """,
                    dead_event_id,
                    OCCURRED_AT,
                    ACTOR_HASH,
                )
        await connection.execute(
            """
            INSERT INTO retail_outbox_replay_audit (
                event_id, replay_number, previous_attempt_count,
                previous_dead_at, reason, requested_by_sub_sha256
            ) VALUES ($1, 1, 8, $2, 'operator_retry', $3)
            """,
            dead_event_id,
            OCCURRED_AT,
            ACTOR_HASH,
        )
        await connection.execute(
            """
            UPDATE retail_outbox_events
            SET state = 'pending', attempt_count = 0, available_at = $1,
                last_error_code = NULL, last_error_at = NULL, dead_at = NULL,
                replay_count = 1, updated_at = $1
            WHERE id = $2
            """,
            transition_at + timedelta(seconds=2),
            dead_event_id,
        )
        replayed = await connection.fetchrow(
            "SELECT state, attempt_count, replay_count FROM retail_outbox_events WHERE id = $1",
            dead_event_id,
        )
        assert replayed is not None
        assert tuple(replayed.values()) == ("pending", 0, 1)
    finally:
        await transaction.rollback()
        await connection.close()


@pytest.mark.asyncio
async def test_069_runtime_roles_have_exact_producer_privileges() -> None:
    connection = await asyncpg.connect(os.environ["DATABASE_URL"])
    transaction = connection.transaction()
    await transaction.start()
    try:
        roles = [*EMITTER_ROLES.values(), "unihub_web_read"]
        for role in roles:
            assert not await connection.fetchval(
                "SELECT has_table_privilege($1, 'public.retail_outbox_events', 'INSERT')",
                role,
            )
            for function_name, expected_role in EMITTER_ROLES.items():
                signature = f"public.{function_name}{EMITTER_SIGNATURE}"
                assert bool(
                    await connection.fetchval(
                        "SELECT has_function_privilege($1, $2, 'EXECUTE')",
                        role,
                        signature,
                    )
                ) is (role == expected_role)

        for index, (function_name, role) in enumerate(EMITTER_ROLES.items(), start=1):
            await connection.execute(f"SET LOCAL ROLE {role}")
            event_id = await _emit(
                connection,
                function_name,
                aggregate_id=f"acl-event-{index}",
            )
            assert event_id
            await connection.execute("RESET ROLE")
        assert await connection.fetchval("SELECT count(*) FROM retail_outbox_events") == 5

        await connection.execute("SET LOCAL ROLE unihub_web_read")
        assert await connection.fetchval(
            "SELECT count(*) FROM ai_forecast_cohort_snapshots"
        ) == 0
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            async with connection.transaction():
                await connection.execute(
                    """
                    INSERT INTO ai_forecast_cohort_snapshots (
                        source_month, target_month, cutoff_at, source_generation,
                        source_generation_sha256, authority_version,
                        row_count, expected_pair_count
                    ) VALUES (
                        '2026-07', '2026-08', $1, 'forbidden', $2,
                        'asof-v1', 0, 0
                    )
                    """,
                    OCCURRED_AT,
                    "4" * 64,
                )
    finally:
        await transaction.rollback()
        await connection.close()


@pytest.mark.asyncio
async def test_release_a_runtime_starts_and_is_ready_on_069(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The baseline application code remains compatible with the new manifest/schema."""
    monkeypatch.setenv("UNIHUB_ENV", "development")
    monkeypatch.delenv("UNIHUB_DB_PROCESS_AUTHORITY", raising=False)
    monkeypatch.delenv("PROMETHEUS_MULTIPROC_DIR", raising=False)
    monkeypatch.setenv("VALKEY_URL", os.environ["RATE_LIMIT_TEST_VALKEY_URL"])
    for name in (
        "SESSION_ENCRYPTION_KEY",
        "SESSION_PUBLIC_ORIGIN",
        "SESSION_VALKEY_URL",
        "OIDC_CLIENT_ID",
        "OIDC_CLIENT_SECRET",
        "OIDC_ISSUER",
        "OIDC_JWKS_URL",
        "OIDC_AUDIENCE",
        "HUB_INTERNAL_SECRET",
        "TRUSTED_PROXY_CIDRS",
        "RATE_LIMIT_CLIENT_IP_HEADER",
        "RATE_LIMIT_VALKEY_URL",
        "RATE_LIMIT_KEY_HMAC_SECRET",
        "RATE_LIMIT_FAILURE_MODE",
        "SALARY_PERSON_ID_HMAC_KEY",
    ):
        monkeypatch.setenv(name, "")

    main = importlib.import_module("main")
    async with main.lifespan(main.app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=main.app),
            base_url="http://release-a.test",
        ) as client:
            live = await client.get("/livez")
            ready = await client.get("/readyz")
        assert live.status_code == 200
        assert live.json() == {"status": "alive"}
        assert ready.status_code == 200
        assert ready.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_pre_069_manifest_is_refused_after_schema_upgrade() -> None:
    """Rollback must target Release A; a pre-069 artifact cannot claim DB currency."""
    from db.migration_runner import MigrationError, MigrationManifest, _validate_applied

    connection = await asyncpg.connect(os.environ["DATABASE_URL"])
    try:
        rows = await connection.fetch(
            "SELECT filename, checksum FROM schema_migrations ORDER BY filename"
        )
    finally:
        await connection.close()
    applied = {str(row["filename"]): str(row["checksum"]) for row in rows}
    assert "069_ai_cohort_and_transactional_outbox.sql" in applied

    pre_069 = MigrationManifest(
        baseline_hash="0" * 64,
        incorporated_through="022_store_pnl_site_links.sql",
        checksums={
            filename: checksum
            for filename, checksum in applied.items()
            if filename < "069_"
        },
    )
    with pytest.raises(MigrationError, match="absent from the manifest"):
        _validate_applied(applied, pre_069, allow_missing_checksums=False)
