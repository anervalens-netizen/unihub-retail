-- The Grile V2 pilot source snapshot runs under the operations worker role.
-- Grant only the base tables and reporting view dependencies that the
-- read_earnings_sources -> calendar/incentive/forecast path reads directly.
GRANT SELECT ON TABLE
    agent_salary_links,
    grile_agent_target_settings,
    grile_calendar_roster,
    grile_calendar_days,
    grile_calendar_store_hours,
    grile_calendar_closures,
    grile_calendar_transfers,
    grile_calendar_compensation,
    reporting_grile_agent_targets_v2,
    incentive_campaigns,
    incentive_products,
    sales_transactions,
    import_snapshots
TO unihub_operations;
