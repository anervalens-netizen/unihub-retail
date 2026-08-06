/* GENERATED FILE. Run npm run contracts:generate; do not edit manually. */
export const RETAIL_OPENAPI_SHA256 = 'f97f73f17a1d18c7c0403e068947dfa9b86251b63b72d4098ef01afe019ff262' as const; // pragma: allowlist secret

export type RetailDecimal = string & { readonly __retailDecimal: unique symbol };

export const RETAIL_DECIMAL_KEYS = new Set<string>([
  "accessory_margin_pct",
  "actual_realized",
  "actual_sales",
  "attainment_pct",
  "avg_monthly_sales",
  "avg_receipt",
  "avg_receipt_value",
  "avg_sales_16m",
  "avg_seniority_months",
  "base_salary_per_agent",
  "base_value",
  "best_month_sales",
  "blended_factor",
  "bon2acc_pct",
  "bon2acc_points",
  "bonuri_pct",
  "bonuri_score",
  "break_even_gross_sales",
  "break_even_total",
  "calculated_weight",
  "cap_target",
  "career_total_sales",
  "cumulative_actual",
  "cumulative_forecast",
  "current_forecast",
  "current_forecast_total",
  "daily_average",
  "daily_reference",
  "daily_score",
  "daily_vs_reference_pct",
  "default_min_floor",
  "default_previous_month_cap_pct",
  "default_previous_month_floor_pct",
  "delta_pct",
  "delta_sales",
  "difference",
  "expected_sales_to_date",
  "final_growth_vs_current_pct",
  "final_target",
  "final_total",
  "floor_target",
  "floor_total",
  "focus_pct",
  "focus_points",
  "focus_score",
  "focus_share_pct",
  "forecast_factor",
  "forecast_sales",
  "forecast_target_pct",
  "forecast_target_progress_pct",
  "forecast_total",
  "incentive_potential",
  "incentive_sales",
  "incentive_value",
  "last_year_base_total",
  "last_year_growth_pct",
  "last_year_store_factor",
  "last_year_target_total",
  "max",
  "medie_produs",
  "medie_zilnica",
  "min",
  "min_floor",
  "multiyear_store_factor",
  "network_factor",
  "normalized_weight",
  "operating_costs",
  "operating_costs_total",
  "peer_daily_average",
  "prc_focus_acc_qty",
  "premium_glass_pct",
  "premium_glass_score",
  "premium_qty_share_pct",
  "premium_sales",
  "premium_sales_share_pct",
  "previous_month_cap_pct",
  "previous_month_floor_pct",
  "proc_bon2acc",
  "proc_realizare_target",
  "promo_discount_value",
  "promo_impact",
  "promo_sales",
  "proposed_growth_vs_current_pct",
  "proposed_target",
  "proposed_total",
  "ratio",
  "raw_adjustment",
  "raw_estimate",
  "realized",
  "regular_sales",
  "remaining_difference",
  "report_value",
  "retail_value",
  "retention_rate",
  "salary_cost_at_90_pct",
  "salary_total",
  "sales",
  "sales_16m",
  "sales_share_pct",
  "sales_total",
  "share_pct",
  "stability_rate",
  "store_factor",
  "store_target",
  "suggested_total_target",
  "target",
  "target_forecast_pct",
  "target_pct",
  "target_points",
  "target_progress_pct",
  "target_score",
  "target_value",
  "total_focus_sales",
  "total_sales",
  "total_score",
  "total_target",
  "total_vanzari",
  "trend_daily_pct",
  "used_adjustment",
  "used_factor",
  "value",
  "value_reper",
  "value_reper_score",
  "weight",
  "zone_factor",
]);

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
  "bonuri_pct": RetailDecimal | null;
  "bonuri_points": number;
  "daily_average": RetailDecimal | null;
  "daily_points": number;
  "firma": string;
  "focus_pct": RetailDecimal | null;
  "focus_points": number;
  "focus_quantity": number;
  "glass_qty": number;
  "has_red_segment": boolean;
  "locatie": string;
  "month": string;
  "peer_daily_average": RetailDecimal | null;
  "premium_glass_pct": RetailDecimal | null;
  "premium_glass_points": number;
  "premium_glass_qty": number;
  "qualifier": "Excelent" | "Foarte Bun" | "Bun" | "Mediu" | "Scazut";
  "receipt_2plus_count": number;
  "receipt_count": number;
  "regional": string;
  "site_code": string;
  "store_target": RetailDecimal;
  "store_working_days": number;
  "target_pct": RetailDecimal | null;
  "target_points": number;
  "target_value": RetailDecimal;
  "total_points": number;
  "total_quantity": number;
  "total_sales": RetailDecimal;
  "value_reper": RetailDecimal | null;
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
  "bonuri_pct": RetailDecimal | null;
  "bonuri_score": RetailDecimal | null;
  "confidence_flags": Array<string>;
  "daily_average": RetailDecimal | null;
  "daily_reference": RetailDecimal | null;
  "daily_reference_type": "colegi" | "istoric_locatie" | "media_manager" | "none";
  "daily_score": RetailDecimal | null;
  "daily_vs_reference_pct": RetailDecimal | null;
  "eligibility_status": "eligibil" | "insuficient";
  "final_month_count": number;
  "firma": string;
  "focus_pct": RetailDecimal | null;
  "focus_quantity": number;
  "focus_score": RetailDecimal | null;
  "forecast_factor": RetailDecimal;
  "forecast_sales": RetailDecimal;
  "glass_qty": number;
  "is_partial": boolean;
  "locatie": string;
  "max_score"?: number;
  "month": string;
  "partial_month_count": number;
  "period_month_count": number;
  "premium_glass_pct": RetailDecimal | null;
  "premium_glass_qty": number;
  "premium_glass_score": RetailDecimal | null;
  "rating": "Insuficient" | "Fara scor" | "Excelent" | "Foarte Bun" | "Bun" | "Risc" | "Critic";
  "receipt_2plus_count": number;
  "receipt_count": number;
  "regional": string;
  "site_code": string;
  "target_forecast_pct": RetailDecimal | null;
  "target_pct": RetailDecimal | null;
  "target_score": RetailDecimal | null;
  "target_source": "partial_agent_target" | "allocated_store_target";
  "target_value": RetailDecimal;
  "total_quantity": number;
  "total_sales": RetailDecimal;
  "total_score": RetailDecimal | null;
  "trend_daily_pct": RetailDecimal | null;
  "trend_direction": "up" | "down" | "flat";
  "value_reper": RetailDecimal | null;
  "value_reper_score": RetailDecimal | null;
  "working_days": number;
}

export interface RetailAgentHistoryPoint {
  "active_store_count": number;
  "is_active": boolean;
  "month": string;
  "receipt_count": number;
  "total_quantity": number;
  "total_sales": RetailDecimal;
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
  "total_sales": RetailDecimal;
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
  "avg_monthly_sales": RetailDecimal;
  "best_month": string | null;
  "best_month_sales": RetailDecimal;
  "career_total_quantity": number;
  "career_total_sales": RetailDecimal;
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
  "medie_produs"?: RetailDecimal | null;
  "medie_zilnica": RetailDecimal | null;
  "nr_bon2acc": number;
  "nr_bonuri": number;
  "prc_focus_acc_qty": RetailDecimal | null;
  "proc_bon2acc": RetailDecimal | null;
  "proc_realizare_target"?: RetailDecimal | null;
  "promo_discount_value"?: RetailDecimal;
  "promo_qty"?: number;
  "regional": string;
  "return_receipt_count"?: number;
  "site_code": string;
  "target"?: RetailDecimal | null;
  "total_vanzari": RetailDecimal;
  "zile_lucrate": number;
}

export interface RetailAgentTargetRunRequest {
  "month": string;
}

export interface RetailAgentsOverviewResponse {
  "active_count": number;
  "avg_seniority_months": RetailDecimal | null;
  "churned_total_count": number;
  "left_this_month_count": number;
  "new_count": number;
  "reactivated_count": number;
  "retention_rate": RetailDecimal | null;
  "stability_rate": RetailDecimal | null;
  "total_unique_agents": number;
}

export interface RetailAiForecastDailyPoint {
  "actual_sales": RetailDecimal;
  "cumulative_actual": RetailDecimal;
  "cumulative_forecast": RetailDecimal;
  "forecast_date": string;
  "forecast_sales": RetailDecimal;
}

export interface RetailAiForecastManagerRow {
  "actual_sales": RetailDecimal;
  "delta_pct"?: RetailDecimal | null;
  "delta_sales": RetailDecimal;
  "expected_sales_to_date": RetailDecimal;
  "forecast_sales": RetailDecimal;
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
  "actual_sales"?: RetailDecimal | null;
  "delta_pct"?: RetailDecimal | null;
  "delta_sales"?: RetailDecimal | null;
  "forecast_sales": RetailDecimal;
  "manager": string;
  "store_count": number;
}

export interface RetailAiForecastRollingMonthlyPoint {
  "actual_sales"?: RetailDecimal | null;
  "delta_pct"?: RetailDecimal | null;
  "delta_sales"?: RetailDecimal | null;
  "forecast_month": string;
  "forecast_sales": RetailDecimal;
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
  "actual_sales"?: RetailDecimal | null;
  "asm": string;
  "delta_pct"?: RetailDecimal | null;
  "delta_sales"?: RetailDecimal | null;
  "firma": string;
  "forecast_sales": RetailDecimal;
  "locatie": string;
  "regional": string;
  "site_code": string;
}

export interface RetailAiForecastRollingSummary {
  "actual_sales"?: RetailDecimal | null;
  "delta_pct"?: RetailDecimal | null;
  "delta_sales"?: RetailDecimal | null;
  "end_month": string;
  "forecast_sales": RetailDecimal;
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
  "actual_sales": RetailDecimal;
  "asm": string;
  "delta_pct"?: RetailDecimal | null;
  "delta_sales": RetailDecimal;
  "expected_sales_to_date": RetailDecimal;
  "firma": string;
  "forecast_sales": RetailDecimal;
  "locatie": string;
  "regional": string;
  "site_code": string;
}

export interface RetailAiForecastSummary {
  "actual_last_date"?: string | null;
  "actual_sales": RetailDecimal;
  "days_elapsed"?: number;
  "days_in_month": number;
  "delta_pct"?: RetailDecimal | null;
  "delta_sales": RetailDecimal;
  "expected_sales_to_date": RetailDecimal;
  "forecast_month": string;
  "forecast_sales": RetailDecimal;
  "source_month": string;
  "store_count": number;
}

export interface RetailAsmStats {
  "asm": string;
  "incentive_qty"?: number;
  "medie_produs"?: RetailDecimal | null;
  "medie_zilnica": RetailDecimal | null;
  "nr_agenti": number;
  "nr_bonuri": number;
  "prc_focus_acc_qty": RetailDecimal | null;
  "proc_bon2acc": RetailDecimal | null;
  "proc_realizare_target": RetailDecimal | null;
  "promo_discount_value"?: RetailDecimal;
  "promo_qty"?: number;
  "qty_total": number;
  "regional": string;
  "target": RetailDecimal;
  "total_vanzari": RetailDecimal;
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
  "sales_total": RetailDecimal;
  "share_pct": RetailDecimal | null;
}

export interface RetailCampaignOverview {
  "active_focus_products": number;
  "active_focus_stores": number;
  "focus_share_pct": RetailDecimal | null;
  "month": string;
  "total_focus_qty": number;
  "total_focus_sales": RetailDecimal;
}

export interface RetailCampaignProductStat {
  "item_code": string;
  "item_name": string;
  "qty_total": number;
  "sales_total": RetailDecimal;
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
  "sales_total": RetailDecimal;
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
  "promo_discount_value"?: RetailDecimal;
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
  "sales_total": RetailDecimal;
  "share_pct": RetailDecimal | null;
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

export interface RetailCrmAlertResponse {
  "asm"?: string | null;
  "locatie"?: string | null;
  "reasons"?: Array<string>;
  "regional"?: string | null;
  "score": number;
  "site_code": string;
}

export interface RetailCrmBreakdownResponse {
  "kpi_pct"?: number | null;
  "target_pct"?: number | null;
  "trend_pct"?: number | null;
  "visits_pct"?: number | null;
}

export interface RetailCrmRecalculateResponse {
  "month": string;
  "recalculated": number;
}

export interface RetailCrmScoreResponse {
  "breakdown": RetailCrmBreakdownResponse;
  "score": number;
  "site_code": string;
}

export interface RetailDailySalesPoint {
  "receipt_count": number;
  "sale_date": string;
  "total_quantity": number;
  "total_sales": RetailDecimal;
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
  "daily_average": RetailDecimal | null;
  "days_in_month"?: number | null;
  "forecast_sales"?: RetailDecimal | null;
  "forecast_target_progress_pct"?: RetailDecimal | null;
  "imported_day_of_month"?: number | null;
  "is_month_final"?: boolean;
  "last_sale_date"?: string | null;
  "medie_produs"?: RetailDecimal | null;
  "month": string;
  "prc_focus_acc_qty": RetailDecimal | null;
  "proc_bon2acc": RetailDecimal | null;
  "target_progress_pct": RetailDecimal | null;
  "total_agents": number;
  "total_quantity": number;
  "total_receipts": number;
  "total_sales": RetailDecimal;
  "total_stores": number;
  "total_target": RetailDecimal;
  "working_days": number;
}

export interface RetailErpReconciliationAppMetric {
  "key": string;
  "label": string;
  "note": string;
  "unit": "RON" | "buc";
  "value"?: RetailDecimal | null;
}

export interface RetailErpReconciliationIssue {
  "difference"?: RetailDecimal | null;
  "entity": string;
  "metric": string;
  "note": string;
  "report_value"?: RetailDecimal | null;
  "retail_value"?: RetailDecimal | null;
  "scope": "report" | "store" | "agent";
  "severity": "warning" | "error";
  "site_code"?: string | null;
}

export interface RetailErpReconciliationMetric {
  "difference"?: RetailDecimal | null;
  "key": string;
  "label": string;
  "note"?: string | null;
  "report_value"?: RetailDecimal | null;
  "retail_value"?: RetailDecimal | null;
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

export interface RetailExportCatalogResponse {
  "comparison_levels": Array<RetailExportComparisonLevel>;
  "daily_metrics": Array<RetailExportColumnDef>;
  "datasets": Array<RetailExportDataset>;
  "metrics": Array<RetailExportColumnDef>;
  "monthly_metrics": Array<RetailExportColumnDef>;
}

export interface RetailExportColumnDef {
  "group": string;
  "key": string;
  "label": string;
  "type": string;
}

export interface RetailExportComparisonLevel {
  "key": string;
  "label": string;
}

export interface RetailExportDataset {
  "description": string;
  "dimensions": Array<RetailExportColumnDef>;
  "key": string;
  "label": string;
}

export interface RetailExportFilters {
  "agent"?: Array<string>;
  "asm"?: Array<string>;
  "firma"?: Array<string>;
  "regional"?: Array<string>;
  "site_code"?: Array<string>;
}

export interface RetailExportPreviewResponse {
  "columns": Array<RetailExportColumnDef>;
  "rows": Array<Record<string, unknown>>;
  "total_rows": number;
  "truncated": boolean;
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
  "focus_share_pct": RetailDecimal | null;
  "month": string;
  "total_focus_qty": number;
  "total_focus_sales": RetailDecimal;
}

export interface RetailFocusHistoryResponse {
  "history": Array<RetailFocusHistoryPoint>;
}

export interface RetailHTTPValidationError {
  "detail"?: Array<RetailValidationError>;
}

export interface RetailHrAgentPerformanceItem {
  "active_days": number;
  "import_month": string;
  "target_pct": number;
  "total_value": number;
  "transaction_count": number;
}

export interface RetailHrAsmHistoryItem {
  "active_stores": number;
  "avg_completion"?: number | null;
  "avg_duration"?: number | null;
  "forecast_sales": number;
  "forecast_target_pct"?: number | null;
  "is_forecast": boolean;
  "month": string;
  "target_pct"?: number | null;
  "total_sales": number;
  "total_target": number;
  "total_visits": number;
}

export interface RetailHrAsmPerformanceItem {
  "active_agents": number;
  "active_stores": number;
  "approved_pct"?: number | null;
  "asm": string;
  "avg_completion"?: number | null;
  "avg_duration"?: number | null;
  "checklist_score"?: number | null;
  "distinct_stores_visited": number;
  "forecast_sales": number;
  "forecast_target_pct"?: number | null;
  "is_forecast": boolean;
  "pct_bon2acc": number;
  "pct_focus": number;
  "regional"?: string | null;
  "target_pct"?: number | null;
  "total_sales": number;
  "total_target": number;
  "total_visits": number;
}

export interface RetailHrAsmSalaryAccFocus {
  "commission": number;
  "pct"?: number | null;
}

export interface RetailHrAsmSalaryBreakdown {
  "acc_focus": RetailHrAsmSalaryAccFocus;
  "asm": string;
  "fixed_salary": number;
  "forecast_factor": number;
  "homogeneity": RetailHrAsmSalaryHomogeneity;
  "is_forecast": boolean;
  "islands"?: Array<RetailHrAsmSalaryIsland>;
  "islands_commission": number;
  "month": string;
  "total_salary": number;
  "zone": RetailHrAsmSalaryZone;
}

export interface RetailHrAsmSalaryHomogeneity {
  "commission": number;
  "eligible": boolean;
  "islands_count": number;
  "min_pct": number;
  "qualifying_count": number;
  "qualifying_pct": number;
}

export interface RetailHrAsmSalaryIsland {
  "commission": number;
  "firma": string;
  "forecast_sales": number;
  "forecast_target_pct"?: number | null;
  "locatie": string;
  "pct_used"?: number | null;
  "site_code": string;
  "target_pct"?: number | null;
  "total_sales": number;
  "total_target": number;
}

export interface RetailHrAsmSalaryZone {
  "commission": number;
  "forecast_sales": number;
  "forecast_target_pct"?: number | null;
  "pct_used"?: number | null;
  "target_pct"?: number | null;
  "total_sales": number;
  "total_target": number;
}

export interface RetailHrManagerOverviewItem {
  "active_agents": number;
  "active_stores": number;
  "agent_delta": number;
  "agents_added": number;
  "agents_left": number;
  "agents_per_store": number;
  "approved_pct"?: number | null;
  "avg_visit_completion"?: number | null;
  "checklist_score"?: number | null;
  "manager": string;
  "month": string;
  "previous_active_agents": number;
  "regional"?: string | null;
  "reporting_available": boolean;
  "stores"?: Array<RetailHrManagerStoreItem>;
  "stores_without_agents": number;
  "total_visits": number;
  "visit_coverage_pct"?: number | null;
  "visited_stores": number;
  "visits_available": boolean;
}

export interface RetailHrManagerStoreItem {
  "active_agents": number;
  "agent_delta": number;
  "firma": string;
  "locatie": string;
  "previous_active_agents": number;
  "site_code": string;
}

export interface RetailImportCoverageReport {
  "active_store_count_before"?: number | null;
  "active_store_coverage_pct"?: number | null;
  "company_count"?: number | null;
  "incoming_store_count"?: number | null;
  "metadata_change_count"?: number | null;
  "missing_active_store_count"?: number | null;
  "missing_prior_store_count"?: number | null;
  "new_store_count"?: number | null;
  "prior_snapshot_coverage_pct"?: number | null;
  "prior_snapshot_store_count"?: number | null;
  "store_activity_writes"?: number | null;
}

export interface RetailImportHistoryEntry {
  "coverage_report"?: RetailImportCoverageReport;
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
  "coverage_report"?: RetailImportCoverageReport;
  "filename": string;
  "generation_state"?: "validated" | "promoted";
  "generation_token"?: string | null;
  "import_month": string;
  "is_month_final": boolean;
  "manifest"?: RetailSalesGenerationManifest | null;
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
  "daily_average": RetailDecimal | null;
  "medie_produs"?: RetailDecimal | null;
  "month": string;
  "prc_focus_acc_qty": RetailDecimal | null;
  "proc_bon2acc": RetailDecimal | null;
  "return_receipt_count"?: number;
  "target_progress_pct": RetailDecimal | null;
  "total_agents": number;
  "total_quantity": number;
  "total_receipts": number;
  "total_sales": RetailDecimal;
  "total_stores": number;
  "total_target": RetailDecimal;
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
  "forecast_target_pct"?: RetailDecimal | null;
  "is_selected"?: boolean;
  "label": string;
  "prc_focus_acc_qty"?: RetailDecimal | null;
  "proc_bon2acc"?: RetailDecimal | null;
  "rank": number;
  "sublabel"?: string | null;
  "target_progress_pct"?: RetailDecimal | null;
  "total_sales": RetailDecimal;
}

export interface RetailPerformanceScoreBreakdown {
  "bon2acc_points": RetailDecimal;
  "focus_points": RetailDecimal;
  "target_points": RetailDecimal;
}

export interface RetailPeriodComparisonPayload {
  "current": RetailPeriodComparisonPoint;
  "previous": RetailPeriodComparisonPoint;
  "year_over_year": RetailPeriodComparisonPoint;
}

export interface RetailPeriodComparisonPoint {
  "avg_receipt_value": RetailDecimal | null;
  "cartele_qty"?: number;
  "daily_average": RetailDecimal | null;
  "day_range": string;
  "label": string;
  "medie_produs"?: RetailDecimal | null;
  "month": string;
  "prc_focus_acc_qty": RetailDecimal | null;
  "proc_bon2acc": RetailDecimal | null;
  "total_quantity": number;
  "total_receipts": number;
  "total_sales": RetailDecimal;
  "working_days": number;
}

export interface RetailPnlAnnualItemResponse {
  "cogs": number;
  "depreciation": number;
  "ebit": number;
  "ebitda": number;
  "gross_margin": number;
  "is_estimated": boolean;
  "month_count": number;
  "operating_costs": number;
  "revenue": number;
  "store_count": number;
  "year": string;
}

export interface RetailPnlAnnualResponse {
  "annual": Array<RetailPnlAnnualItemResponse>;
}

export interface RetailPnlMetricsResponse {
  "cogs": number;
  "depreciation": number;
  "ebit": number;
  "ebitda": number;
  "gross_margin": number;
  "operating_costs": number;
  "revenue": number;
}

export interface RetailPnlMonthResponse {
  "has_actual": boolean;
  "has_estimated": boolean;
  "month": string;
}

export interface RetailPnlMonthlyItemResponse {
  "cogs": number;
  "depreciation": number;
  "ebit": number;
  "ebitda": number;
  "gross_margin": number;
  "is_estimated": boolean;
  "month": string;
  "operating_costs": number;
  "revenue": number;
}

export interface RetailPnlMonthsResponse {
  "months": Array<RetailPnlMonthResponse>;
}

export interface RetailPnlOverviewResponse {
  "categories"?: Record<string, number>;
  "company"?: string | null;
  "end_month": string;
  "monthly"?: Array<RetailPnlMonthlyItemResponse>;
  "reconciliation"?: Array<RetailPnlReconciliationResponse>;
  "regional"?: string | null;
  "site_code"?: string | null;
  "site_company"?: string | null;
  "start_month": string;
  "stores"?: Array<RetailPnlStoreResponse>;
  "summary": RetailPnlMetricsResponse;
}

export interface RetailPnlPermissionsResponse {
  "can_view": boolean;
}

export interface RetailPnlReconciliationResponse {
  "difference_to_net": number;
  "month": string;
  "pnl_revenue": number;
  "pnl_to_net_sales_pct"?: number | null;
  "retail_sales_gross": number;
  "retail_sales_net": number;
}

export interface RetailPnlRegionsResponse {
  "regions": Array<string>;
}

export interface RetailPnlStoreOptionResponse {
  "company_name": string;
  "location": string;
  "regional"?: string | null;
  "scope_company"?: string | null;
  "site_code": string;
}

export interface RetailPnlStoreResponse {
  "cogs": number;
  "company": string;
  "depreciation": number;
  "ebit": number;
  "ebitda": number;
  "gross_margin": number;
  "has_estimates": boolean;
  "location": string;
  "operating_costs": number;
  "regional"?: string | null;
  "revenue": number;
  "site_code": string;
  "source_site_code": string;
}

export interface RetailPnlStoresResponse {
  "stores": Array<RetailPnlStoreOptionResponse>;
}

export interface RetailPremiumGlassAgentStat {
  "agent": string;
  "firma": string;
  "locatie": string;
  "premium_qty"?: number;
  "premium_qty_share_pct"?: RetailDecimal | null;
  "premium_sales"?: RetailDecimal;
  "regular_qty"?: number;
  "regular_sales"?: RetailDecimal;
  "site_code": string;
  "total_qty"?: number;
  "total_sales"?: RetailDecimal;
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
  "premium_qty_share_pct"?: RetailDecimal | null;
  "premium_sales"?: RetailDecimal;
  "regular_qty"?: number;
  "regular_sales"?: RetailDecimal;
  "store_count"?: number;
  "total_qty"?: number;
  "total_sales"?: RetailDecimal;
}

export interface RetailPremiumGlassModelStat {
  "model_key": string;
  "model_label": string;
  "premium_item_count"?: number;
  "premium_qty"?: number;
  "premium_qty_share_pct"?: RetailDecimal | null;
  "premium_sales"?: RetailDecimal;
  "regular_item_count"?: number;
  "regular_qty"?: number;
  "regular_sales"?: RetailDecimal;
  "total_qty"?: number;
  "total_sales"?: RetailDecimal;
}

export interface RetailPremiumGlassProductStat {
  "is_premium": boolean;
  "item_code": string;
  "item_name": string;
  "model_labels"?: Array<string>;
  "qty"?: number;
  "sales"?: RetailDecimal;
  "store_count"?: number;
}

export interface RetailPremiumGlassStoreStat {
  "firma": string;
  "locatie": string;
  "premium_qty"?: number;
  "premium_qty_share_pct"?: RetailDecimal | null;
  "premium_sales"?: RetailDecimal;
  "regular_qty"?: number;
  "regular_sales"?: RetailDecimal;
  "site_code": string;
  "total_qty"?: number;
  "total_sales"?: RetailDecimal;
}

export interface RetailPremiumGlassSummary {
  "active_agents"?: number;
  "active_stores"?: number;
  "month": string;
  "premium_active_agents"?: number;
  "premium_active_stores"?: number;
  "premium_qty"?: number;
  "premium_qty_share_pct"?: RetailDecimal | null;
  "premium_sales"?: RetailDecimal;
  "premium_sales_share_pct"?: RetailDecimal | null;
  "regular_qty"?: number;
  "regular_sales"?: RetailDecimal;
  "target_model_count"?: number;
  "total_qty"?: number;
  "total_sales"?: RetailDecimal;
}

export interface RetailPremiumGlassSurfaceStat {
  "premium_qty"?: number;
  "premium_qty_share_pct"?: RetailDecimal | null;
  "premium_sales"?: RetailDecimal;
  "regular_qty"?: number;
  "regular_sales"?: RetailDecimal;
  "surface_key": "screen" | "camera";
  "surface_label": string;
  "total_qty"?: number;
  "total_sales"?: RetailDecimal;
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
  "incentive_potential"?: RetailDecimal | null;
  "incentive_qty"?: number | null;
  "incentive_qualified_agents"?: number;
  "incentive_qualified_agents_full"?: number;
  "incentive_qualified_agents_half"?: number;
  "incentive_qualified_qty"?: number | null;
  "incentive_qualified_stores"?: number;
  "incentive_qualified_stores_full"?: number;
  "incentive_qualified_stores_half"?: number;
  "incentive_sales"?: RetailDecimal;
  "incentive_sold_qty"?: number;
  "incentive_value"?: RetailDecimal | null;
  "promo_impact"?: RetailDecimal;
  "promo_qty"?: number;
  "promo_sales"?: RetailDecimal;
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
  "share_pct": RetailDecimal | null;
}

export interface RetailRegionalStats {
  "forecast_target_pct"?: RetailDecimal | null;
  "incentive_qty"?: number;
  "medie_produs"?: RetailDecimal | null;
  "medie_zilnica": RetailDecimal | null;
  "nr_agenti": number;
  "nr_bonuri": number;
  "prc_focus_acc_qty": RetailDecimal | null;
  "proc_bon2acc": RetailDecimal | null;
  "proc_realizare_target": RetailDecimal | null;
  "promo_discount_value"?: RetailDecimal;
  "promo_qty"?: number;
  "qty_total": number;
  "regional": string;
  "return_receipt_count"?: number;
  "target": RetailDecimal;
  "total_vanzari": RetailDecimal;
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

export interface RetailSalaryCompanyTotal {
  "company"?: string | null;
  "name"?: string | null;
  "total": number;
}

export interface RetailSalaryComparisonItem {
  "agent_count": number;
  "avg_agent_count": number;
  "avg_salary": number;
  "company_name": string;
  "locatie"?: string | null;
  "ratio": number;
  "site_code": string;
  "total_salary": number;
  "total_sales": number;
}

export interface RetailSalaryEvolutionPoint {
  "mobicell": number;
  "mobiup": number;
  "month": string;
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

export interface RetailSalaryOverviewResponse {
  "agent_count"?: number | null;
  "agent_month_count"?: number | null;
  "avg_agent_month_count"?: number | null;
  "avg_salary"?: number | null;
  "by_company"?: Array<RetailSalaryCompanyTotal>;
  "months_span"?: [number, number, number, number] | null;
  "record_count"?: number | null;
  "total"?: number | null;
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

export interface RetailSalaryStoreOption {
  "locatie"?: string | null;
  "site_code": string;
}

export interface RetailSalarySummaryResponse {
  "items"?: Array<RetailSalaryComparisonItem>;
  "month"?: string | null;
}

export interface RetailSalaryTrendPoint {
  "agent_count": number;
  "avg_agent_count": number;
  "avg_salary": number;
  "by_company"?: Record<string, unknown>;
  "month": string;
  "total_salary": number;
  "total_sales": number;
}

export interface RetailSalesGenerationAnomaly {
  "blocking": boolean;
  "code": string;
  "count"?: number | null;
  "message": string;
}

export interface RetailSalesGenerationManifest {
  "anomalies"?: Array<RetailSalesGenerationAnomaly>;
  "business_sha256"?: string | null;
  "cutoff_date"?: string | null;
  "generation_state"?: "validated" | "promoted" | null;
  "receipt_count"?: number | null;
  "site_day_count"?: number | null;
  "total_quantity"?: number | null;
  "total_value"?: string | null;
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
  "forecast_target_pct"?: RetailDecimal | null;
  "import_month": string;
  "incentive_qty"?: number;
  "locatie": string;
  "medie_produs"?: RetailDecimal | null;
  "nr_agenti": number;
  "nr_bonuri": number;
  "prc_focus_acc_qty"?: RetailDecimal | null;
  "proc_bon2acc"?: RetailDecimal | null;
  "proc_realizare_target": RetailDecimal | null;
  "promo_discount_value"?: RetailDecimal;
  "promo_qty"?: number;
  "qty_total": number | null;
  "regional": string;
  "return_receipt_count"?: number;
  "site_code": string;
  "target": RetailDecimal;
  "total_vanzari": RetailDecimal;
  "zile_active": number;
}

export interface RetailStoreTargetInput {
  "import_month": string;
  "site_code": string;
  "target_value": number | RetailDecimal;
}

export interface RetailTargetCalculationDetails {
  "allocation_reason"?: string | null;
  "cap_target"?: RetailDecimal | null;
  "current_forecast"?: RetailDecimal | null;
  "current_month"?: string | null;
  "flags"?: Array<string>;
  "floor_target"?: RetailDecimal | null;
  "is_cap_limited"?: boolean | null;
  "is_floor_limited"?: boolean | null;
  "method"?: string | null;
  "raw_estimate"?: RetailDecimal | null;
  "seasonality"?: RetailTargetSeasonalityDetails | null;
  "seasonality_years"?: number | null;
  "trend"?: RetailTargetTrendDetails | null;
}

export interface RetailTargetCalculationParams {
  "profitability"?: RetailTargetOpenModel | null;
  "profitability_summary"?: RetailTargetOpenModel | null;
  "seasonality_years"?: number | null;
}

export interface RetailTargetCalculationRequest {
  "cohort_month"?: string | null;
  "expected_revision"?: number | null;
  "min_floor"?: number | RetailDecimal;
  "previous_month_cap_pct"?: number | RetailDecimal;
  "previous_month_floor_pct"?: number | RetailDecimal;
  "seasonality_years"?: number;
  "target_month": string;
  "total_target": number | RetailDecimal;
}

export interface RetailTargetContextResponse {
  "active_store_count": number;
  "can_finalize": boolean;
  "default_min_floor": RetailDecimal;
  "default_previous_month_cap_pct": RetailDecimal;
  "default_previous_month_floor_pct": RetailDecimal;
  "default_seasonality_years": number;
  "latest_sales_month": string;
  "regionals": Array<string>;
  "suggested_cohort_month": string;
  "suggested_target_month": string;
  "suggested_total_target": RetailDecimal;
}

export interface RetailTargetFinalRow {
  "final_target"?: number | RetailDecimal | null;
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

export interface RetailTargetForecastRunResponse {
  "generated_at": string;
  "id": number;
  "model_mode": string;
  "model_name": string;
  "source_month"?: string | null;
  "variant": string;
}

export interface RetailTargetHistoryValue {
  "actual_realized"?: RetailDecimal | null;
  "attainment_pct"?: RetailDecimal | null;
  "forecast_factor"?: RetailDecimal;
  "is_forecast"?: boolean;
  "label": string;
  "month": string;
  "realized": RetailDecimal;
  "role": string;
  "target": RetailDecimal;
  "weight"?: RetailDecimal;
}

export type RetailTargetOpenModel = Record<string, unknown>;

export interface RetailTargetProfitabilityResponse {
  "accessory_margin_pct"?: RetailDecimal | null;
  "agent_count": number;
  "anomaly_flags"?: Array<string>;
  "base_salary_per_agent": RetailDecimal;
  "break_even_gross_sales"?: RetailDecimal | null;
  "forecast_sales"?: RetailDecimal | null;
  "operating_costs"?: RetailDecimal | null;
  "salary_cost_at_90_pct": RetailDecimal;
}

export interface RetailTargetProfitabilitySummaryResponse {
  "assumptions"?: RetailTargetOpenModel | null;
  "break_even_total"?: RetailDecimal | null;
  "forecast_below_break_even_count": number;
  "forecast_coverage"?: RetailTargetOpenModel | null;
  "forecast_run"?: RetailTargetForecastRunResponse | null;
  "forecast_store_count": number;
  "forecast_total"?: RetailDecimal | null;
  "operating_costs_total"?: RetailDecimal | null;
  "pnl_months"?: Array<string>;
  "pnl_store_count": number;
  "salary_total": RetailDecimal;
  "status": string;
  "target_below_break_even_count": number;
}

export interface RetailTargetRegionalSummaryResponse {
  "current_forecast_total"?: RetailDecimal;
  "current_month"?: string | null;
  "final_growth_vs_current_pct"?: RetailDecimal | null;
  "final_total": RetailDecimal;
  "floor_total": RetailDecimal;
  "last_year_base_month"?: string | null;
  "last_year_base_total"?: RetailDecimal;
  "last_year_growth_pct"?: RetailDecimal | null;
  "last_year_target_month"?: string | null;
  "last_year_target_total"?: RetailDecimal;
  "proposed_growth_vs_current_pct"?: RetailDecimal | null;
  "proposed_total": RetailDecimal;
  "regional": string;
  "store_count": number;
}

export interface RetailTargetScenarioResponse {
  "calculation_method": string;
  "calculation_params"?: RetailTargetCalculationParams;
  "cap_limited_count"?: number;
  "cohort_month": string;
  "created_at": string;
  "final_total"?: RetailDecimal;
  "finalized_at"?: string | null;
  "floor_limited_count": number;
  "id": number;
  "manager_overrides_count"?: number;
  "manual_adjustments_count": number;
  "min_floor": RetailDecimal;
  "pending_final_count": number;
  "previous_month_floor_pct": RetailDecimal;
  "profitability_summary"?: RetailTargetProfitabilitySummaryResponse | null;
  "proposed_total"?: RetailDecimal;
  "regional_summary"?: Array<RetailTargetRegionalSummaryResponse>;
  "remaining_difference": RetailDecimal;
  "revision": number;
  "rows": Array<RetailTargetScenarioRowResponse>;
  "source_months"?: Array<RetailTargetSourceMonth>;
  "source_summary"?: Array<RetailTargetSourceSummaryResponse>;
  "status": string;
  "store_count"?: number;
  "target_month": string;
  "total_target": RetailDecimal;
  "updated_at": string;
  "warnings"?: Array<string>;
}

export interface RetailTargetScenarioRowResponse {
  "asm": string;
  "calculated_weight": RetailDecimal;
  "calculation_details"?: RetailTargetCalculationDetails;
  "cap_target"?: RetailDecimal | null;
  "final_target"?: RetailDecimal | null;
  "firma": string;
  "floor_target": RetailDecimal;
  "history"?: Array<RetailTargetHistoryValue>;
  "is_cap_limited"?: boolean;
  "is_floor_limited"?: boolean;
  "locatie": string;
  "normalized_weight"?: RetailDecimal | null;
  "note"?: string | null;
  "profitability"?: RetailTargetProfitabilityResponse | null;
  "proposed_target": RetailDecimal;
  "regional": string;
  "site_code": string;
  "updated_at"?: string | null;
}

export interface RetailTargetScenarioSummaryResponse {
  "calculation_method": string;
  "calculation_params"?: RetailTargetCalculationParams;
  "cohort_month": string;
  "created_at": string;
  "final_total"?: RetailDecimal;
  "finalized_at"?: string | null;
  "id": number;
  "min_floor": RetailDecimal;
  "pending_final_count"?: number;
  "previous_month_floor_pct": RetailDecimal;
  "proposed_total"?: RetailDecimal;
  "revision": number;
  "source_months"?: Array<RetailTargetSourceMonth>;
  "status": string;
  "store_count"?: number;
  "target_month": string;
  "total_target": RetailDecimal;
  "updated_at": string;
  "warnings"?: Array<string>;
}

export interface RetailTargetSeasonalityDetails {
  "blended_factor"?: RetailDecimal | null;
  "last_year_store_factor"?: RetailDecimal | null;
  "max"?: RetailDecimal | null;
  "min"?: RetailDecimal | null;
  "multiyear_store_factor"?: RetailDecimal | null;
  "network_factor"?: RetailDecimal | null;
  "network_years"?: Array<RetailTargetSeasonalityYear>;
  "store_factor"?: RetailDecimal | null;
  "store_years"?: Array<RetailTargetSeasonalityYear>;
  "used_factor"?: RetailDecimal | null;
  "weights"?: Record<string, RetailDecimal> | null;
  "zone_factor"?: RetailDecimal | null;
  "zone_years"?: Array<RetailTargetSeasonalityYear>;
}

export interface RetailTargetSeasonalityYear {
  "base_month": string;
  "base_value": RetailDecimal;
  "ratio"?: RetailDecimal | null;
  "target_month": string;
  "target_value": RetailDecimal;
  "year_offset": number;
}

export interface RetailTargetSourceMonth {
  "label": string;
  "month": string;
  "role": string;
}

export interface RetailTargetSourceSummaryResponse {
  "actual_realized": RetailDecimal;
  "attainment_pct"?: RetailDecimal | null;
  "forecast_factor": RetailDecimal;
  "is_forecast": boolean;
  "label": string;
  "month": string;
  "realized": RetailDecimal;
  "target": RetailDecimal;
}

export interface RetailTargetStoreAgentResponse {
  "active_months_16": number;
  "agent": string;
  "avg_receipt"?: RetailDecimal | null;
  "bon2acc_pct"?: RetailDecimal | null;
  "focus_pct"?: RetailDecimal | null;
  "receipt_count": number;
  "sales_16m": RetailDecimal;
  "sales_share_pct": RetailDecimal;
  "total_quantity": number;
  "total_sales": RetailDecimal;
}

export interface RetailTargetStoreDetailResponse {
  "agents"?: Array<RetailTargetStoreAgentResponse>;
  "asm": string;
  "avg_sales_16m": RetailDecimal;
  "best_month"?: RetailTargetStoreHistoryPointResponse | null;
  "cohort_month": string;
  "final_target"?: RetailDecimal | null;
  "firma": string;
  "history"?: Array<RetailTargetStoreHistoryPointResponse>;
  "latest"?: RetailTargetStoreHistoryPointResponse | null;
  "locatie": string;
  "proposed_target": RetailDecimal;
  "regional": string;
  "site_code": string;
  "target_month": string;
}

export interface RetailTargetStoreHistoryPointResponse {
  "active_agents": number;
  "avg_receipt"?: RetailDecimal | null;
  "bon2acc_pct"?: RetailDecimal | null;
  "cartele_qty": number;
  "focus_pct"?: RetailDecimal | null;
  "month": string;
  "receipt_count": number;
  "target_pct"?: RetailDecimal | null;
  "target_value": RetailDecimal;
  "total_quantity": number;
  "total_sales": RetailDecimal;
  "working_days": number;
}

export interface RetailTargetTrendDetails {
  "base_month"?: string | null;
  "max"?: RetailDecimal | null;
  "min"?: RetailDecimal | null;
  "ratio"?: RetailDecimal | null;
  "raw_adjustment"?: RetailDecimal | null;
  "used_adjustment"?: RetailDecimal | null;
  "weight"?: RetailDecimal | null;
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

export interface RetailTaskDeleteResponse {
  "ok": boolean;
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
  "total_sales": RetailDecimal;
  "total_target": RetailDecimal;
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
    '200': Array<RetailCrmAlertResponse>;
    '422': RetailHTTPValidationError;
  }

  'get_scores_api_crm_scores_get': {
    '200': Array<RetailCrmScoreResponse>;
    '422': RetailHTTPValidationError;
  }

  'recalculate_scores_api_crm_scores_recalculate_post': {
    '200': RetailCrmRecalculateResponse;
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
    '200': RetailExportCatalogResponse;
  }

  'download_export_api_exports_download_post': {
    '200': Blob;
    '422': RetailHTTPValidationError;
  }

  'preview_export_api_exports_preview_post': {
    '200': RetailExportPreviewResponse;
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
    '200': Array<RetailHrAsmPerformanceItem>;
    '422': RetailHTTPValidationError;
  }

  'get_asm_perf_history_api_hr_asm_performance__asm_name__history_get': {
    '200': Array<RetailHrAsmHistoryItem>;
    '422': RetailHTTPValidationError;
  }

  'get_asm_salary_api_hr_asm_salary__asm_name__get': {
    '200': RetailHrAsmSalaryBreakdown;
    '422': RetailHTTPValidationError;
  }

  'get_leave_requests_api_hr_leave_requests_get': {
    '200': RetailLeaveRequestListResponse;
    '422': RetailHTTPValidationError;
  }

  'post_leave_request_api_hr_leave_requests_post': {
    '200': RetailLeaveRequestItem;
    '422': RetailHTTPValidationError;
  }

  'patch_leave_request_api_hr_leave_requests__request_id__patch': {
    '200': RetailLeaveRequestItem;
    '422': RetailHTTPValidationError;
  }

  'get_manager_overview_api_hr_manager_overview_get': {
    '200': Array<RetailHrManagerOverviewItem>;
    '422': RetailHTTPValidationError;
  }

  'get_performance_api_hr_performance__agent_name__get': {
    '200': Array<RetailHrAgentPerformanceItem>;
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
    '200': RetailPnlAnnualResponse;
    '422': RetailHTTPValidationError;
  }

  'months_api_store_pnl_months_get': {
    '200': RetailPnlMonthsResponse;
  }

  'overview_api_store_pnl_overview_get': {
    '200': RetailPnlOverviewResponse;
    '422': RetailHTTPValidationError;
  }

  'pnl_permissions_api_store_pnl_permissions_get': {
    '200': RetailPnlPermissionsResponse;
  }

  'regions_api_store_pnl_regions_get': {
    '200': RetailPnlRegionsResponse;
    '422': RetailHTTPValidationError;
  }

  'stores_api_store_pnl_stores_get': {
    '200': RetailPnlStoresResponse;
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
    '200': RetailTargetContextResponse;
  }

  'list_scenarios_api_target_calculator_scenarios_get': {
    '200': Array<RetailTargetScenarioSummaryResponse>;
  }

  'calculate_scenario_api_target_calculator_scenarios_calculate_post': {
    '200': RetailTargetScenarioResponse;
    '422': RetailHTTPValidationError;
  }

  'get_scenario_api_target_calculator_scenarios__scenario_id__get': {
    '200': RetailTargetScenarioResponse;
    '422': RetailHTTPValidationError;
  }

  'export_scenario_api_target_calculator_scenarios__scenario_id__export_get': {
    '200': Blob;
    '422': RetailHTTPValidationError;
  }

  'finalize_scenario_api_target_calculator_scenarios__scenario_id__finalize_post': {
    '200': RetailTargetScenarioResponse;
    '422': RetailHTTPValidationError;
  }

  'update_final_targets_api_target_calculator_scenarios__scenario_id__rows_patch': {
    '200': RetailTargetScenarioResponse;
    '422': RetailHTTPValidationError;
  }

  'get_store_detail_api_target_calculator_scenarios__scenario_id__stores__site_code__get': {
    '200': RetailTargetStoreDetailResponse;
    '422': RetailHTTPValidationError;
  }

  'get_tasks_api_tasks_get': {
    '200': RetailTaskListResponse;
    '422': RetailHTTPValidationError;
  }

  'post_task_api_tasks_post': {
    '200': RetailTaskItem;
    '422': RetailHTTPValidationError;
  }

  'remove_task_api_tasks__task_id__delete': {
    '200': RetailTaskDeleteResponse;
    '422': RetailHTTPValidationError;
  }

  'patch_task_api_tasks__task_id__patch': {
    '200': RetailTaskItem;
    '422': RetailHTTPValidationError;
  }

  'get_visits_report_api_visits_report_get': {
    '200': RetailVisitReportResponse;
    '422': RetailHTTPValidationError;
  }

  'get_visit_photo_api_visits_report_photo__visit_id___filename__get': {
    '200': Blob;
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
    '200': Array<RetailSalaryEvolutionPoint>;
    '422': RetailHTTPValidationError;
  }

  'salarii_overview_salarii_overview_get': {
    '200': RetailSalaryOverviewResponse;
    '422': RetailHTTPValidationError;
  }

  'list_records_salarii_records_get': {
    '200': Array<RetailSalaryRecordPublic>;
    '422': RetailHTTPValidationError;
  }

  'salarii_stores_salarii_stores_get': {
    '200': Array<RetailSalaryStoreOption>;
    '422': RetailHTTPValidationError;
  }

  'salarii_summary_salarii_summary_get': {
    '200': RetailSalarySummaryResponse;
    '422': RetailHTTPValidationError;
  }

  'salarii_trend_salarii_trend_get': {
    '200': Array<RetailSalaryTrendPoint>;
    '422': RetailHTTPValidationError;
  }

}

export const RETAIL_OPERATION_ROUTES = {
  'get_agent_evaluation_api_agents_evaluation_get': { method: 'get', path: '/api/agents/evaluation' },
  'get_agent_evaluation_v2_api_agents_evaluation_v2_get': { method: 'get', path: '/api/agents/evaluation-v2' },
  'get_agent_history_api_agents_history_get': { method: 'get', path: '/api/agents/history' },
  'get_agents_list_api_agents_list_get': { method: 'get', path: '/api/agents/list' },
  'get_agents_movement_api_agents_movement_get': { method: 'get', path: '/api/agents/movement' },
  'get_agents_overview_api_agents_overview_get': { method: 'get', path: '/api/agents/overview' },
  'get_agent_profile_api_agents_profile_get': { method: 'get', path: '/api/agents/profile' },
  'get_stores_coverage_api_agents_stores_coverage_get': { method: 'get', path: '/api/agents/stores-coverage' },
  'get_current_ai_forecast_api_ai_forecast_current_get': { method: 'get', path: '/api/ai-forecast/current' },
  'get_rolling_12_ai_forecast_api_ai_forecast_rolling_12_get': { method: 'get', path: '/api/ai-forecast/rolling-12' },
  'get_focus_history_api_campaigns_history_get': { method: 'get', path: '/api/campaigns/history' },
  'get_campaign_overview_api_campaigns_overview_get': { method: 'get', path: '/api/campaigns/overview' },
  'get_promotions_incentives_api_campaigns_promotions_incentives_get': { method: 'get', path: '/api/campaigns/promotions-incentives' },
  'get_active_contest_api_contests_active_get': { method: 'get', path: '/api/contests/active' },
  'get_active_contests_api_contests_active_all_get': { method: 'get', path: '/api/contests/active/all' },
  'get_alerts_api_crm_alerts_get': { method: 'get', path: '/api/crm/alerts' },
  'get_scores_api_crm_scores_get': { method: 'get', path: '/api/crm/scores' },
  'recalculate_scores_api_crm_scores_recalculate_post': { method: 'post', path: '/api/crm/scores/recalculate' },
  'get_dashboard_all_api_dashboard_all_get': { method: 'get', path: '/api/dashboard/all' },
  'get_dashboard_all_batch_api_dashboard_all_batch_post': { method: 'post', path: '/api/dashboard/all-batch' },
  'get_daily_sales_api_dashboard_daily_get': { method: 'get', path: '/api/dashboard/daily' },
  'get_monthly_history_api_dashboard_history_get': { method: 'get', path: '/api/dashboard/history' },
  'get_dashboard_history_details_batch_api_dashboard_history_details_batch_post': { method: 'post', path: '/api/dashboard/history-details-batch' },
  'get_history_by_year_api_dashboard_history_year_get': { method: 'get', path: '/api/dashboard/history-year' },
  'get_performance_detail_api_dashboard_performance_detail_get': { method: 'get', path: '/api/dashboard/performance-detail' },
  'get_premium_glass_api_dashboard_premium_glass_get': { method: 'get', path: '/api/dashboard/premium-glass' },
  'get_special_cards_api_dashboard_special_cards_get': { method: 'get', path: '/api/dashboard/special-cards' },
  'get_summary_api_dashboard_summary_get': { method: 'get', path: '/api/dashboard/summary' },
  'get_catalog_api_exports_catalog_get': { method: 'get', path: '/api/exports/catalog' },
  'download_export_api_exports_download_post': { method: 'post', path: '/api/exports/download' },
  'preview_export_api_exports_preview_post': { method: 'post', path: '/api/exports/preview' },
  'get_available_months_api_filters_months_get': { method: 'get', path: '/api/filters/months' },
  'get_filter_options_api_filters_options_get': { method: 'get', path: '/api/filters/options' },
  'grile_agent_targets_diff_api_grile_agent_targets_diff_post': { method: 'post', path: '/api/grile/agent-targets/diff' },
  'grile_agent_targets_operation_api_grile_agent_targets_operations__operation_id__get': { method: 'get', path: '/api/grile/agent-targets/operations/{operation_id}' },
  'grile_agent_targets_sync_api_grile_agent_targets_sync_post': { method: 'post', path: '/api/grile/agent-targets/sync' },
  'grile_monthly_download_api_grile_monthly_download__kind___month__get': { method: 'get', path: '/api/grile/monthly/download/{kind}/{month}' },
  'grile_monthly_job_api_grile_monthly_job__job_id__get': { method: 'get', path: '/api/grile/monthly/job/{job_id}' },
  'grile_monthly_manifest_approve_api_grile_monthly_manifests__manifest_id__approve_post': { method: 'post', path: '/api/grile/monthly/manifests/{manifest_id}/approve' },
  'grile_monthly_manifest_api_grile_monthly_manifests__month__get': { method: 'get', path: '/api/grile/monthly/manifests/{month}' },
  'grile_monthly_permissions_api_grile_monthly_permissions_get': { method: 'get', path: '/api/grile/monthly/permissions' },
  'grile_monthly_run_api_grile_monthly_run_post': { method: 'post', path: '/api/grile/monthly/run' },
  'grile_overview_api_grile_overview_get': { method: 'get', path: '/api/grile/overview' },
  'grile_run_api_grile_run_post': { method: 'post', path: '/api/grile/run' },
  'grile_run_status_api_grile_run_status_get': { method: 'get', path: '/api/grile/run-status' },
  'grile_store_refresh_api_grile_stores__site_code__refresh_post': { method: 'post', path: '/api/grile/stores/{site_code}/refresh' },
  'get_asm_perf_api_hr_asm_performance_get': { method: 'get', path: '/api/hr/asm-performance' },
  'get_asm_perf_history_api_hr_asm_performance__asm_name__history_get': { method: 'get', path: '/api/hr/asm-performance/{asm_name}/history' },
  'get_asm_salary_api_hr_asm_salary__asm_name__get': { method: 'get', path: '/api/hr/asm-salary/{asm_name}' },
  'get_leave_requests_api_hr_leave_requests_get': { method: 'get', path: '/api/hr/leave-requests' },
  'post_leave_request_api_hr_leave_requests_post': { method: 'post', path: '/api/hr/leave-requests' },
  'patch_leave_request_api_hr_leave_requests__request_id__patch': { method: 'patch', path: '/api/hr/leave-requests/{request_id}' },
  'get_manager_overview_api_hr_manager_overview_get': { method: 'get', path: '/api/hr/manager-overview' },
  'get_performance_api_hr_performance__agent_name__get': { method: 'get', path: '/api/hr/performance/{agent_name}' },
  'reconcile_erp_report_file_api_import_erp_reconciliation_post': { method: 'post', path: '/api/import/erp-reconciliation' },
  'get_import_history_api_import_history_get': { method: 'get', path: '/api/import/history' },
  'get_import_job_status_api_import_jobs__job_id__get': { method: 'get', path: '/api/import/jobs/{job_id}' },
  'upload_promo_actuals_file_api_import_promo_actuals_post': { method: 'post', path: '/api/import/promo-actuals' },
  'upload_sales_file_api_import_sales_post': { method: 'post', path: '/api/import/sales' },
  'promote_sales_generation_api_import_sales__snapshot_id__promote_post': { method: 'post', path: '/api/import/sales/{snapshot_id}/promote' },
  'annual_api_store_pnl_annual_get': { method: 'get', path: '/api/store-pnl/annual' },
  'months_api_store_pnl_months_get': { method: 'get', path: '/api/store-pnl/months' },
  'overview_api_store_pnl_overview_get': { method: 'get', path: '/api/store-pnl/overview' },
  'pnl_permissions_api_store_pnl_permissions_get': { method: 'get', path: '/api/store-pnl/permissions' },
  'regions_api_store_pnl_regions_get': { method: 'get', path: '/api/store-pnl/regions' },
  'stores_api_store_pnl_stores_get': { method: 'get', path: '/api/store-pnl/stores' },
  'list_stores_api_stores_get': { method: 'get', path: '/api/stores' },
  'save_targets_api_stores_targets_post': { method: 'post', path: '/api/stores/targets' },
  'change_store_activity_api_stores__site_code__activity_post': { method: 'post', path: '/api/stores/{site_code}/activity' },
  'get_context_api_target_calculator_context_get': { method: 'get', path: '/api/target-calculator/context' },
  'list_scenarios_api_target_calculator_scenarios_get': { method: 'get', path: '/api/target-calculator/scenarios' },
  'calculate_scenario_api_target_calculator_scenarios_calculate_post': { method: 'post', path: '/api/target-calculator/scenarios/calculate' },
  'get_scenario_api_target_calculator_scenarios__scenario_id__get': { method: 'get', path: '/api/target-calculator/scenarios/{scenario_id}' },
  'export_scenario_api_target_calculator_scenarios__scenario_id__export_get': { method: 'get', path: '/api/target-calculator/scenarios/{scenario_id}/export' },
  'finalize_scenario_api_target_calculator_scenarios__scenario_id__finalize_post': { method: 'post', path: '/api/target-calculator/scenarios/{scenario_id}/finalize' },
  'update_final_targets_api_target_calculator_scenarios__scenario_id__rows_patch': { method: 'patch', path: '/api/target-calculator/scenarios/{scenario_id}/rows' },
  'get_store_detail_api_target_calculator_scenarios__scenario_id__stores__site_code__get': { method: 'get', path: '/api/target-calculator/scenarios/{scenario_id}/stores/{site_code}' },
  'get_tasks_api_tasks_get': { method: 'get', path: '/api/tasks' },
  'post_task_api_tasks_post': { method: 'post', path: '/api/tasks' },
  'remove_task_api_tasks__task_id__delete': { method: 'delete', path: '/api/tasks/{task_id}' },
  'patch_task_api_tasks__task_id__patch': { method: 'patch', path: '/api/tasks/{task_id}' },
  'get_visits_report_api_visits_report_get': { method: 'get', path: '/api/visits-report' },
  'get_visit_photo_api_visits_report_photo__visit_id___filename__get': { method: 'get', path: '/api/visits-report/photo/{visit_id}/{filename}' },
  'get_visits_tree_api_visits_report_tree_get': { method: 'get', path: '/api/visits-report/tree' },
  'get_visit_detail_api_visits_report_visit__visit_id__get': { method: 'get', path: '/api/visits-report/visit/{visit_id}' },
  'session_status_auth_session_get': { method: 'get', path: '/auth/session' },
  'session_login_auth_session_login_get': { method: 'get', path: '/auth/session/login' },
  'session_logout_auth_session_logout_post': { method: 'post', path: '/auth/session/logout' },
  'metrics_metrics_get': { method: 'get', path: '/metrics' },
  'agent_history_by_retail_code_salarii_agents_history_by_retail_code_get': { method: 'get', path: '/salarii/agents/history-by-retail-code' },
  'agents_summary_salarii_agents_summary_get': { method: 'get', path: '/salarii/agents/summary' },
  'agent_history_salarii_agents__person_id__history_get': { method: 'get', path: '/salarii/agents/{person_id}/history' },
  'audit_salary_export_salarii_audit_export_post': { method: 'post', path: '/salarii/audit/export' },
  'salarii_evolution_salarii_evolution_get': { method: 'get', path: '/salarii/evolution' },
  'salarii_overview_salarii_overview_get': { method: 'get', path: '/salarii/overview' },
  'list_records_salarii_records_get': { method: 'get', path: '/salarii/records' },
  'salarii_stores_salarii_stores_get': { method: 'get', path: '/salarii/stores' },
  'salarii_summary_salarii_summary_get': { method: 'get', path: '/salarii/summary' },
  'salarii_trend_salarii_trend_get': { method: 'get', path: '/salarii/trend' },
} as const;
