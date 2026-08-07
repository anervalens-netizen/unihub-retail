-- Additive Insight Grile v2 read models.
--
-- v1 used only the current fenced projection.  Historical completed full runs
-- remain immutable audit evidence, so v2 selects one source for the whole
-- period: a non-empty current projection first, otherwise the latest completed
-- full run ordered by its terminal instant and id.  It never fills individual
-- current-projection holes from a different run.

CREATE OR REPLACE VIEW reporting_source_snapshot_v6 (
    domain, period, source, source_generation, authority, authority_head,
    contract_version, rule_version, status, as_of, cutoff, is_final,
    coverage_numerator, coverage_denominator, produced_at, warnings
) WITH (security_barrier = true) AS
WITH sales_periods AS (
    SELECT * FROM reporting_source_snapshot_v5 WHERE domain = 'sales'
), grile_eligible AS (
    SELECT sales.period, sheet.site_code
    FROM sales_periods AS sales
    JOIN grile_sheets AS sheet ON sheet.is_active
       AND (sheet.active_from_month IS NULL OR sheet.active_from_month <= sales.period)
    JOIN stores AS store ON store.site_code = sheet.site_code
       AND store.locatie NOT ILIKE 'TR%'
       AND store.locatie NOT ILIKE '%cartel%'
), current_projection AS (
    SELECT
        eligible.period,
        COUNT(*)::bigint AS denominator,
        COUNT(*) FILTER (
            WHERE current.current_observation_id IS NOT NULL
        )::bigint AS numerator,
        COUNT(*) FILTER (
            WHERE current.current_observation_id IS NOT NULL
              AND current.error_code IS NOT NULL
        )::bigint AS error_count,
        COUNT(*) FILTER (
            WHERE current.current_observation_id IS NOT NULL
              AND (
                  current.fill_status IS DISTINCT FROM 'COMPLETAT'
                  OR current.target_status IS DISTINCT FROM 'OK'
                  OR current.sales_status IS DISTINCT FROM 'OK'
              )
        )::bigint AS mismatch_count,
        MAX(current.generation) FILTER (
            WHERE current.current_observation_id IS NOT NULL
        ) AS head_generation,
        MAX(current.checked_at) FILTER (
            WHERE current.current_observation_id IS NOT NULL
        ) AS produced_at,
        MAX(current.db_max_sale_date) FILTER (
            WHERE current.current_observation_id IS NOT NULL
        ) AS cutoff
    FROM grile_eligible AS eligible
    LEFT JOIN grile_store_current_status AS current
      ON current.run_month = eligible.period
     AND current.site_code = eligible.site_code
    GROUP BY eligible.period
), latest_completed_run_ranked AS (
    SELECT
        sales.period,
        run.id AS run_id,
        run.progress_total,
        COALESCE(run.finished_at, run.heartbeat_at, run.started_at, run.created_at)
            AS terminal_at,
        ROW_NUMBER() OVER (
            PARTITION BY sales.period
            ORDER BY
                COALESCE(run.finished_at, run.heartbeat_at, run.started_at, run.created_at) DESC NULLS LAST,
                run.id DESC
        ) AS selection_rank
    FROM sales_periods AS sales
    JOIN grile_runs AS run
      ON run.run_month = sales.period
     AND run.status = 'completed'
), latest_completed_run AS (
    SELECT period, run_id, progress_total, terminal_at
    FROM latest_completed_run_ranked
    WHERE selection_rank = 1
), completed_run_sites AS (
    -- Fenced runs retain the claimed store set.  Pre-fence immutable runs have
    -- only their persisted row set, which is still their auditable population.
    SELECT run.period, run.run_id, generation.site_code
    FROM latest_completed_run AS run
    JOIN grile_run_store_generations AS generation ON generation.run_id = run.run_id

    UNION

    SELECT run.period, run.run_id, status.site_code
    FROM latest_completed_run AS run
    JOIN grile_store_status AS status ON status.run_id = run.run_id
), completed_run_projection AS (
    SELECT
        sales.period,
        run.run_id,
        run.terminal_at,
        GREATEST(
            COUNT(site.site_code) FILTER (
                WHERE store.locatie NOT ILIKE 'TR%'
                  AND store.locatie NOT ILIKE '%cartel%'
            )::bigint,
            GREATEST(
                COALESCE(run.progress_total, 0)::bigint
                - COUNT(site.site_code) FILTER (
                    WHERE store.locatie ILIKE 'TR%'
                       OR store.locatie ILIKE '%cartel%'
                )::bigint,
                0::bigint
            )
        ) AS denominator,
        COUNT(status.run_id) FILTER (
            WHERE store.locatie NOT ILIKE 'TR%'
              AND store.locatie NOT ILIKE '%cartel%'
        )::bigint AS numerator,
        COUNT(*) FILTER (
            WHERE status.run_id IS NOT NULL
              AND store.locatie NOT ILIKE 'TR%'
              AND store.locatie NOT ILIKE '%cartel%'
              AND status.error_code IS NOT NULL
        )::bigint AS error_count,
        COUNT(*) FILTER (
            WHERE status.run_id IS NOT NULL
              AND store.locatie NOT ILIKE 'TR%'
              AND store.locatie NOT ILIKE '%cartel%'
              AND (
                  status.fill_status IS DISTINCT FROM 'COMPLETAT'
                  OR status.target_status IS DISTINCT FROM 'OK'
                  OR status.sales_status IS DISTINCT FROM 'OK'
              )
        )::bigint AS mismatch_count,
        MAX(status.db_max_sale_date) FILTER (
            WHERE status.run_id IS NOT NULL
              AND store.locatie NOT ILIKE 'TR%'
              AND store.locatie NOT ILIKE '%cartel%'
        ) AS cutoff
    FROM sales_periods AS sales
    LEFT JOIN latest_completed_run AS run ON run.period = sales.period
    LEFT JOIN completed_run_sites AS site
      ON site.period = sales.period
     AND site.run_id = run.run_id
    LEFT JOIN stores AS store ON store.site_code = site.site_code
    LEFT JOIN grile_store_status AS status
      ON status.run_id = run.run_id
     AND status.site_code = site.site_code
    GROUP BY sales.period, run.run_id, run.progress_total, run.terminal_at
), grile_choice AS (
    SELECT
        sales.period,
        current.denominator AS current_denominator,
        current.numerator AS current_numerator,
        current.error_count AS current_error_count,
        current.mismatch_count AS current_mismatch_count,
        current.head_generation,
        current.produced_at AS current_produced_at,
        current.cutoff AS current_cutoff,
        completed.run_id,
        completed.terminal_at,
        completed.denominator AS completed_denominator,
        completed.numerator AS completed_numerator,
        completed.error_count AS completed_error_count,
        completed.mismatch_count AS completed_mismatch_count,
        completed.cutoff AS completed_cutoff,
        COALESCE(current.numerator, 0) > 0 AS use_current
    FROM sales_periods AS sales
    LEFT JOIN current_projection AS current ON current.period = sales.period
    LEFT JOIN completed_run_projection AS completed ON completed.period = sales.period
)
SELECT
    domain, period, source, source_generation, authority, authority_head,
    contract_version, rule_version, status, as_of, cutoff, is_final,
    coverage_numerator, coverage_denominator, produced_at, warnings
FROM reporting_source_snapshot_v5
WHERE domain <> 'grile'
UNION ALL
SELECT
    'grile'::text,
    choice.period,
    CASE
        WHEN choice.use_current THEN 'grile_store_current_status'
        ELSE 'grile_store_status'
    END,
    CASE
        WHEN choice.use_current THEN
            'grile-current-v2:' || choice.period || ':'
                || COALESCE(choice.head_generation, 0)::text
        ELSE
            'grile-completed-run-v2:' || choice.period || ':'
                || COALESCE(choice.run_id, 0)::text
    END,
    CASE
        WHEN choice.use_current THEN 'grile_store_current_status_fence'
        ELSE 'grile_completed_full_run'
    END,
    CASE
        WHEN choice.use_current THEN
            'grile:' || choice.period || ':current-projection:'
                || COALESCE(choice.head_generation, 0)::text
        ELSE
            'grile:' || choice.period || ':completed-run:'
                || COALESCE(choice.run_id, 0)::text
    END,
    2,
    CASE
        WHEN choice.use_current THEN 'grile-current-fenced-v2'
        ELSE 'grile-completed-full-run-v2'
    END,
    CASE
        WHEN choice.use_current THEN
            CASE
                WHEN COALESCE(choice.current_denominator, 0) = 0
                     OR COALESCE(choice.current_numerator, 0) = 0 THEN 'unavailable'
                WHEN choice.current_numerator = choice.current_denominator
                     AND choice.current_error_count = 0
                     AND choice.current_mismatch_count = 0 THEN 'official'
                ELSE 'partial'
            END
        ELSE
            CASE
                WHEN COALESCE(choice.completed_denominator, 0) = 0
                     OR COALESCE(choice.completed_numerator, 0) = 0 THEN 'unavailable'
                WHEN choice.completed_numerator = choice.completed_denominator
                     AND choice.completed_error_count = 0
                     AND choice.completed_mismatch_count = 0 THEN 'official'
                ELSE 'partial'
            END
    END,
    CASE
        WHEN choice.use_current THEN choice.current_cutoff
        ELSE choice.completed_cutoff
    END,
    CASE
        WHEN choice.use_current THEN choice.current_cutoff
        ELSE choice.completed_cutoff
    END,
    CASE
        WHEN choice.use_current THEN false
        ELSE choice.run_id IS NOT NULL
    END,
    CASE
        WHEN choice.use_current THEN COALESCE(choice.current_numerator, 0)
        ELSE COALESCE(choice.completed_numerator, 0)
    END,
    CASE
        WHEN choice.use_current THEN COALESCE(choice.current_denominator, 0)
        ELSE COALESCE(choice.completed_denominator, 0)
    END,
    CASE
        WHEN choice.use_current THEN COALESCE(choice.current_produced_at, sales.produced_at)
        ELSE COALESCE(choice.terminal_at, sales.produced_at)
    END,
    ARRAY_REMOVE(ARRAY[
        CASE WHEN choice.use_current THEN 'grile_current_fenced_projection_selected' END,
        CASE WHEN choice.use_current THEN 'grile_current_fenced_projection_not_month_final' END,
        CASE WHEN NOT choice.use_current THEN 'grile_current_projection_empty' END,
        CASE WHEN NOT choice.use_current AND choice.run_id IS NOT NULL
             THEN 'grile_completed_full_run_immutable' END,
        CASE WHEN NOT choice.use_current AND choice.run_id IS NULL
             THEN 'grile_completed_run_missing' END,
        CASE WHEN choice.use_current
                  AND COALESCE(choice.current_numerator, 0)
                        <> COALESCE(choice.current_denominator, 0)
             THEN 'grile_coverage_incomplete' END,
        CASE WHEN NOT choice.use_current
                  AND COALESCE(choice.completed_numerator, 0)
                        <> COALESCE(choice.completed_denominator, 0)
             THEN 'grile_coverage_incomplete' END,
        CASE WHEN choice.use_current AND COALESCE(choice.current_error_count, 0) > 0
             THEN 'grile_rows_with_errors' END,
        CASE WHEN NOT choice.use_current AND COALESCE(choice.completed_error_count, 0) > 0
             THEN 'grile_rows_with_errors' END,
        CASE WHEN choice.use_current AND COALESCE(choice.current_mismatch_count, 0) > 0
             THEN 'grile_row_status_mismatch' END,
        CASE WHEN NOT choice.use_current AND COALESCE(choice.completed_mismatch_count, 0) > 0
             THEN 'grile_row_status_mismatch' END
    ], NULL)
FROM grile_choice AS choice
JOIN sales_periods AS sales ON sales.period = choice.period;

CREATE OR REPLACE VIEW reporting_grile_month_v2 (
    period, run_month, site_code, locatie, firma, regional, asm, source_run_id,
    observation_generation, generation, checked_at, completion_status, fill_status, target_status,
    sales_status, last_error_code, status, covered, eligible, source, source_generation,
    authority, authority_head, contract_version, rule_version, as_of, cutoff, is_final,
    coverage_numerator, coverage_denominator, produced_at, warnings
) WITH (security_barrier = true) AS
WITH selected_rows AS (
    SELECT
        snapshot.period,
        COALESCE(current.run_month, snapshot.period) AS run_month,
        store.site_code, store.locatie, store.firma, store.regional, store.asm,
        current.source_run_id,
        CASE WHEN current.current_observation_id IS NULL THEN NULL
             ELSE 'grile-observation:' || current.current_observation_id::text END
            AS observation_generation,
        current.generation,
        current.checked_at,
        current.completion_pct,
        current.fill_status,
        current.target_status,
        current.sales_status,
        current.error_code,
        current.last_error_code,
        current.current_observation_id IS NOT NULL AS covered,
        snapshot.source, snapshot.source_generation, snapshot.authority, snapshot.authority_head,
        snapshot.contract_version, snapshot.rule_version, snapshot.status AS source_status,
        snapshot.as_of, snapshot.cutoff, snapshot.is_final, snapshot.coverage_numerator,
        snapshot.coverage_denominator, snapshot.produced_at, snapshot.warnings
    FROM reporting_source_snapshot_v6 AS snapshot
    JOIN grile_sheets AS sheet ON sheet.is_active
       AND (sheet.active_from_month IS NULL OR sheet.active_from_month <= snapshot.period)
    JOIN stores AS store ON store.site_code = sheet.site_code
       AND store.locatie NOT ILIKE 'TR%'
       AND store.locatie NOT ILIKE '%cartel%'
    LEFT JOIN grile_store_current_status AS current
      ON current.run_month = snapshot.period
     AND current.site_code = store.site_code
    WHERE snapshot.domain = 'grile'
      AND snapshot.source = 'grile_store_current_status'

    UNION ALL

    SELECT
        snapshot.period,
        snapshot.period AS run_month,
        store.site_code, store.locatie, store.firma, store.regional, store.asm,
        run.id AS source_run_id,
        CASE WHEN historic.run_id IS NULL THEN NULL
             ELSE 'grile-run-status:' || historic.run_id::text || ':' || store.site_code END
            AS observation_generation,
        run.id::bigint AS generation,
        COALESCE(run.finished_at, run.heartbeat_at, run.started_at, run.created_at) AS checked_at,
        historic.completion_pct,
        historic.fill_status,
        historic.target_status,
        historic.sales_status,
        historic.error_code,
        historic.error_code AS last_error_code,
        historic.run_id IS NOT NULL AS covered,
        snapshot.source, snapshot.source_generation, snapshot.authority, snapshot.authority_head,
        snapshot.contract_version, snapshot.rule_version, snapshot.status AS source_status,
        snapshot.as_of, snapshot.cutoff, snapshot.is_final, snapshot.coverage_numerator,
        snapshot.coverage_denominator, snapshot.produced_at, snapshot.warnings
    FROM reporting_source_snapshot_v6 AS snapshot
    JOIN grile_runs AS run
      ON snapshot.authority_head =
            'grile:' || snapshot.period || ':completed-run:' || run.id::text
     AND run.run_month = snapshot.period
     AND run.status = 'completed'
    JOIN (
        SELECT generation.run_id, generation.site_code
        FROM grile_run_store_generations AS generation
        UNION
        SELECT historic.run_id, historic.site_code
        FROM grile_store_status AS historic
    ) AS run_site
      ON run_site.run_id = run.id
    JOIN stores AS store ON store.site_code = run_site.site_code
       AND store.locatie NOT ILIKE 'TR%'
       AND store.locatie NOT ILIKE '%cartel%'
    LEFT JOIN grile_store_status AS historic
      ON historic.run_id = run.id
     AND historic.site_code = run_site.site_code
    WHERE snapshot.domain = 'grile'
      AND snapshot.source = 'grile_store_status'
)
SELECT
    row.period, row.run_month, row.site_code, row.locatie, row.firma, row.regional, row.asm,
    row.source_run_id, row.observation_generation, row.generation, row.checked_at,
    CASE
        WHEN NOT row.covered THEN 'unavailable'
        WHEN row.error_code IS NOT NULL THEN 'error'
        WHEN row.completion_pct IS NULL THEN 'incomplete'
        WHEN row.completion_pct >= 100 THEN 'complete'
        ELSE 'in_progress'
    END,
    row.fill_status, row.target_status, row.sales_status, row.last_error_code,
    CASE
        WHEN NOT row.covered OR row.error_code IS NOT NULL THEN 'unavailable'
        WHEN row.fill_status IS DISTINCT FROM 'COMPLETAT'
          OR row.target_status IS DISTINCT FROM 'OK'
          OR row.sales_status IS DISTINCT FROM 'OK' THEN 'partial'
        ELSE row.source_status
    END,
    row.covered, true,
    row.source, row.source_generation, row.authority, row.authority_head,
    row.contract_version, row.rule_version, row.as_of, row.cutoff, row.is_final,
    row.coverage_numerator, row.coverage_denominator, row.produced_at,
    row.warnings || ARRAY_REMOVE(ARRAY[
        CASE WHEN NOT row.covered THEN 'grile_observation_missing' END,
        CASE WHEN row.error_code IS NOT NULL THEN 'grile_error:' || row.error_code END,
        CASE WHEN row.last_error_code IS NOT NULL THEN 'grile_last_error:' || row.last_error_code END,
        CASE WHEN row.covered AND row.fill_status IS DISTINCT FROM 'COMPLETAT'
             THEN 'grile_fill_status_mismatch' END,
        CASE WHEN row.covered AND row.target_status IS DISTINCT FROM 'OK'
             THEN 'grile_target_status_mismatch' END,
        CASE WHEN row.covered AND row.sales_status IS DISTINCT FROM 'OK'
             THEN 'grile_sales_status_mismatch' END
    ], NULL)
FROM selected_rows AS row;

COMMENT ON VIEW reporting_source_snapshot_v6 IS
    'Additive Grile v2 source metadata: selects one complete-period source, preferring a non-empty fenced current projection and otherwise the latest immutable completed full run.';
COMMENT ON VIEW reporting_grile_month_v2 IS
    'Additive Grile v2 rows from exactly the period source selected by reporting_source_snapshot_v6; no per-store fallback mixes current and historical runs.';

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'unihub_insight_reader') THEN
        GRANT SELECT ON TABLE reporting_source_snapshot_v6, reporting_grile_month_v2
            TO unihub_insight_reader;
    END IF;
END
$$;
