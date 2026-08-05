-- Deny-in-depth for the retired broad runtime role.  The role may remain as a
-- NOLOGIN compatibility principal, but it must not retain Grile authority.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'unihub_runtime') THEN
        REVOKE ALL ON TABLE
            agent_targets,
            grile_sheets,
            grile_runs,
            grile_store_status,
            grile_store_current_status,
            grile_store_observations,
            grile_store_projection_generations,
            grile_store_refreshes,
            grile_run_store_generations,
            grile_monthly_operations,
            grile_monthly_manifests,
            grile_monthly_reset_items,
            grile_agent_target_sync_runs
        FROM unihub_runtime;

        REVOKE ALL ON SEQUENCE
            grile_runs_id_seq,
            grile_store_observations_id_seq,
            grile_store_refreshes_id_seq,
            grile_monthly_operations_id_seq,
            grile_monthly_manifests_id_seq,
            grile_monthly_reset_items_id_seq,
            grile_agent_target_sync_runs_id_seq
        FROM unihub_runtime;
    END IF;
END
$$;
