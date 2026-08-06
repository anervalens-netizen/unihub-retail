/* GENERATED FILE. Run npm run contracts:generate; do not edit manually. */
export const RETAIL_OPENAPI_SHA256 = '50500c82375f8685c642a46f9dc2b39e60e0e04f6fd63e1b11f6633fd8501969' as const;

export interface RetailAgentEvaluationOption {
  "label": string;
  "value": string;
}

export interface RetailAgentEvaluationResponse {
  "asms": Array<RetailAgentEvaluationOption>;
  "firmas": Array<RetailAgentEvaluationOption>;
  "months": Array<RetailAgentEvaluationOption>;
  "rows": Array<RetailAgentEvaluationRow>;
  "stores": Array<RetailAgentEvaluationOption>;
}

export interface RetailAgentEvaluationRow {
  "agent": string;
  "asm": string;
  "bonuri_pct": string | null;
  "bonuri_points": number;
  "daily_average": string | null;
  "daily_points": number;
  "firma": string;
  "focus_pct": string | null;
  "focus_points": number;
  "focus_quantity": number;
  "glass_qty": number;
  "has_red_segment": boolean;
  "locatie": string;
  "month": string;
  "peer_daily_average": string | null;
  "premium_glass_pct": string | null;
  "premium_glass_points": number;
  "premium_glass_qty": number;
  "qualifier": "Excelent" | "Foarte Bun" | "Bun" | "Mediu" | "Scazut";
  "receipt_2plus_count": number;
  "receipt_count": number;
  "regional": string;
  "site_code": string;
  "store_target": string;
  "store_working_days": number;
  "target_pct": string | null;
  "target_points": number;
  "target_value": string;
  "total_points": number;
  "total_quantity": number;
  "total_sales": string;
  "value_reper": string | null;
  "value_reper_points": number;
  "working_days": number;
}

export interface RetailAgentEvaluationV2Response {
  "asms": Array<RetailAgentEvaluationOption>;
  "firmas": Array<RetailAgentEvaluationOption>;
  "months": Array<RetailAgentEvaluationOption>;
  "rows": Array<RetailAgentEvaluationV2Row>;
  "stores": Array<RetailAgentEvaluationOption>;
}

export interface RetailAgentEvaluationV2Row {
  "agent": string;
  "asm": string;
  "bonuri_pct": string | null;
  "bonuri_score": string | null;
  "confidence_flags": Array<string>;
  "daily_average": string | null;
  "daily_reference": string | null;
  "daily_reference_type": "colegi" | "istoric_locatie" | "media_manager" | "none";
  "daily_score": string | null;
  "daily_vs_reference_pct": string | null;
  "eligibility_status": "eligibil" | "insuficient";
  "final_month_count": number;
  "firma": string;
  "focus_pct": string | null;
  "focus_quantity": number;
  "focus_score": string | null;
  "forecast_factor": string;
  "forecast_sales": string;
  "glass_qty": number;
  "is_partial": boolean;
  "locatie": string;
  "max_score"?: number;
  "month": string;
  "partial_month_count": number;
  "period_month_count": number;
  "premium_glass_pct": string | null;
  "premium_glass_qty": number;
  "premium_glass_score": string | null;
  "rating": "Insuficient" | "Fara scor" | "Excelent" | "Foarte Bun" | "Bun" | "Risc" | "Critic";
  "receipt_2plus_count": number;
  "receipt_count": number;
  "regional": string;
  "site_code": string;
  "target_forecast_pct": string | null;
  "target_pct": string | null;
  "target_score": string | null;
  "target_source": "partial_agent_target" | "allocated_store_target";
  "target_value": string;
  "total_quantity": number;
  "total_sales": string;
  "total_score": string | null;
  "trend_daily_pct": string | null;
  "trend_direction": "up" | "down" | "flat";
  "value_reper": string | null;
  "value_reper_score": string | null;
  "working_days": number;
}

export interface RetailAgentHistoryPoint {
  "active_store_count": number;
  "is_active": boolean;
  "month": string;
  "receipt_count": number;
  "total_quantity": number;
  "total_sales": string;
}

export interface RetailAgentHistoryResponse {
  "history": Array<RetailAgentHistoryPoint>;
}

export interface RetailAgentListItem {
  "active_in_month": boolean;
  "agent": string;
  "current_status": "active" | "inactive_recent" | "churned";
  "firma"?: string | null;
  "is_new": boolean;
  "is_reactivated": boolean;
  "store_name"?: string | null;
  "total_quantity": number;
  "total_sales": string;
}

export interface RetailAgentListResponse {
  "items": Array<RetailAgentListItem>;
}

export interface RetailAgentMovementPoint {
  "active": number;
  "churned": number;
  "is_baseline"?: boolean;
  "month": string;
  "net_growth"?: number;
  "new": number;
  "reactivated": number;
}

export interface RetailAgentMovementResponse {
  "history": Array<RetailAgentMovementPoint>;
}

export interface RetailAgentOption {
  "agent": string;
  "asm": string;
  "firma": string;
  "locatie": string;
  "regional": string;
  "site_code": string;
}

export interface RetailAgentProfileResponse {
  "active_months_count": number;
  "agent": string;
  "avg_monthly_sales": string;
  "best_month": string | null;
  "best_month_sales": string;
  "career_total_quantity": number;
  "career_total_sales": string;
  "current_status": "active" | "inactive_recent" | "churned";
  "distinct_asm_count": number;
  "distinct_firma_count": number;
  "distinct_regional_count": number;
  "distinct_store_count": number;
  "first_seen_month": string;
  "last_seen_month": string;
  "longest_active_streak": number;
  "months_since_last_seen": number;
  "reactivation_count": number;
}

export interface RetailAgentSalaryLinkPublic {
  "agent_code": string;
  "confidence": "high" | "medium" | "low" | "unknown";
  "effective_from_month": string | null;
  "match_source": "auto" | "manual";
  "match_status": "confirmed" | "unknown";
  "note": string | null;
  "person_id": string | null;
  "salary_full_name": string | null;
  "site_code": string;
}

export interface RetailAgentStats {
  "acc_focus_qty": number;
  "acc_qty_realizat": number;
  "agent": string;
  "asm": string;
  "firma": string;
  "import_month": string;
  "incentive_qty"?: number;
  "locatie": string;
  "medie_produs"?: string | null;
  "medie_zilnica": string | null;
  "nr_bon2acc": number;
  "nr_bonuri": number;
  "prc_focus_acc_qty": string | null;
  "proc_bon2acc": string | null;
  "proc_realizare_target"?: string | null;
  "promo_discount_value"?: string;
  "promo_qty"?: number;
  "regional": string;
  "return_receipt_count"?: number;
  "site_code": string;
  "target"?: string | null;
  "total_vanzari": string;
  "zile_lucrate": number;
}

export interface RetailAgentTargetRunRequest {
  "month": string;
}

export interface RetailAgentsOverviewResponse {
  "active_count": number;
  "avg_seniority_months": string | null;
  "churned_total_count": number;
  "left_this_month_count": number;
  "new_count": number;
  "reactivated_count": number;
  "retention_rate": string | null;
  "stability_rate": string | null;
  "total_unique_agents": number;
}

export interface RetailAiForecastDailyPoint {
  "actual_sales": string;
  "cumulative_actual": string;
  "cumulative_forecast": string;
  "forecast_date": string;
  "forecast_sales": string;
}

export interface RetailAiForecastManagerRow {
  "actual_sales": string;
  "delta_pct"?: string | null;
  "delta_sales": string;
  "expected_sales_to_date": string;
  "forecast_sales": string;
  "manager": string;
  "store_count": number;
}

export interface RetailAiForecastResponse {
  "daily"?: Array<RetailAiForecastDailyPoint>;
  "managers"?: Array<RetailAiForecastManagerRow>;
  "run": RetailAiForecastRunInfo;
  "stores"?: Array<RetailAiForecastStoreRow>;
  "summary": RetailAiForecastSummary;
}

export interface RetailAiForecastRollingManagerRow {
  "actual_sales"?: string | null;
  "delta_pct"?: string | null;
  "delta_sales"?: string | null;
  "forecast_sales": string;
  "manager": string;
  "store_count": number;
}

export interface RetailAiForecastRollingMonthlyPoint {
  "actual_sales"?: string | null;
  "delta_pct"?: string | null;
  "delta_sales"?: string | null;
  "forecast_month": string;
  "forecast_sales": string;
  "store_count": number;
}

export interface RetailAiForecastRollingResponse {
  "managers"?: Array<RetailAiForecastRollingManagerRow>;
  "months"?: Array<RetailAiForecastRollingMonthlyPoint>;
  "runs"?: Array<RetailAiForecastRunInfo>;
  "stores"?: Array<RetailAiForecastRollingStoreRow>;
  "summary": RetailAiForecastRollingSummary;
}

export interface RetailAiForecastRollingStoreRow {
  "actual_sales"?: string | null;
  "asm": string;
  "delta_pct"?: string | null;
  "delta_sales"?: string | null;
  "firma": string;
  "forecast_sales": string;
  "locatie": string;
  "regional": string;
  "site_code": string;
}

export interface RetailAiForecastRollingSummary {
  "actual_sales"?: string | null;
  "delta_pct"?: string | null;
  "delta_sales"?: string | null;
  "end_month": string;
  "forecast_sales": string;
  "month_count": number;
  "source_month": string;
  "start_month": string;
  "store_count": number;
}

export interface RetailAiForecastRunInfo {
  "forecast_month": string;
  "generated_at": string;
  "horizon"?: "current_month" | "rolling_12m";
  "id": number;
  "metadata"?: Record<string, unknown>;
  "metric"?: "sales_value" | "units";
  "model_mode": string;
  "model_name": string;
  "source_month": string;
  "variant": string;
}

export interface RetailAiForecastStoreRow {
  "actual_sales": string;
  "asm": string;
  "delta_pct"?: string | null;
  "delta_sales": string;
  "expected_sales_to_date": string;
  "firma": string;
  "forecast_sales": string;
  "locatie": string;
  "regional": string;
  "site_code": string;
}

export interface RetailAiForecastSummary {
  "actual_last_date"?: string | null;
  "actual_sales": string;
  "days_elapsed"?: number;
  "days_in_month": number;
  "delta_pct"?: string | null;
  "delta_sales": string;
  "expected_sales_to_date": string;
  "forecast_month": string;
  "forecast_sales": string;
  "source_month": string;
  "store_count": number;
}

export interface RetailAsmStats {
  "asm": string;
  "incentive_qty"?: number;
  "medie_produs"?: string | null;
  "medie_zilnica": string | null;
  "nr_agenti": number;
  "nr_bonuri": number;
  "prc_focus_acc_qty": string | null;
  "proc_bon2acc": string | null;
  "proc_realizare_target": string | null;
  "promo_discount_value"?: string;
  "promo_qty"?: number;
  "qty_total": number;
  "regional": string;
  "target": string;
  "total_vanzari": string;
  "zile_active": number;
}

export interface RetailBody_reconcile_erp_report_file_api_import_erp_reconciliation_post {
  "file": string;
  "import_month": string;
}

export interface RetailBody_upload_promo_actuals_file_api_import_promo_actuals_post {
  "cutoff_date": string;
  "file": string;
  "import_month": string;
}

export interface RetailBody_upload_sales_file_api_import_sales_post {
  "cutoff_date": string;
  "file": string;
}

export interface RetailBrandMixItem {
  "brand": string;
  "quantity_total": number;
  "sales_total": string;
  "share_pct": string | null;
}

export interface RetailCampaignOverview {
  "active_focus_products": number;
  "active_focus_stores": number;
  "focus_share_pct": string | null;
  "month": string;
  "total_focus_qty": number;
  "total_focus_sales": string;
}

export interface RetailCampaignProductStat {
  "item_code": string;
  "item_name": string;
  "qty_total": number;
  "sales_total": string;
  "store_count": number;
}

export interface RetailCampaignPromotionOption {
  "key": string;
  "label": string;
}

export interface RetailCampaignSnapshot {
  "overview": RetailCampaignOverview;
  "products": Array<RetailCampaignProductStat>;
  "stores": Array<RetailCampaignStoreStat>;
}

export interface RetailCampaignStoreStat {
  "active_products": number;
  "locatie": string;
  "qty_total": number;
  "sales_total": string;
  "site_code": string;
}

export interface RetailCampaignsPromotionsResponse {
  "calculation_warnings"?: Array<string>;
  "has_active_promotion"?: boolean;
  "incentive_calculation_status"?: "complete" | "invalid" | "not_configured";
  "incentive_categories"?: Array<RetailIncentiveCategory>;
  "incentive_category_breakdown"?: Array<RetailIncentiveCategoryBreakdown>;
  "incentive_description"?: string;
  "incentive_periods"?: Array<RetailIncentivePeriodStat>;
  "incentive_potential"?: number | null;
  "incentive_product_count"?: number;
  "incentive_qty"?: number | null;
  "incentive_qualified_agents"?: number;
  "incentive_qualified_agents_full"?: number;
  "incentive_qualified_agents_half"?: number;
  "incentive_qualified_qty"?: number | null;
  "incentive_qualified_stores"?: number;
  "incentive_qualified_stores_full"?: number;
  "incentive_qualified_stores_half"?: number;
  "incentive_sold_qty"?: number;
  "incentive_title"?: string;
  "incentive_value"?: number | null;
  "promo_active_agents"?: number;
  "promo_active_stores"?: number;
  "promo_agents"?: Array<RetailPromoTopAgent>;
  "promo_calculation_status"?: "complete" | "partial" | "invalid" | "not_configured";
  "promo_category_qty"?: number | null;
  "promo_description"?: string;
  "promo_discount_value"?: string;
  "promo_discounted_units"?: number;
  "promo_impact"?: number;
  "promo_qty"?: number;
  "promo_qualifying_bons"?: number;
  "promo_title"?: string;
  "promo_total_qty"?: number;
  "promotions"?: Array<RetailCampaignPromotionOption>;
  "selected_promotion_key"?: string;
  "top_agents"?: Array<RetailIncentiveTopAgent>;
  "top_stores"?: Array<RetailPromoTopStore>;
}

export interface RetailCategoryMixItem {
  "category": string;
  "quantity_total": number;
  "sales_total": string;
  "share_pct": string | null;
}

export interface RetailContestLeaderboardRow {
  "agent": string;
  "firma"?: string | null;
  "focus_points"?: number;
  "focus_units"?: number;
  "price_points"?: number;
  "price_units"?: number;
  "prize"?: string | null;
  "promo_bonuri"?: number;
  "promo_points"?: number;
  "rank": number;
  "site_code"?: string | null;
  "store_name"?: string | null;
  "total_points"?: number;
}

export interface RetailContestPrizeInfo {
  "label": string;
  "rank_from": number;
  "rank_to": number;
}

export interface RetailContestResponse {
  "end_date": string;
  "identity_policy"?: "site_agent" | "person_id";
  "key": string;
  "leaderboard"?: Array<RetailContestLeaderboardRow>;
  "month": string;
  "prizes"?: Array<RetailContestPrizeInfo>;
  "rules"?: Array<RetailContestRuleInfo>;
  "scope_label"?: string;
  "start_date": string;
  "store_count"?: number;
  "subtitle"?: string;
  "title": string;
}

export interface RetailContestRuleInfo {
  "label": string;
  "points": number;
  "threshold"?: number | null;
  "type": string;
}

export interface RetailDailySalesPoint {
  "receipt_count": number;
  "sale_date": string;
  "total_quantity": number;
  "total_sales": string;
}

export interface RetailDashboardAllBatchRequest {
  "queries": Array<RetailDashboardAllQuery>;
}

export interface RetailDashboardAllBatchResponse {
  "results": Array<RetailDashboardAllResponse>;
}

export interface RetailDashboardAllQuery {
  "agent"?: string | null;
  "asm"?: string | null;
  "current_scope"?: boolean;
  "firma"?: string | null;
  "include_closed_stores"?: boolean;
  "month": string;
  "regional"?: string | null;
  "site_code"?: string | null;
}

export interface RetailDashboardAllResponse {
  "agents": Array<RetailAgentStats>;
  "asms"?: Array<RetailAsmStats>;
  "brand_mix"?: Array<RetailBrandMixItem>;
  "category_mix"?: Array<RetailCategoryMixItem>;
  "daily": Array<RetailDailySalesPoint>;
  "daily_last_year"?: Array<RetailDailySalesPoint>;
  "focus_subcategory_mix"?: Array<RetailCategoryMixItem>;
  "period_comparison"?: RetailPeriodComparisonPayload | null;
  "premium_glass"?: RetailPremiumGlassAnalysis | null;
  "promo_incentive"?: RetailPromoIncentiveSummary;
  "receipt_bucket_mix"?: Array<RetailReceiptBucketItem>;
  "regionals"?: Array<RetailRegionalStats>;
  "special_cards"?: Array<RetailDashboardSpecialCard>;
  "stores": Array<RetailStoreStats>;
  "summary": RetailDashboardSummary;
}

export interface RetailDashboardHistoryResponse {
  "history": Array<RetailMonthlyHistoryPoint>;
}

export interface RetailDashboardSpecialCard {
  "coverage_note"?: string | null;
  "description": string;
  "highlight_value": string;
  "key": "promotion" | "incentive" | "premium_glass";
  "metrics"?: Array<RetailDashboardSpecialCardMetric>;
  "status": "ready" | "inactive" | "no_data" | "missing_config" | "missing_source" | "limited_scope";
  "status_label": string;
  "subtitle"?: string | null;
  "title": string;
}

export interface RetailDashboardSpecialCardMetric {
  "label": string;
  "value": string;
}

export interface RetailDashboardSpecialCardsResponse {
  "cards"?: Array<RetailDashboardSpecialCard>;
}

export interface RetailDashboardSummary {
  "cartele_qty"?: number;
  "daily_average": string | null;
  "days_in_month"?: number | null;
  "forecast_sales"?: string | null;
  "forecast_target_progress_pct"?: string | null;
  "imported_day_of_month"?: number | null;
  "is_month_final"?: boolean;
  "last_sale_date"?: string | null;
  "medie_produs"?: string | null;
  "month": string;
  "prc_focus_acc_qty": string | null;
  "proc_bon2acc": string | null;
  "target_progress_pct": string | null;
  "total_agents": number;
  "total_quantity": number;
  "total_receipts": number;
  "total_sales": string;
  "total_stores": number;
  "total_target": string;
  "working_days": number;
}

export interface RetailErpReconciliationAppMetric {
  "key": string;
  "label": string;
  "note": string;
  "unit": "RON" | "buc";
  "value"?: string | null;
}

export interface RetailErpReconciliationIssue {
  "difference"?: string | null;
  "entity": string;
  "metric": string;
  "note": string;
  "report_value"?: string | null;
  "retail_value"?: string | null;
  "scope": "report" | "store" | "agent";
  "severity": "warning" | "error";
  "site_code"?: string | null;
}

export interface RetailErpReconciliationMetric {
  "difference"?: string | null;
  "key": string;
  "label": string;
  "note"?: string | null;
  "report_value"?: string | null;
  "retail_value"?: string | null;
  "status": "ok" | "explained" | "difference" | "not_comparable";
  "unit": "RON" | "buc" | "bonuri" | "magazine" | "agenti";
}

export interface RetailErpReconciliationResponse {
  "app_only_metrics": Array<RetailErpReconciliationAppMetric>;
  "cutoff_matches": boolean;
  "file_digest": string;
  "filename": string;
  "import_month": string;
  "issue_count": number;
  "issues": Array<RetailErpReconciliationIssue>;
  "metrics": Array<RetailErpReconciliationMetric>;
  "notes": Array<string>;
  "omitted_issue_count": number;
  "report_agent_count": number;
  "report_cutoff_date": string;
  "report_store_count": number;
  "retail_agent_count": number;
  "retail_cutoff_date": string | null;
  "retail_store_count": number;
  "status": "ok" | "differences";
}

export interface RetailExportFilters {
  "agent"?: Array<string>;
  "asm"?: Array<string>;
  "firma"?: Array<string>;
  "regional"?: Array<string>;
  "site_code"?: Array<string>;
}

export interface RetailExportRequest {
  "comparison_levels"?: Array<string>;
  "daily_metrics"?: Array<string>;
  "dataset": string;
  "dimensions"?: Array<string>;
  "export_mode"?: string;
  "filename"?: string | null;
  "filters"?: RetailExportFilters;
  "include_closed_stores"?: boolean;
  "metrics"?: Array<string>;
  "monthly_metrics"?: Array<string>;
  "months": Array<string>;
  "preview_limit"?: number;
  "selected_days"?: Array<number>;
}

export interface RetailFilterOptions {
  "agenti": Array<RetailAgentOption>;
  "asmi": Array<string>;
  "firme": Array<string>;
  "magazine": Array<RetailStoreOption>;
  "regionali": Array<string>;
}

export interface RetailFocusHistoryPoint {
  "active_focus_products": number;
  "active_focus_stores": number;
  "focus_share_pct": string | null;
  "month": string;
  "total_focus_qty": number;
  "total_focus_sales": string;
}

export interface RetailFocusHistoryResponse {
  "history": Array<RetailFocusHistoryPoint>;
}

export interface RetailHTTPValidationError {
  "detail"?: Array<RetailValidationError>;
}

export interface RetailImportHistoryEntry {
  "coverage_report"?: Record<string, unknown>;
  "created_at": string;
  "duration_seconds"?: number | null;
  "error_message": string | null;
  "filename": string;
  "finished_at"?: string | null;
  "id": number;
  "import_month": string;
  "is_month_final": boolean;
  "rows_imported": number | null;
  "rows_in_file": number | null;
  "status": "processing" | "completed" | "failed";
  "upload_date": string;
}

export interface RetailImportJobStatus {
  "error"?: string | null;
  "job_id": string;
  "result"?: RetailImportResponse | null;
  "status": "queued" | "in_progress" | "complete" | "not_found";
}

export interface RetailImportResponse {
  "agent_count": number;
  "coverage_report"?: Record<string, unknown>;
  "filename": string;
  "generation_state"?: "validated" | "promoted";
  "generation_token"?: string | null;
  "import_month": string;
  "is_month_final": boolean;
  "manifest"?: Record<string, unknown> | null;
  "manifest_sha256"?: string | null;
  "rows_filtered": number;
  "rows_imported": number;
  "rows_in_file": number;
  "snapshot_id": number;
  "store_count": number;
}

export interface RetailIncentiveCategory {
  "label": string;
  "qty": number;
  "value": number;
}

export interface RetailIncentiveCategoryBreakdown {
  "label": string;
  "potential": number;
  "qty": number;
  "qualified_qty": number;
  "value": number;
}

export interface RetailIncentivePeriodStat {
  "end_date": string;
  "label": string;
  "potential"?: number;
  "product_count": number;
  "qty"?: number;
  "reward_values"?: Array<number>;
  "start_date": string;
  "value"?: number;
}

export interface RetailIncentiveTopAgent {
  "achievement"?: number | null;
  "agent_name": string;
  "firma"?: string;
  "incentive_potential"?: number;
  "qty_sold": number;
  "store_name"?: string;
  "val_incentive": number;
}

export interface RetailLeaveRequestCreate {
  "agent_name": string;
  "end_date": string;
  "leave_type": string;
  "notes"?: string | null;
  "start_date": string;
}

export interface RetailLeaveRequestItem {
  "agent_name": string;
  "created_at"?: string | null;
  "end_date": string;
  "id": number;
  "leave_type": string;
  "notes"?: string | null;
  "start_date": string;
  "status": string;
  "updated_at"?: string | null;
}

export interface RetailLeaveRequestListResponse {
  "items": Array<RetailLeaveRequestItem>;
  "limit": number;
  "offset": number;
  "total": number;
}

export interface RetailLeaveStatusUpdate {
  "status": string;
}

export interface RetailMonthlyHistoryPoint {
  "daily_average": string | null;
  "medie_produs"?: string | null;
  "month": string;
  "prc_focus_acc_qty": string | null;
  "proc_bon2acc": string | null;
  "return_receipt_count"?: number;
  "target_progress_pct": string | null;
  "total_agents": number;
  "total_quantity": number;
  "total_receipts": number;
  "total_sales": string;
  "total_stores": number;
  "total_target": string;
  "working_days": number;
}

export interface RetailMonthlyRunRequest {
  "approved_manifest_id"?: number | null;
  "dry_run"?: boolean;
  "month": string;
  "op": "finalize" | "archive" | "reset";
}

export interface RetailPerformanceDetailResponse {
  "context_summary"?: RetailDashboardSummary | null;
  "daily"?: Array<RetailDailySalesPoint>;
  "history"?: Array<RetailMonthlyHistoryPoint>;
  "key": string;
  "level": "regional" | "store" | "agent";
  "month": string;
  "note": string;
  "peer_rows"?: Array<RetailPerformancePeerRow>;
  "risks"?: Array<string>;
  "score": number;
  "score_breakdown": RetailPerformanceScoreBreakdown;
  "score_label": string;
  "strengths"?: Array<string>;
  "subtitle"?: string | null;
  "summary": RetailDashboardSummary;
  "title": string;
}

export interface RetailPerformancePeerRow {
  "forecast_target_pct"?: string | null;
  "is_selected"?: boolean;
  "label": string;
  "prc_focus_acc_qty"?: string | null;
  "proc_bon2acc"?: string | null;
  "rank": number;
  "sublabel"?: string | null;
  "target_progress_pct"?: string | null;
  "total_sales": string;
}

export interface RetailPerformanceScoreBreakdown {
  "bon2acc_points": string;
  "focus_points": string;
  "target_points": string;
}

export interface RetailPeriodComparisonPayload {
  "current": RetailPeriodComparisonPoint;
  "previous": RetailPeriodComparisonPoint;
  "year_over_year": RetailPeriodComparisonPoint;
}

export interface RetailPeriodComparisonPoint {
  "avg_receipt_value": string | null;
  "cartele_qty"?: number;
  "daily_average": string | null;
  "day_range": string;
  "label": string;
  "medie_produs"?: string | null;
  "month": string;
  "prc_focus_acc_qty": string | null;
  "proc_bon2acc": string | null;
  "total_quantity": number;
  "total_receipts": number;
  "total_sales": string;
  "working_days": number;
}

export interface RetailPremiumGlassAgentStat {
  "agent": string;
  "firma": string;
  "locatie": string;
  "premium_qty"?: number;
  "premium_qty_share_pct"?: string | null;
  "premium_sales"?: string;
  "regular_qty"?: number;
  "regular_sales"?: string;
  "site_code": string;
  "total_qty"?: number;
  "total_sales"?: string;
}

export interface RetailPremiumGlassAnalysis {
  "agents"?: Array<RetailPremiumGlassAgentStat>;
  "managers"?: Array<RetailPremiumGlassManagerStat>;
  "models"?: Array<RetailPremiumGlassModelStat>;
  "products"?: Array<RetailPremiumGlassProductStat>;
  "stores"?: Array<RetailPremiumGlassStoreStat>;
  "summary": RetailPremiumGlassSummary;
  "surfaces"?: Array<RetailPremiumGlassSurfaceStat>;
}

export interface RetailPremiumGlassManagerStat {
  "agent_count"?: number;
  "manager": string;
  "premium_qty"?: number;
  "premium_qty_share_pct"?: string | null;
  "premium_sales"?: string;
  "regular_qty"?: number;
  "regular_sales"?: string;
  "store_count"?: number;
  "total_qty"?: number;
  "total_sales"?: string;
}

export interface RetailPremiumGlassModelStat {
  "model_key": string;
  "model_label": string;
  "premium_item_count"?: number;
  "premium_qty"?: number;
  "premium_qty_share_pct"?: string | null;
  "premium_sales"?: string;
  "regular_item_count"?: number;
  "regular_qty"?: number;
  "regular_sales"?: string;
  "total_qty"?: number;
  "total_sales"?: string;
}

export interface RetailPremiumGlassProductStat {
  "is_premium": boolean;
  "item_code": string;
  "item_name": string;
  "model_labels"?: Array<string>;
  "qty"?: number;
  "sales"?: string;
  "store_count"?: number;
}

export interface RetailPremiumGlassStoreStat {
  "firma": string;
  "locatie": string;
  "premium_qty"?: number;
  "premium_qty_share_pct"?: string | null;
  "premium_sales"?: string;
  "regular_qty"?: number;
  "regular_sales"?: string;
  "site_code": string;
  "total_qty"?: number;
  "total_sales"?: string;
}

export interface RetailPremiumGlassSummary {
  "active_agents"?: number;
  "active_stores"?: number;
  "month": string;
  "premium_active_agents"?: number;
  "premium_active_stores"?: number;
  "premium_qty"?: number;
  "premium_qty_share_pct"?: string | null;
  "premium_sales"?: string;
  "premium_sales_share_pct"?: string | null;
  "regular_qty"?: number;
  "regular_sales"?: string;
  "target_model_count"?: number;
  "total_qty"?: number;
  "total_sales"?: string;
}

export interface RetailPremiumGlassSurfaceStat {
  "premium_qty"?: number;
  "premium_qty_share_pct"?: string | null;
  "premium_sales"?: string;
  "regular_qty"?: number;
  "regular_sales"?: string;
  "surface_key": "screen" | "camera";
  "surface_label": string;
  "total_qty"?: number;
  "total_sales"?: string;
}

export interface RetailPromoActualImportResponse {
  "config_sha256": string;
  "cutoff_date": string;
  "filename": string;
  "generation_id": string;
  "import_month": string;
  "material_sha256": string;
  "promo_units": number;
  "report_rows": number;
  "source_sha256": string;
  "updated_promotions": number;
}

export interface RetailPromoIncentiveSummary {
  "calculation_status"?: "complete" | "invalid";
  "calculation_warnings"?: Array<string>;
  "incentive_potential"?: string | null;
  "incentive_qty"?: number | null;
  "incentive_qualified_agents"?: number;
  "incentive_qualified_agents_full"?: number;
  "incentive_qualified_agents_half"?: number;
  "incentive_qualified_qty"?: number | null;
  "incentive_qualified_stores"?: number;
  "incentive_qualified_stores_full"?: number;
  "incentive_qualified_stores_half"?: number;
  "incentive_sales"?: string;
  "incentive_sold_qty"?: number;
  "incentive_value"?: string | null;
  "promo_impact"?: string;
  "promo_qty"?: number;
  "promo_sales"?: string;
}

export interface RetailPromoTopAgent {
  "agent_name": string;
  "firma"?: string;
  "promo_bons"?: number;
  "store_name"?: string;
}

export interface RetailPromoTopStore {
  "achievement"?: number | null;
  "category_qty": number;
  "firma"?: string;
  "incentive_potential"?: number;
  "incentive_value"?: number;
  "promo_bons"?: number;
  "qty": number;
  "store_name": string;
  "total_qty": number;
}

export interface RetailReceiptBucketItem {
  "bucket": string;
  "receipt_count": number;
  "share_pct": string | null;
}

export interface RetailRegionalStats {
  "forecast_target_pct"?: string | null;
  "incentive_qty"?: number;
  "medie_produs"?: string | null;
  "medie_zilnica": string | null;
  "nr_agenti": number;
  "nr_bonuri": number;
  "prc_focus_acc_qty": string | null;
  "proc_bon2acc": string | null;
  "proc_realizare_target": string | null;
  "promo_discount_value"?: string;
  "promo_qty"?: number;
  "qty_total": number;
  "regional": string;
  "return_receipt_count"?: number;
  "target": string;
  "total_vanzari": string;
  "zile_active": number;
}

export interface RetailSalaryAgentSummaryPublic {
  "avg_month_count": number;
  "avg_salary": number;
  "company_name": string;
  "full_name": string;
  "locatie": string | null;
  "month_count": number;
  "person_id": string;
  "total_salary": number;
}

export interface RetailSalaryAgentsSummaryResponse {
  "items": Array<RetailSalaryAgentSummaryPublic>;
  "total": number;
}

export interface RetailSalaryExportAudit {
  "export_kind": "store_summary" | "monthly_trend" | "agents_page";
  "row_count": number;
}

export interface RetailSalaryHistoryRecordPublic {
  "company_name": string;
  "locatie": string | null;
  "month": number;
  "site_code": string | null;
  "total_salary": number;
  "year": number;
}

export interface RetailSalaryHistoryResponse {
  "avg": number;
  "avg_month_count": number;
  "link"?: RetailAgentSalaryLinkPublic | null;
  "month_count": number;
  "records": Array<RetailSalaryHistoryRecordPublic>;
  "total": number;
}

export interface RetailSalaryRecordPublic {
  "company_name": string;
  "full_name": string;
  "id": number;
  "locatie": string | null;
  "month": number;
  "person_id": string;
  "site_code": string | null;
  "total_salary": number;
  "year": number;
}

export interface RetailSalesGenerationPromotionRequest {
  "generation_token": string;
  "manifest_sha256": string;
  "override_reason"?: string | null;
}

export interface RetailStoreActivityChangeRequest {
  "expected_is_active": boolean;
  "is_active": boolean;
  "reason": string;
}

export interface RetailStoreActivityChangeResponse {
  "event_id": number;
  "is_active": boolean;
  "previous_is_active": boolean;
  "site_code": string;
}

export interface RetailStoreCoverageItem {
  "added_agents_count"?: number;
  "agent_count": number;
  "asm": string;
  "change_reason"?: string | null;
  "firma": string;
  "has_changes"?: boolean;
  "locatie": string;
  "previous_agent_count"?: number;
  "regional": string;
  "removed_agents_count"?: number;
  "site_code": string;
  "status": "covered" | "uncovered" | "closed" | "inactive";
}

export interface RetailStoreCoverageResponse {
  "active_stores_count": number;
  "closed_stores_count": number;
  "items": Array<RetailStoreCoverageItem>;
  "modified_stores_count"?: number;
  "uncovered_stores_count": number;
}

export interface RetailStoreOption {
  "asm": string;
  "firma": string;
  "locatie": string;
  "regional": string;
  "site_code": string;
}

export interface RetailStoreStats {
  "asm": string;
  "firma": string;
  "forecast_target_pct"?: string | null;
  "import_month": string;
  "incentive_qty"?: number;
  "locatie": string;
  "medie_produs"?: string | null;
  "nr_agenti": number;
  "nr_bonuri": number;
  "prc_focus_acc_qty"?: string | null;
  "proc_bon2acc"?: string | null;
  "proc_realizare_target": string | null;
  "promo_discount_value"?: string;
  "promo_qty"?: number;
  "qty_total": number | null;
  "regional": string;
  "return_receipt_count"?: number;
  "site_code": string;
  "target": string;
  "total_vanzari": string;
  "zile_active": number;
}

export interface RetailStoreTargetInput {
  "import_month": string;
  "site_code": string;
  "target_value": number | string;
}

export interface RetailTargetCalculationRequest {
  "cohort_month"?: string | null;
  "expected_revision"?: number | null;
  "min_floor"?: number | string;
  "previous_month_cap_pct"?: number | string;
  "previous_month_floor_pct"?: number | string;
  "seasonality_years"?: number;
  "target_month": string;
  "total_target": number | string;
}

export interface RetailTargetFinalRow {
  "final_target"?: number | string | null;
  "note"?: string | null;
  "override_reason"?: string | null;
  "site_code": string;
}

export interface RetailTargetFinalRowsRequest {
  "expected_revision": number;
  "rows": Array<RetailTargetFinalRow>;
}

export interface RetailTargetFinalizeRequest {
  "expected_revision": number;
}

export interface RetailTaskCreate {
  "assignee"?: string | null;
  "deadline"?: string | null;
  "site_code"?: string | null;
  "source"?: string;
  "source_meta"?: Record<string, unknown> | null;
  "status"?: string;
  "title": string;
}

export interface RetailTaskItem {
  "assignee"?: string | null;
  "created_at"?: string | null;
  "deadline"?: string | null;
  "id": number;
  "site_code"?: string | null;
  "source": string;
  "source_meta"?: Record<string, unknown> | null;
  "status": string;
  "title": string;
  "updated_at"?: string | null;
}

export interface RetailTaskListResponse {
  "items": Array<RetailTaskItem>;
  "limit": number;
  "offset": number;
  "total": number;
}

export interface RetailTaskUpdate {
  "assignee"?: string | null;
  "deadline"?: string | null;
  "site_code"?: string | null;
  "status"?: string | null;
  "title"?: string | null;
}

export interface RetailTeamLeaderGroup {
  "months": Array<RetailVisitMonthGroup>;
  "nr_vizite": number;
  "team_leader": string;
}

export interface RetailValidationError {
  "ctx"?: Record<string, unknown>;
  "input"?: unknown;
  "loc": Array<string | number>;
  "msg": string;
  "type": string;
}

export interface RetailVisitDayGroup {
  "date": string;
  "nr_vizite": number;
  "visits": Array<RetailVisitSummaryItem>;
}

export interface RetailVisitDetail {
  "afise": boolean;
  "agent1_analiza": string | null;
  "agent1_doi_pe_bon": number | null;
  "agent1_focus": number | null;
  "agent1_nume": string | null;
  "agent1_perf": number | null;
  "agent1_plan": string | null;
  "agent2_analiza": string | null;
  "agent2_doi_pe_bon": number | null;
  "agent2_focus": number | null;
  "agent2_nume": string | null;
  "agent2_perf": number | null;
  "agent2_plan": string | null;
  "altele": number | null;
  "asm": string | null;
  "avizat": boolean;
  "casa": number | null;
  "charisma": number | null;
  "completion_pct": number;
  "curatenie": boolean;
  "data_raport": string | null;
  "durata_vizita_ore": number | null;
  "firma": string | null;
  "id": string;
  "imagine": boolean;
  "incarcari_charisma": number | null;
  "incarcari_epay": number | null;
  "magazin": string | null;
  "notes": string | null;
  "ora_trimitere": string | null;
  "photos": Array<string>;
  "produse_promo": boolean;
  "regional": string | null;
  "sticla": number | null;
  "team_leader": string | null;
  "tpu": number | null;
  "uniforma": boolean;
}

export interface RetailVisitMonthGroup {
  "days": Array<RetailVisitDayGroup>;
  "month": string;
  "nr_vizite": number;
}

export interface RetailVisitReportResponse {
  "avg_completion": number;
  "magazine_unice": number;
  "month": string;
  "rows": Array<RetailVisitReportRow>;
  "total_vizite": number;
}

export interface RetailVisitReportRow {
  "afise_pct": number;
  "asm": string | null;
  "avg_completion": number;
  "curatenie_pct": number;
  "firma": string | null;
  "imagine_pct": number;
  "last_visit": string | null;
  "magazin": string;
  "nr_vizite": number;
  "produse_promo_pct": number;
  "regional": string | null;
  "uniforma_pct": number;
}

export interface RetailVisitSummaryItem {
  "completion_pct": number;
  "firma": string | null;
  "has_photos": boolean;
  "id": string;
  "locatie": string | null;
  "magazin": string;
  "ora": string | null;
}

export interface RetailVisitTreeResponse {
  "team_leaders": Array<RetailTeamLeaderGroup>;
}

export interface RetailYearHistoryPoint {
  "is_aggregate": boolean;
  "label": string;
  "sort_key": string;
  "total_quantity": number;
  "total_sales": string;
  "total_target": string;
}

export interface RetailYearHistoryResponse {
  "points": Array<RetailYearHistoryPoint>;
}

export type RetailOperationId =
  'get_agent_evaluation_api_agents_evaluation_get' |
  'get_agent_evaluation_v2_api_agents_evaluation_v2_get' |
  'get_agent_history_api_agents_history_get' |
  'get_agents_list_api_agents_list_get' |
  'get_agents_movement_api_agents_movement_get' |
  'get_agents_overview_api_agents_overview_get' |
  'get_agent_profile_api_agents_profile_get' |
  'get_stores_coverage_api_agents_stores_coverage_get' |
  'get_current_ai_forecast_api_ai_forecast_current_get' |
  'get_rolling_12_ai_forecast_api_ai_forecast_rolling_12_get' |
  'get_focus_history_api_campaigns_history_get' |
  'get_campaign_overview_api_campaigns_overview_get' |
  'get_promotions_incentives_api_campaigns_promotions_incentives_get' |
  'get_active_contest_api_contests_active_get' |
  'get_active_contests_api_contests_active_all_get' |
  'get_alerts_api_crm_alerts_get' |
  'get_scores_api_crm_scores_get' |
  'recalculate_scores_api_crm_scores_recalculate_post' |
  'get_dashboard_all_api_dashboard_all_get' |
  'get_dashboard_all_batch_api_dashboard_all_batch_post' |
  'get_daily_sales_api_dashboard_daily_get' |
  'get_monthly_history_api_dashboard_history_get' |
  'get_dashboard_history_details_batch_api_dashboard_history_details_batch_post' |
  'get_history_by_year_api_dashboard_history_year_get' |
  'get_performance_detail_api_dashboard_performance_detail_get' |
  'get_premium_glass_api_dashboard_premium_glass_get' |
  'get_special_cards_api_dashboard_special_cards_get' |
  'get_summary_api_dashboard_summary_get' |
  'get_catalog_api_exports_catalog_get' |
  'download_export_api_exports_download_post' |
  'preview_export_api_exports_preview_post' |
  'get_available_months_api_filters_months_get' |
  'get_filter_options_api_filters_options_get' |
  'grile_agent_targets_diff_api_grile_agent_targets_diff_post' |
  'grile_agent_targets_operation_api_grile_agent_targets_operations__operation_id__get' |
  'grile_agent_targets_sync_api_grile_agent_targets_sync_post' |
  'grile_monthly_download_api_grile_monthly_download__kind___month__get' |
  'grile_monthly_job_api_grile_monthly_job__job_id__get' |
  'grile_monthly_manifest_approve_api_grile_monthly_manifests__manifest_id__approve_post' |
  'grile_monthly_manifest_api_grile_monthly_manifests__month__get' |
  'grile_monthly_permissions_api_grile_monthly_permissions_get' |
  'grile_monthly_run_api_grile_monthly_run_post' |
  'grile_overview_api_grile_overview_get' |
  'grile_run_api_grile_run_post' |
  'grile_run_status_api_grile_run_status_get' |
  'grile_store_refresh_api_grile_stores__site_code__refresh_post' |
  'get_asm_perf_api_hr_asm_performance_get' |
  'get_asm_perf_history_api_hr_asm_performance__asm_name__history_get' |
  'get_asm_salary_api_hr_asm_salary__asm_name__get' |
  'get_leave_requests_api_hr_leave_requests_get' |
  'post_leave_request_api_hr_leave_requests_post' |
  'patch_leave_request_api_hr_leave_requests__request_id__patch' |
  'get_manager_overview_api_hr_manager_overview_get' |
  'get_performance_api_hr_performance__agent_name__get' |
  'reconcile_erp_report_file_api_import_erp_reconciliation_post' |
  'get_import_history_api_import_history_get' |
  'get_import_job_status_api_import_jobs__job_id__get' |
  'upload_promo_actuals_file_api_import_promo_actuals_post' |
  'upload_sales_file_api_import_sales_post' |
  'promote_sales_generation_api_import_sales__snapshot_id__promote_post' |
  'annual_api_store_pnl_annual_get' |
  'months_api_store_pnl_months_get' |
  'overview_api_store_pnl_overview_get' |
  'pnl_permissions_api_store_pnl_permissions_get' |
  'regions_api_store_pnl_regions_get' |
  'stores_api_store_pnl_stores_get' |
  'list_stores_api_stores_get' |
  'save_targets_api_stores_targets_post' |
  'change_store_activity_api_stores__site_code__activity_post' |
  'get_context_api_target_calculator_context_get' |
  'list_scenarios_api_target_calculator_scenarios_get' |
  'calculate_scenario_api_target_calculator_scenarios_calculate_post' |
  'get_scenario_api_target_calculator_scenarios__scenario_id__get' |
  'export_scenario_api_target_calculator_scenarios__scenario_id__export_get' |
  'finalize_scenario_api_target_calculator_scenarios__scenario_id__finalize_post' |
  'update_final_targets_api_target_calculator_scenarios__scenario_id__rows_patch' |
  'get_store_detail_api_target_calculator_scenarios__scenario_id__stores__site_code__get' |
  'get_tasks_api_tasks_get' |
  'post_task_api_tasks_post' |
  'remove_task_api_tasks__task_id__delete' |
  'patch_task_api_tasks__task_id__patch' |
  'get_visits_report_api_visits_report_get' |
  'get_visit_photo_api_visits_report_photo__visit_id___filename__get' |
  'get_visits_tree_api_visits_report_tree_get' |
  'get_visit_detail_api_visits_report_visit__visit_id__get' |
  'session_status_auth_session_get' |
  'session_login_auth_session_login_get' |
  'session_logout_auth_session_logout_post' |
  'metrics_metrics_get' |
  'agent_history_by_retail_code_salarii_agents_history_by_retail_code_get' |
  'agents_summary_salarii_agents_summary_get' |
  'agent_history_salarii_agents__person_id__history_get' |
  'audit_salary_export_salarii_audit_export_post' |
  'salarii_evolution_salarii_evolution_get' |
  'salarii_overview_salarii_overview_get' |
  'list_records_salarii_records_get' |
  'salarii_stores_salarii_stores_get' |
  'salarii_summary_salarii_summary_get' |
  'salarii_trend_salarii_trend_get';

export interface RetailOperationResponses {
  'get_agent_evaluation_api_agents_evaluation_get': {
    '200': RetailAgentEvaluationResponse;
    '422': RetailHTTPValidationError;
  }

  'get_agent_evaluation_v2_api_agents_evaluation_v2_get': {
    '200': RetailAgentEvaluationV2Response;
    '422': RetailHTTPValidationError;
  }

  'get_agent_history_api_agents_history_get': {
    '200': RetailAgentHistoryResponse;
    '422': RetailHTTPValidationError;
  }

  'get_agents_list_api_agents_list_get': {
    '200': RetailAgentListResponse;
    '422': RetailHTTPValidationError;
  }

  'get_agents_movement_api_agents_movement_get': {
    '200': RetailAgentMovementResponse;
    '422': RetailHTTPValidationError;
  }

  'get_agents_overview_api_agents_overview_get': {
    '200': RetailAgentsOverviewResponse;
    '422': RetailHTTPValidationError;
  }

  'get_agent_profile_api_agents_profile_get': {
    '200': RetailAgentProfileResponse;
    '422': RetailHTTPValidationError;
  }

  'get_stores_coverage_api_agents_stores_coverage_get': {
    '200': RetailStoreCoverageResponse;
    '422': RetailHTTPValidationError;
  }

  'get_current_ai_forecast_api_ai_forecast_current_get': {
    '200': RetailAiForecastResponse;
    '422': RetailHTTPValidationError;
  }

  'get_rolling_12_ai_forecast_api_ai_forecast_rolling_12_get': {
    '200': RetailAiForecastRollingResponse;
    '422': RetailHTTPValidationError;
  }

  'get_focus_history_api_campaigns_history_get': {
    '200': RetailFocusHistoryResponse;
    '422': RetailHTTPValidationError;
  }

  'get_campaign_overview_api_campaigns_overview_get': {
    '200': RetailCampaignSnapshot;
    '422': RetailHTTPValidationError;
  }

  'get_promotions_incentives_api_campaigns_promotions_incentives_get': {
    '200': RetailCampaignsPromotionsResponse;
    '422': RetailHTTPValidationError;
  }

  'get_active_contest_api_contests_active_get': {
    '200': RetailContestResponse | null;
    '422': RetailHTTPValidationError;
  }

  'get_active_contests_api_contests_active_all_get': {
    '200': Array<RetailContestResponse>;
    '422': RetailHTTPValidationError;
  }

  'get_alerts_api_crm_alerts_get': {
    '200': unknown;
    '422': RetailHTTPValidationError;
  }

  'get_scores_api_crm_scores_get': {
    '200': unknown;
    '422': RetailHTTPValidationError;
  }

  'recalculate_scores_api_crm_scores_recalculate_post': {
    '200': unknown;
    '422': RetailHTTPValidationError;
  }

  'get_dashboard_all_api_dashboard_all_get': {
    '200': RetailDashboardAllResponse;
    '422': RetailHTTPValidationError;
  }

  'get_dashboard_all_batch_api_dashboard_all_batch_post': {
    '200': RetailDashboardAllBatchResponse;
    '422': RetailHTTPValidationError;
  }

  'get_daily_sales_api_dashboard_daily_get': {
    '200': Array<RetailDailySalesPoint>;
    '422': RetailHTTPValidationError;
  }

  'get_monthly_history_api_dashboard_history_get': {
    '200': RetailDashboardHistoryResponse;
    '422': RetailHTTPValidationError;
  }

  'get_dashboard_history_details_batch_api_dashboard_history_details_batch_post': {
    '200': RetailDashboardAllBatchResponse;
    '422': RetailHTTPValidationError;
  }

  'get_history_by_year_api_dashboard_history_year_get': {
    '200': RetailYearHistoryResponse;
    '422': RetailHTTPValidationError;
  }

  'get_performance_detail_api_dashboard_performance_detail_get': {
    '200': RetailPerformanceDetailResponse;
    '422': RetailHTTPValidationError;
  }

  'get_premium_glass_api_dashboard_premium_glass_get': {
    '200': RetailPremiumGlassAnalysis;
    '422': RetailHTTPValidationError;
  }

  'get_special_cards_api_dashboard_special_cards_get': {
    '200': RetailDashboardSpecialCardsResponse;
    '422': RetailHTTPValidationError;
  }

  'get_summary_api_dashboard_summary_get': {
    '200': RetailDashboardSummary;
    '422': RetailHTTPValidationError;
  }

  'get_catalog_api_exports_catalog_get': {
    '200': Record<string, unknown>;
  }

  'download_export_api_exports_download_post': {
    '200': unknown;
    '422': RetailHTTPValidationError;
  }

  'preview_export_api_exports_preview_post': {
    '200': Record<string, unknown>;
    '422': RetailHTTPValidationError;
  }

  'get_available_months_api_filters_months_get': {
    '200': Array<string>;
  }

  'get_filter_options_api_filters_options_get': {
    '200': RetailFilterOptions;
    '422': RetailHTTPValidationError;
  }

  'grile_agent_targets_diff_api_grile_agent_targets_diff_post': {
    '200': Record<string, unknown>;
    '422': RetailHTTPValidationError;
  }

  'grile_agent_targets_operation_api_grile_agent_targets_operations__operation_id__get': {
    '200': Record<string, unknown>;
    '422': RetailHTTPValidationError;
  }

  'grile_agent_targets_sync_api_grile_agent_targets_sync_post': {
    '200': Record<string, unknown>;
    '422': RetailHTTPValidationError;
  }

  'grile_monthly_download_api_grile_monthly_download__kind___month__get': {
    '200': unknown;
    '422': RetailHTTPValidationError;
  }

  'grile_monthly_job_api_grile_monthly_job__job_id__get': {
    '200': Record<string, unknown>;
    '422': RetailHTTPValidationError;
  }

  'grile_monthly_manifest_approve_api_grile_monthly_manifests__manifest_id__approve_post': {
    '200': Record<string, unknown>;
    '422': RetailHTTPValidationError;
  }

  'grile_monthly_manifest_api_grile_monthly_manifests__month__get': {
    '200': Record<string, unknown>;
    '422': RetailHTTPValidationError;
  }

  'grile_monthly_permissions_api_grile_monthly_permissions_get': {
    '200': Record<string, unknown>;
  }

  'grile_monthly_run_api_grile_monthly_run_post': {
    '200': Record<string, unknown>;
    '422': RetailHTTPValidationError;
  }

  'grile_overview_api_grile_overview_get': {
    '200': Record<string, unknown>;
    '422': RetailHTTPValidationError;
  }

  'grile_run_api_grile_run_post': {
    '200': Record<string, unknown>;
    '422': RetailHTTPValidationError;
  }

  'grile_run_status_api_grile_run_status_get': {
    '200': Record<string, unknown>;
    '422': RetailHTTPValidationError;
  }

  'grile_store_refresh_api_grile_stores__site_code__refresh_post': {
    '200': Record<string, unknown>;
    '422': RetailHTTPValidationError;
  }

  'get_asm_perf_api_hr_asm_performance_get': {
    '200': unknown;
    '422': RetailHTTPValidationError;
  }

  'get_asm_perf_history_api_hr_asm_performance__asm_name__history_get': {
    '200': unknown;
    '422': RetailHTTPValidationError;
  }

  'get_asm_salary_api_hr_asm_salary__asm_name__get': {
    '200': unknown;
    '422': RetailHTTPValidationError;
  }

  'get_leave_requests_api_hr_leave_requests_get': {
    '200': RetailLeaveRequestListResponse;
    '422': RetailHTTPValidationError;
  }

  'post_leave_request_api_hr_leave_requests_post': {
    '200': unknown;
    '422': RetailHTTPValidationError;
  }

  'patch_leave_request_api_hr_leave_requests__request_id__patch': {
    '200': unknown;
    '422': RetailHTTPValidationError;
  }

  'get_manager_overview_api_hr_manager_overview_get': {
    '200': unknown;
    '422': RetailHTTPValidationError;
  }

  'get_performance_api_hr_performance__agent_name__get': {
    '200': unknown;
    '422': RetailHTTPValidationError;
  }

  'reconcile_erp_report_file_api_import_erp_reconciliation_post': {
    '200': RetailErpReconciliationResponse;
    '422': RetailHTTPValidationError;
  }

  'get_import_history_api_import_history_get': {
    '200': Array<RetailImportHistoryEntry>;
  }

  'get_import_job_status_api_import_jobs__job_id__get': {
    '200': RetailImportJobStatus;
    '422': RetailHTTPValidationError;
  }

  'upload_promo_actuals_file_api_import_promo_actuals_post': {
    '200': RetailPromoActualImportResponse;
    '422': RetailHTTPValidationError;
  }

  'upload_sales_file_api_import_sales_post': {
    '200': RetailImportJobStatus;
    '422': RetailHTTPValidationError;
  }

  'promote_sales_generation_api_import_sales__snapshot_id__promote_post': {
    '200': RetailImportJobStatus;
    '422': RetailHTTPValidationError;
  }

  'annual_api_store_pnl_annual_get': {
    '200': unknown;
    '422': RetailHTTPValidationError;
  }

  'months_api_store_pnl_months_get': {
    '200': unknown;
  }

  'overview_api_store_pnl_overview_get': {
    '200': unknown;
    '422': RetailHTTPValidationError;
  }

  'pnl_permissions_api_store_pnl_permissions_get': {
    '200': Record<string, boolean>;
  }

  'regions_api_store_pnl_regions_get': {
    '200': unknown;
    '422': RetailHTTPValidationError;
  }

  'stores_api_store_pnl_stores_get': {
    '200': unknown;
    '422': RetailHTTPValidationError;
  }

  'list_stores_api_stores_get': {
    '200': Array<RetailStoreOption>;
  }

  'save_targets_api_stores_targets_post': {
    '200': Record<string, number>;
    '422': RetailHTTPValidationError;
  }

  'change_store_activity_api_stores__site_code__activity_post': {
    '200': RetailStoreActivityChangeResponse;
    '422': RetailHTTPValidationError;
  }

  'get_context_api_target_calculator_context_get': {
    '200': unknown;
  }

  'list_scenarios_api_target_calculator_scenarios_get': {
    '200': unknown;
  }

  'calculate_scenario_api_target_calculator_scenarios_calculate_post': {
    '200': unknown;
    '422': RetailHTTPValidationError;
  }

  'get_scenario_api_target_calculator_scenarios__scenario_id__get': {
    '200': unknown;
    '422': RetailHTTPValidationError;
  }

  'export_scenario_api_target_calculator_scenarios__scenario_id__export_get': {
    '200': unknown;
    '422': RetailHTTPValidationError;
  }

  'finalize_scenario_api_target_calculator_scenarios__scenario_id__finalize_post': {
    '200': unknown;
    '422': RetailHTTPValidationError;
  }

  'update_final_targets_api_target_calculator_scenarios__scenario_id__rows_patch': {
    '200': unknown;
    '422': RetailHTTPValidationError;
  }

  'get_store_detail_api_target_calculator_scenarios__scenario_id__stores__site_code__get': {
    '200': unknown;
    '422': RetailHTTPValidationError;
  }

  'get_tasks_api_tasks_get': {
    '200': RetailTaskListResponse;
    '422': RetailHTTPValidationError;
  }

  'post_task_api_tasks_post': {
    '200': unknown;
    '422': RetailHTTPValidationError;
  }

  'remove_task_api_tasks__task_id__delete': {
    '200': unknown;
    '422': RetailHTTPValidationError;
  }

  'patch_task_api_tasks__task_id__patch': {
    '200': unknown;
    '422': RetailHTTPValidationError;
  }

  'get_visits_report_api_visits_report_get': {
    '200': RetailVisitReportResponse;
    '422': RetailHTTPValidationError;
  }

  'get_visit_photo_api_visits_report_photo__visit_id___filename__get': {
    '200': unknown;
    '422': RetailHTTPValidationError;
  }

  'get_visits_tree_api_visits_report_tree_get': {
    '200': RetailVisitTreeResponse;
    '422': RetailHTTPValidationError;
  }

  'get_visit_detail_api_visits_report_visit__visit_id__get': {
    '200': RetailVisitDetail;
    '422': RetailHTTPValidationError;
  }

  'session_status_auth_session_get': {
    '200': unknown;
  }

  'session_login_auth_session_login_get': {
    '200': unknown;
  }

  'session_logout_auth_session_logout_post': {
    '200': unknown;
  }

  'metrics_metrics_get': {
    '200': unknown;
  }

  'agent_history_by_retail_code_salarii_agents_history_by_retail_code_get': {
    '200': RetailSalaryHistoryResponse;
    '422': RetailHTTPValidationError;
  }

  'agents_summary_salarii_agents_summary_get': {
    '200': RetailSalaryAgentsSummaryResponse;
    '422': RetailHTTPValidationError;
  }

  'agent_history_salarii_agents__person_id__history_get': {
    '200': RetailSalaryHistoryResponse;
    '422': RetailHTTPValidationError;
  }

  'audit_salary_export_salarii_audit_export_post': {
    '204': void;
    '422': RetailHTTPValidationError;
  }

  'salarii_evolution_salarii_evolution_get': {
    '200': unknown;
    '422': RetailHTTPValidationError;
  }

  'salarii_overview_salarii_overview_get': {
    '200': unknown;
    '422': RetailHTTPValidationError;
  }

  'list_records_salarii_records_get': {
    '200': Array<RetailSalaryRecordPublic>;
    '422': RetailHTTPValidationError;
  }

  'salarii_stores_salarii_stores_get': {
    '200': unknown;
    '422': RetailHTTPValidationError;
  }

  'salarii_summary_salarii_summary_get': {
    '200': unknown;
    '422': RetailHTTPValidationError;
  }

  'salarii_trend_salarii_trend_get': {
    '200': unknown;
    '422': RetailHTTPValidationError;
  }

}
