-- Authoritative Team Leader visit contract for UniHub Insight.
--
-- V1 remains available for N-1 rollback consumers. V2 reads the FieldOps
-- authority directly, keeps the author Team Leader snapshot and enriches only
-- the store hierarchy from the current Retail store catalog. A fresh isolated
-- Retail schema may intentionally omit the externally owned FieldOps table;
-- in that case the v2 contracts exist but expose no Visits source or rows.

DO $publish_source_snapshot_v2$
BEGIN
    IF to_regclass('public.fieldops_visits') IS NULL THEN
        EXECUTE $view$
            CREATE OR REPLACE VIEW reporting_source_snapshot_v2 (
                domain,
                period,
                source,
                source_generation,
                authority,
                authority_head,
                contract_version,
                rule_version,
                status,
                as_of,
                cutoff,
                is_final,
                coverage_numerator,
                coverage_denominator,
                produced_at,
                warnings
            )
            WITH (security_barrier = true)
            AS
            SELECT
                snapshot.domain,
                snapshot.period,
                snapshot.source,
                snapshot.source_generation,
                snapshot.authority,
                snapshot.authority_head,
                snapshot.contract_version,
                snapshot.rule_version,
                snapshot.status,
                snapshot.as_of,
                snapshot.cutoff,
                snapshot.is_final,
                snapshot.coverage_numerator,
                snapshot.coverage_denominator,
                snapshot.produced_at,
                snapshot.warnings
            FROM reporting_source_snapshot_v1 AS snapshot
            WHERE snapshot.domain <> 'visits'
        $view$;
    ELSE
        EXECUTE $view$
            CREATE OR REPLACE VIEW reporting_source_snapshot_v2 (
                domain,
                period,
                source,
                source_generation,
                authority,
                authority_head,
                contract_version,
                rule_version,
                status,
                as_of,
                cutoff,
                is_final,
                coverage_numerator,
                coverage_denominator,
                produced_at,
                warnings
            )
            WITH (security_barrier = true)
            AS
            WITH eligible_visits AS (
                SELECT
                    visit.data_raport,
                    visit.updated_at,
                    visit.team_leader_id,
                    visit.team_leader_name,
                    store.site_code
                FROM fieldops_visits AS visit
                LEFT JOIN stores AS store
                  ON store.site_code = visit.magazin
                WHERE visit.status <> 'draft'
                  AND visit.data_raport IS NOT NULL
            ),
            visit_source AS (
                SELECT
                    to_char(date_trunc('month', visit.data_raport), 'YYYY-MM') AS period,
                    COUNT(*)::bigint AS eligible_count,
                    COUNT(*) FILTER (
                        WHERE visit.site_code IS NOT NULL
                          AND (
                              NULLIF(BTRIM(visit.team_leader_id), '') IS NOT NULL
                              OR NULLIF(BTRIM(visit.team_leader_name), '') IS NOT NULL
                          )
                    )::bigint AS covered_count,
                    COUNT(*) FILTER (
                        WHERE NULLIF(BTRIM(visit.team_leader_id), '') IS NULL
                          AND NULLIF(BTRIM(visit.team_leader_name), '') IS NULL
                    )::bigint AS missing_team_leader_count,
                    COUNT(*) FILTER (WHERE visit.site_code IS NULL)::bigint AS unmapped_store_count,
                    MAX(visit.data_raport) AS cutoff,
                    MAX(visit.updated_at) AS produced_at
                FROM eligible_visits AS visit
                GROUP BY to_char(date_trunc('month', visit.data_raport), 'YYYY-MM')
            )
            SELECT
                snapshot.domain,
                snapshot.period,
                snapshot.source,
                snapshot.source_generation,
                snapshot.authority,
                snapshot.authority_head,
                snapshot.contract_version,
                snapshot.rule_version,
                snapshot.status,
                snapshot.as_of,
                snapshot.cutoff,
                snapshot.is_final,
                snapshot.coverage_numerator,
                snapshot.coverage_denominator,
                snapshot.produced_at,
                snapshot.warnings
            FROM reporting_source_snapshot_v1 AS snapshot
            WHERE snapshot.domain <> 'visits'

            UNION ALL

            SELECT
                'visits'::text,
                visit.period,
                'fieldops_visits'::text,
                'fieldops-visits:' || visit.period || ':' || visit.eligible_count::text || ':'
                    || COALESCE(visit.produced_at::text, 'missing'),
                'fieldops_visits'::text,
                COALESCE(visit.produced_at::text, visit.period),
                2::integer,
                'visit-author-team-leader-snapshot-v2'::text,
                CASE
                    WHEN visit.covered_count = visit.eligible_count THEN 'official'::text
                    ELSE 'partial'::text
                END,
                visit.cutoff,
                visit.cutoff,
                false,
                visit.covered_count,
                visit.eligible_count,
                visit.produced_at,
                array_remove(
                    ARRAY[
                        CASE
                            WHEN visit.missing_team_leader_count > 0
                            THEN 'unassigned_visit_team_leader'
                        END,
                        CASE
                            WHEN visit.unmapped_store_count > 0
                            THEN 'unmapped_visit_store'
                        END
                    ]::text[],
                    NULL
                )
            FROM visit_source AS visit
        $view$;
    END IF;
END
$publish_source_snapshot_v2$;

DO $publish_visit_month_v2$
BEGIN
    IF to_regclass('public.fieldops_visits') IS NULL THEN
        EXECUTE $view$
            CREATE OR REPLACE VIEW reporting_visit_month_v2 (
                period,
                team_leader_id,
                team_leader_name,
                site_code,
                locatie,
                firma,
                regional,
                asm,
                total_visits,
                avg_completion,
                avg_duration,
                distinct_stores,
                checklist_score,
                approved_pct,
                source,
                source_generation,
                authority,
                authority_head,
                contract_version,
                rule_version,
                status,
                as_of,
                cutoff,
                is_final,
                coverage_numerator,
                coverage_denominator,
                produced_at,
                warnings
            )
            WITH (security_barrier = true)
            AS
            SELECT
                NULL::text,
                NULL::text,
                NULL::text,
                NULL::text,
                NULL::text,
                NULL::text,
                NULL::text,
                NULL::text,
                NULL::bigint,
                NULL::numeric,
                NULL::numeric,
                NULL::bigint,
                NULL::numeric,
                NULL::numeric,
                NULL::text,
                NULL::text,
                NULL::text,
                NULL::text,
                NULL::integer,
                NULL::text,
                NULL::text,
                NULL::date,
                NULL::date,
                NULL::boolean,
                NULL::bigint,
                NULL::bigint,
                NULL::timestamp without time zone,
                ARRAY[]::text[]
            WHERE false
        $view$;
    ELSE
        EXECUTE $view$
            CREATE OR REPLACE VIEW reporting_visit_month_v2 (
                period,
                team_leader_id,
                team_leader_name,
                site_code,
                locatie,
                firma,
                regional,
                asm,
                total_visits,
                avg_completion,
                avg_duration,
                distinct_stores,
                checklist_score,
                approved_pct,
                source,
                source_generation,
                authority,
                authority_head,
                contract_version,
                rule_version,
                status,
                as_of,
                cutoff,
                is_final,
                coverage_numerator,
                coverage_denominator,
                produced_at,
                warnings
            )
            WITH (security_barrier = true)
            AS
            WITH visit_aggregate AS (
                SELECT
                    to_char(date_trunc('month', visit.data_raport), 'YYYY-MM') AS period,
                    COALESCE(
                        NULLIF(BTRIM(visit.team_leader_id), ''),
                        'name:' || LOWER(NULLIF(BTRIM(visit.team_leader_name), '')),
                        '__UNASSIGNED__'
                    ) AS team_leader_id,
                    COALESCE(
                        NULLIF(BTRIM(visit.team_leader_name), ''),
                        'Fără TL atribuit'
                    ) AS team_leader_name,
                    store.site_code,
                    store.locatie,
                    store.firma,
                    store.regional,
                    store.asm,
                    COUNT(*)::bigint AS total_visits,
                    ROUND(AVG(visit.completion_pct)::numeric, 1) AS avg_completion,
                    ROUND(AVG(visit.durata_vizita_ore)::numeric, 2) AS avg_duration,
                    COUNT(DISTINCT store.site_code)::bigint AS distinct_stores,
                    ROUND(
                        AVG(
                            (
                                COALESCE(visit.curatenie, false)::integer
                                + COALESCE(visit.imagine, false)::integer
                                + COALESCE(visit.uniforma, false)::integer
                                + COALESCE(visit.afise, false)::integer
                                + COALESCE(visit.produse_promo, false)::integer
                            ) * 20.0
                        )::numeric,
                        1
                    ) AS checklist_score,
                    ROUND(
                        COUNT(*) FILTER (WHERE visit.status = 'approved') * 100.0 / COUNT(*),
                        1
                    ) AS approved_pct
                FROM fieldops_visits AS visit
                JOIN stores AS store
                  ON store.site_code = visit.magazin
                WHERE visit.status <> 'draft'
                  AND visit.data_raport IS NOT NULL
                  AND store.locatie NOT ILIKE 'TR %'
                  AND store.locatie NOT ILIKE '%cartel%'
                GROUP BY
                    to_char(date_trunc('month', visit.data_raport), 'YYYY-MM'),
                    COALESCE(
                        NULLIF(BTRIM(visit.team_leader_id), ''),
                        'name:' || LOWER(NULLIF(BTRIM(visit.team_leader_name), '')),
                        '__UNASSIGNED__'
                    ),
                    COALESCE(
                        NULLIF(BTRIM(visit.team_leader_name), ''),
                        'Fără TL atribuit'
                    ),
                    store.site_code,
                    store.locatie,
                    store.firma,
                    store.regional,
                    store.asm
            )
            SELECT
                visit.period,
                visit.team_leader_id,
                visit.team_leader_name,
                visit.site_code,
                visit.locatie,
                visit.firma,
                visit.regional,
                visit.asm,
                visit.total_visits,
                visit.avg_completion,
                visit.avg_duration,
                visit.distinct_stores,
                visit.checklist_score,
                visit.approved_pct,
                snapshot.source,
                snapshot.source_generation,
                snapshot.authority,
                snapshot.authority_head,
                snapshot.contract_version,
                snapshot.rule_version,
                snapshot.status,
                snapshot.as_of,
                snapshot.cutoff,
                snapshot.is_final,
                snapshot.coverage_numerator,
                snapshot.coverage_denominator,
                snapshot.produced_at,
                snapshot.warnings
            FROM visit_aggregate AS visit
            JOIN reporting_source_snapshot_v2 AS snapshot
              ON snapshot.domain = 'visits'
             AND snapshot.period = visit.period
        $view$;
    END IF;
END
$publish_visit_month_v2$;

COMMENT ON VIEW reporting_source_snapshot_v2 IS
    'V2 Insight source metadata; Visits uses the authoritative FieldOps Team Leader snapshot while all other v1 domains remain rollback-compatible.';
COMMENT ON VIEW reporting_visit_month_v2 IS
    'Authoritative FieldOps visit aggregates grouped by visit author Team Leader snapshot and current store hierarchy; empty when the external authority is absent.';

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'unihub_insight_reader') THEN
        EXECUTE 'GRANT SELECT ON TABLE '
            || 'reporting_source_snapshot_v2, reporting_visit_month_v2 '
            || 'TO unihub_insight_reader';
    END IF;
END
$$;
