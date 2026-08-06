-- Correct the Visits completion semantic without rewriting FieldOps history.
--
-- Some PostgreSQL-native FieldOps updates retained the first non-zero
-- completion_pct instead of recalculating it after later autosaves. The
-- authoritative visit fields remain intact, so the reporting contract derives
-- the percentage from the same 19-field formula used by FieldOps. The relation
-- shape stays v2-compatible; source_generation and rule_version change so
-- consumers cannot reuse a snapshot produced under the stale rule.

DO $publish_source_snapshot_v2$
BEGIN
    IF to_regclass('public.fieldops_visits') IS NOT NULL THEN
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
                'fieldops-visits-v3:' || visit.period || ':' || visit.eligible_count::text || ':'
                    || COALESCE(visit.produced_at::text, 'missing'),
                'fieldops_visits'::text,
                COALESCE(visit.produced_at::text, visit.period),
                2::integer,
                'visit-author-team-leader-recomputed-completion-v3'::text,
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
    IF to_regclass('public.fieldops_visits') IS NOT NULL THEN
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
            WITH canonical_visit AS (
                SELECT
                    visit.*,
                    ROUND(
                        (
                            (visit.durata_vizita_ore IS NOT NULL AND visit.durata_vizita_ore <> 0)::integer
                            + COALESCE(visit.curatenie, false)::integer
                            + COALESCE(visit.imagine, false)::integer
                            + COALESCE(visit.uniforma, false)::integer
                            + COALESCE(visit.afise, false)::integer
                            + COALESCE(visit.produse_promo, false)::integer
                            + (visit.tpu IS NOT NULL AND visit.tpu <> 0)::integer
                            + (visit.sticla IS NOT NULL AND visit.sticla <> 0)::integer
                            + (visit.altele IS NOT NULL AND visit.altele <> 0)::integer
                            + COALESCE(visit.avizat, false)::integer
                            + COALESCE(visit.avize, false)::integer
                            + (visit.charisma IS NOT NULL AND visit.charisma <> 0)::integer
                            + (visit.casa IS NOT NULL AND visit.casa <> 0)::integer
                            + (visit.incarcari_epay IS NOT NULL AND visit.incarcari_epay <> 0)::integer
                            + (
                                visit.incarcari_charisma IS NOT NULL
                                AND visit.incarcari_charisma <> 0
                            )::integer
                            + (
                                NULLIF(BTRIM(visit.agent1_nume), '') IS NOT NULL
                                AND BTRIM(visit.agent1_nume) NOT IN ('0', 'FALSE', 'false')
                            )::integer
                            + (visit.agent1_perf IS NOT NULL AND visit.agent1_perf <> 0)::integer
                            + (
                                visit.agent1_doi_pe_bon IS NOT NULL
                                AND visit.agent1_doi_pe_bon <> 0
                            )::integer
                            + (visit.agent1_focus IS NOT NULL AND visit.agent1_focus <> 0)::integer
                        ) * 100.0 / 19.0
                    )::integer AS canonical_completion_pct
                FROM fieldops_visits AS visit
                WHERE visit.status <> 'draft'
                  AND visit.data_raport IS NOT NULL
            ),
            visit_aggregate AS (
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
                    ROUND(AVG(visit.canonical_completion_pct)::numeric, 1) AS avg_completion,
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
                FROM canonical_visit AS visit
                JOIN stores AS store
                  ON store.site_code = visit.magazin
                WHERE store.locatie NOT ILIKE 'TR %'
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
