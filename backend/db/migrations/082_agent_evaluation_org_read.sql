-- Agent evaluation already uses this current-store hierarchy for peer history.
-- Grant the same read-only application authority as its underlying store catalog.
GRANT SELECT ON v_retail_current_store_org TO unihub_web_read;
