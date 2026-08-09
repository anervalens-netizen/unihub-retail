/* GENERATED FILE. Run npm run contracts:generate; do not edit manually. */
export const RETAIL_OPENAPI_SHA256 = '40d92e0c005aabe1a60a0f2dc5d57467e8c918bcd511a6e94a60ecaf3d5ecb78' as const; // pragma: allowlist secret

export type RetailDecimal = string & { readonly __retailDecimal: unique symbol };

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
  "has_actual": boolean;
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
  "avg_completion"?: number | null;
  "forecast_factor"?: number | null;
  "kpi_bon2acc"?: number | null;
  "kpi_bon2acc_avg"?: number | null;
  "kpi_bon2acc_score"?: number | null;
  "kpi_focus"?: number | null;
  "kpi_focus_avg"?: number | null;
  "kpi_focus_score"?: number | null;
  "kpi_pct"?: number | null;
  "nr_vizite"?: number | null;
  "target_attainment"?: number | null;
  "target_pct"?: number | null;
  "trend_pct"?: number | null;
  "visits_pct"?: number | null;
}

export interface RetailCrmRecalculateResponse {
  "month": string;
  "recalculated": number;
}

export interface RetailCrmScoreResponse {
  "asm"?: string | null;
  "breakdown": RetailCrmBreakdownResponse;
  "calculated_at"?: string | null;
  "locatie"?: string | null;
  "regional"?: string | null;
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

export interface RetailExportOperationPublishUncertainDetail {
  "job_id"?: string | null;
  "operation_id"?: number | null;
  "status": string;
}

export interface RetailExportOperationResponse {
  "artifact_sha256"?: string | null;
  "artifact_size"?: number | null;
  "build_seconds"?: number | null;
  "can_download"?: boolean;
  "cell_count"?: number | null;
  "created_at": string;
  "error_code"?: string | null;
  "expires_at"?: string | null;
  "filename"?: string | null;
  "finished_at"?: string | null;
  "id": number;
  "job_id": string;
  "kind": "daily_metrics" | "daily_comparison";
  "peak_rss_bytes"?: number | null;
  "started_at"?: string | null;
  "status": "queued" | "running" | "completed" | "failed" | "cancelled" | "expired";
}

export interface RetailExportOperationUnavailableResponse {
  "detail": string | RetailExportOperationPublishUncertainDetail;
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

export interface RetailGrileAgentTargetEnqueueResponse {
  "job_id"?: string | null;
  "operation"?: RetailGrileAgentTargetOperationResponse | null;
  "operation_id": number;
  "status": string;
}

export interface RetailGrileAgentTargetOperationEnvelope {
  "operation": RetailGrileAgentTargetOperationResponse;
}

export interface RetailGrileAgentTargetOperationResponse {
  "after_count"?: number | null;
  "after_sha256"?: string | null;
  "before_count"?: number | null;
  "before_sha256"?: string | null;
  "created_at"?: string | null;
  "diff"?: Record<string, unknown> | null;
  "error_message"?: string | null;
  "finished_at"?: string | null;
  "id": number;
  "job_id"?: string | null;
  "mode": "dry_run" | "sync";
  "run_month": string;
  "started_at"?: string | null;
  "status": string;
}

export interface RetailGrileFirmResponse {
  "name": string;
  "stores": Array<RetailGrileStoreResponse>;
}

export interface RetailGrileManagerResponse {
  "avg_completion"?: number | null;
  "business_unknown": number;
  "legacy_completion_windows": number;
  "name": string;
  "ok": number;
  "problems": number;
  "provider_errors": number;
  "provider_fresh": number;
  "provider_stale": number;
  "provider_unknown": number;
  "store_count": number;
  "team_leaders": Array<RetailGrileTeamLeaderResponse>;
}

export interface RetailGrileMonthlyJobResponse {
  "error"?: string | null;
  "job_id": string;
  "result"?: Record<string, unknown> | null;
  "status": "queued" | "in_progress" | "complete" | "not_found";
}

export interface RetailGrileMonthlyManifestEnvelope {
  "manifest"?: RetailGrileMonthlyManifestResponse | null;
}

export interface RetailGrileMonthlyManifestResponse {
  "approved": boolean;
  "approved_at"?: string | null;
  "consumed_at"?: string | null;
  "created_at"?: string | null;
  "error_count": number;
  "expected"?: Record<string, unknown>;
  "id": number;
  "manifest_sha256"?: string | null;
  "month": string;
  "operation": "finalize" | "archive" | "reset";
  "operation_id": number;
  "processed"?: Record<string, unknown>;
  "status": "building" | "failed" | "verified" | "approved" | "consumed" | "rolled_back" | "uncertain";
  "verified_at"?: string | null;
}

export interface RetailGrileMonthlyRunResponse {
  "dry_run"?: boolean | null;
  "job_id"?: string | null;
  "month": string;
  "month_label": string;
  "next_month_label"?: string | null;
  "op": "finalize" | "archive" | "reset";
  "operation"?: Record<string, unknown> | null;
  "operation_id": number;
  "status": "enqueued" | "already_running" | "already_completed";
}

export interface RetailGrileOverviewResponse {
  "managers": Array<RetailGrileManagerResponse>;
  "month": string;
  "run"?: RetailGrileRunResponse | null;
  "summary": RetailGrileOverviewSummary;
  "total_sheets": number;
}

export interface RetailGrileOverviewSummary {
  "business_ok": number;
  "business_problems": number;
  "business_unknown": number;
  "legacy_completion_windows": number;
  "provider_errors": number;
  "provider_fresh": number;
  "provider_stale": number;
  "provider_unknown": number;
}

export interface RetailGrilePermissionsResponse {
  "can_run": boolean;
}

export interface RetailGrileProviderStatus {
  "last_attempt_at"?: string | null;
  "last_error_at"?: string | null;
  "last_error_code"?: string | null;
  "last_error_message"?: string | null;
  "last_success_at"?: string | null;
  "stale_age_seconds"?: number | null;
  "state": "fresh" | "stale" | "error" | "unknown";
}

export interface RetailGrileRunEnqueueResponse {
  "job_id"?: string | null;
  "month"?: string | null;
  "run"?: RetailGrileRunResponse | null;
  "run_id"?: number | null;
  "status": "enqueued" | "already_running";
}

export interface RetailGrileRunResponse {
  "active": boolean;
  "created_at"?: string | null;
  "duration_ms"?: number | null;
  "error_count": number;
  "error_message"?: string | null;
  "finished_at"?: string | null;
  "heartbeat_at"?: string | null;
  "id": number;
  "ok_count": number;
  "problem_count": number;
  "progress_current": number;
  "progress_total": number;
  "run_month": string;
  "source": "manual" | "auto";
  "source_snapshot_id"?: number | null;
  "started_at"?: string | null;
  "status": "queued" | "running" | "completed" | "failed";
}

export interface RetailGrileRunStatusResponse {
  "run"?: RetailGrileRunResponse | null;
}

export interface RetailGrileStoreRefreshEnqueueResponse {
  "job_id"?: string | null;
  "month": string;
  "operation_id": number;
  "status": "enqueued" | "already_running";
}

export interface RetailGrileStoreRefreshOperationEnvelope {
  "operation": RetailGrileStoreRefreshOperationResponse;
}

export interface RetailGrileStoreRefreshOperationResponse {
  "created_at": string;
  "error_code"?: string | null;
  "error_message"?: string | null;
  "finished_at"?: string | null;
  "heartbeat_at"?: string | null;
  "id": number;
  "projection_applied"?: boolean | null;
  "run_month": string;
  "site_code": string;
  "started_at"?: string | null;
  "status": "queued" | "running" | "completed" | "failed" | "cancelled" | "unknown";
}

export interface RetailGrileStoreResponse {
  "asm": string;
  "checked_at"?: string | null;
  "completion_algorithm_version": number;
  "completion_as_of"?: string | null;
  "completion_pct"?: number | null;
  "completion_window_status": "current" | "legacy_incomplete_window";
  "days_elapsed"?: number | null;
  "db_max_sale_date"?: string | null;
  "db_sales_mtd"?: RetailDecimal | null;
  "db_target"?: RetailDecimal | null;
  "error_code"?: string | null;
  "error_message"?: string | null;
  "fill_status"?: string | null;
  "firma": string;
  "grila_sales"?: RetailDecimal | null;
  "grila_target"?: RetailDecimal | null;
  "last_edit"?: string | null;
  "locatie": string;
  "missing_days"?: Array<number> | null;
  "provider_status": RetailGrileProviderStatus;
  "regional": string;
  "sales_diff"?: RetailDecimal | null;
  "sales_status"?: string | null;
  "sheet_id"?: string | null;
  "site_code": string;
  "target_diff"?: RetailDecimal | null;
  "target_status"?: string | null;
  "team_leader_name"?: string | null;
}

export interface RetailGrileTeamLeaderResponse {
  "firms": Array<RetailGrileFirmResponse>;
  "name"?: string | null;
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
  "anomalies"?: Array<RetailSalesGenerationAnomaly> | null;
  "company_count"?: number | null;
  "incoming_set_sha256"?: string | null;
  "incoming_store_count"?: number | null;
  "metadata_change_count"?: number | null;
  "missing_active_set_sha256"?: string | null;
  "missing_active_store_count"?: number | null;
  "missing_prior_set_sha256"?: string | null;
  "missing_prior_store_count"?: number | null;
  "new_store_count"?: number | null;
  "new_store_set_sha256"?: string | null;
  "prior_snapshot_coverage_pct"?: number | null;
  "prior_snapshot_store_count"?: number | null;
  "store_activity_writes"?: number | null;
  "stores_missing_count"?: number | null;
  "stores_present_count"?: number | null;
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
  "erp_result"?: RetailErpReconciliationResponse | null;
  "error"?: string | null;
  "job_id": string;
  "job_kind"?: "sales" | "promo_actuals" | "erp_reconciliation";
  "promo_result"?: RetailPromoActualImportResponse | null;
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
  "cogs": RetailDecimal;
  "depreciation": RetailDecimal;
  "ebit": RetailDecimal;
  "ebitda": RetailDecimal;
  "gross_margin": RetailDecimal;
  "is_estimated": boolean;
  "month_count": number;
  "operating_costs": RetailDecimal;
  "revenue": RetailDecimal;
  "store_count": number;
  "year": string;
}

export interface RetailPnlAnnualResponse {
  "annual": Array<RetailPnlAnnualItemResponse>;
}

export interface RetailPnlMetricsResponse {
  "cogs": RetailDecimal;
  "depreciation": RetailDecimal;
  "ebit": RetailDecimal;
  "ebitda": RetailDecimal;
  "gross_margin": RetailDecimal;
  "operating_costs": RetailDecimal;
  "revenue": RetailDecimal;
}

export interface RetailPnlMonthResponse {
  "has_actual": boolean;
  "has_estimated": boolean;
  "month": string;
}

export interface RetailPnlMonthlyItemResponse {
  "cogs": RetailDecimal;
  "depreciation": RetailDecimal;
  "ebit": RetailDecimal;
  "ebitda": RetailDecimal;
  "gross_margin": RetailDecimal;
  "is_estimated": boolean;
  "month": string;
  "operating_costs": RetailDecimal;
  "revenue": RetailDecimal;
}

export interface RetailPnlMonthsResponse {
  "months": Array<RetailPnlMonthResponse>;
}

export interface RetailPnlOverviewResponse {
  "categories"?: Record<string, RetailDecimal>;
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
  "difference_to_net": RetailDecimal;
  "month": string;
  "pnl_revenue": RetailDecimal;
  "pnl_to_net_sales_pct"?: RetailDecimal | null;
  "retail_sales_gross": RetailDecimal;
  "retail_sales_net": RetailDecimal;
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
  "cogs": RetailDecimal;
  "company": string;
  "depreciation": RetailDecimal;
  "ebit": RetailDecimal;
  "ebitda": RetailDecimal;
  "gross_margin": RetailDecimal;
  "has_estimates": boolean;
  "location": string;
  "operating_costs": RetailDecimal;
  "regional"?: string | null;
  "revenue": RetailDecimal;
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
  "classification"?: "informational" | "structural_contradiction" | null;
  "code": string;
  "count"?: number | null;
  "cutoff_date"?: string | null;
  "drop_pct"?: string | null;
  "import_month"?: string | null;
  "incoming"?: string | null;
  "max_sale_date"?: string | null;
  "message": string;
  "months"?: Array<string> | null;
  "previous"?: string | null;
  "set_sha256"?: string | null;
  "site_days"?: Array<string> | null;
  "threshold_pct"?: string | null;
}

export interface RetailSalesGenerationManifest {
  "agent_count"?: number | null;
  "anomalies"?: Array<RetailSalesGenerationAnomaly>;
  "business_sha256"?: string | null;
  "cutoff_date"?: string | null;
  "generation_state"?: "validated" | "promoting" | "promoted" | null;
  "import_month"?: string | null;
  "max_sale_date"?: string | null;
  "parser_resources"?: Record<string, number | string | null> | null;
  "receipt_count"?: number | null;
  "rows_filtered"?: number | null;
  "rows_imported"?: number | null;
  "rows_in_file"?: number | null;
  "schema_version"?: number | null;
  "site_day_count"?: number | null;
  "site_day_sha256"?: string | null;
  "site_days"?: Array<RetailSalesSiteDayManifest> | null;
  "source_sha256"?: string | null;
  "stage_rows_sha256"?: string | null;
  "store_count"?: number | null;
  "total_quantity"?: number | null;
  "total_value"?: string | null;
}

export interface RetailSalesGenerationPromotionRequest {
  "generation_token": string;
  "manifest_sha256": string;
  "override_reason"?: string | null;
}

export interface RetailSalesSiteDayManifest {
  "quantity": number;
  "receipts": number;
  "rows": number;
  "sale_date": string;
  "site_code": string;
  "value": string;
}

export interface RetailSessionLogoutResponse {
  "logout_url": string;
}

export interface RetailSessionProfileResponse {
  "email"?: string | null;
  "groups": Array<string>;
  "preferred_username"?: string | null;
  "sub": string;
}

export interface RetailSessionStatusResponse {
  "csrf_token": string;
  "profile": RetailSessionProfileResponse;
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

export interface RetailStoreTargetsSaveResponse {
  "inserted": number;
}

export interface RetailTargetApiErrorResponse {
  "detail": string | Record<string, unknown>;
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
  "minimum_seasonality_base"?: RetailDecimal | null;
  "new_store_weights"?: Record<string, RetailDecimal>;
  "previous_month_cap_pct"?: RetailDecimal | null;
  "profitability"?: RetailTargetProfitabilityAssumptionsResponse | null;
  "profitability_summary"?: RetailTargetProfitabilitySummaryResponse | null;
  "seasonality_max"?: RetailDecimal | null;
  "seasonality_min"?: RetailDecimal | null;
  "seasonality_years"?: number | null;
  "strong_weights"?: Record<string, RetailDecimal>;
  "trend_adjustment_max"?: RetailDecimal | null;
  "trend_adjustment_min"?: RetailDecimal | null;
  "trend_weight"?: RetailDecimal | null;
  "weak_weights"?: Record<string, RetailDecimal>;
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

export interface RetailTargetForecastCoverageResponse {
  "covered_store_count": number;
  "cutoff"?: string | null;
  "cutoff_max"?: string | null;
  "cutoff_min"?: string | null;
  "expected_store_count": number;
  "missing_site_codes"?: Array<string>;
  "mode": string;
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

export interface RetailTargetProfitabilityAssumptionsResponse {
  "base_salary_default": RetailDecimal;
  "base_salary_high"?: RetailDecimal | null;
  "default_store_agent_count": number;
  "meal_vouchers_per_agent": RetailDecimal;
  "salary_assumed_attainment": RetailDecimal;
  "salary_pnl_factor": RetailDecimal;
  "sales_commission_rate": RetailDecimal;
  "sun_plaza_agent_count"?: number | null;
  "target_rule_set_hash"?: string | null;
  "target_rule_set_id"?: string | null;
  "vat_effective_from"?: string | null;
  "vat_multiplier": RetailDecimal;
  "vat_rate": RetailDecimal;
  "vat_rule_id": string;
  "vat_ruleset_hash"?: string | null;
  "vat_ruleset_id": string;
}

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
  "assumptions"?: RetailTargetProfitabilityAssumptionsResponse | null;
  "break_even_total"?: RetailDecimal | null;
  "forecast_below_break_even_count": number;
  "forecast_coverage"?: RetailTargetForecastCoverageResponse | null;
  "forecast_run"?: RetailTargetForecastRunResponse | null;
  "forecast_store_count": number;
  "forecast_total"?: RetailDecimal | null;
  "input_sha256"?: string | null;
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
  "calculation_input_sha256"?: string | null;
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
  "profitability_input_sha256"?: string | null;
  "profitability_summary"?: RetailTargetProfitabilitySummaryResponse | null;
  "proposed_total"?: RetailDecimal;
  "regional_summary"?: Array<RetailTargetRegionalSummaryResponse>;
  "remaining_difference": RetailDecimal;
  "revision": number;
  "rows": Array<RetailTargetScenarioRowResponse>;
  "rule_set_hash"?: string | null;
  "rule_set_id"?: string | null;
  "rule_set_snapshot"?: Record<string, unknown> | null;
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
  "manager_override_at"?: string | null;
  "manager_override_reason"?: string | null;
  "manager_override_revision"?: number | null;
  "manager_override_target"?: RetailDecimal | null;
  "normalized_weight"?: RetailDecimal | null;
  "note"?: string | null;
  "profitability"?: RetailTargetProfitabilityResponse | null;
  "proposed_target": RetailDecimal;
  "regional": string;
  "site_code": string;
  "updated_at"?: string | null;
}

export interface RetailTargetScenarioSummaryResponse {
  "calculation_input_sha256"?: string | null;
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
  "profitability_input_sha256"?: string | null;
  "proposed_total"?: RetailDecimal;
  "revision": number;
  "rule_set_hash"?: string | null;
  "rule_set_id"?: string | null;
  "rule_set_snapshot"?: Record<string, unknown> | null;
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
  'create_export_operation_api_exports_operations_post' |
  'get_resumable_export_operation_api_exports_operations_resumable_get' |
  'get_export_operation_api_exports_operations__operation_id__get' |
  'cancel_export_operation_api_exports_operations__operation_id__cancel_post' |
  'download_export_operation_api_exports_operations__operation_id__download_get' |
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
  'grile_store_refresh_operation_api_grile_store_refreshes__operation_id__get' |
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

  'create_export_operation_api_exports_operations_post': {
    '200': RetailExportOperationResponse;
    '400': void;
    '409': void;
    '422': RetailHTTPValidationError;
    '503': RetailExportOperationUnavailableResponse;
  }

  'get_resumable_export_operation_api_exports_operations_resumable_get': {
    '200': RetailExportOperationResponse | null;
  }

  'get_export_operation_api_exports_operations__operation_id__get': {
    '200': RetailExportOperationResponse;
    '404': void;
    '422': RetailHTTPValidationError;
  }

  'cancel_export_operation_api_exports_operations__operation_id__cancel_post': {
    '200': RetailExportOperationResponse;
    '404': void;
    '409': void;
    '422': RetailHTTPValidationError;
  }

  'download_export_operation_api_exports_operations__operation_id__download_get': {
    '200': Blob;
    '404': void;
    '409': void;
    '410': void;
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
    '200': RetailGrileAgentTargetEnqueueResponse;
    '422': RetailHTTPValidationError;
  }

  'grile_agent_targets_operation_api_grile_agent_targets_operations__operation_id__get': {
    '200': RetailGrileAgentTargetOperationEnvelope;
    '422': RetailHTTPValidationError;
  }

  'grile_agent_targets_sync_api_grile_agent_targets_sync_post': {
    '200': RetailGrileAgentTargetEnqueueResponse;
    '422': RetailHTTPValidationError;
  }

  'grile_monthly_download_api_grile_monthly_download__kind___month__get': {
    '200': unknown;
    '422': RetailHTTPValidationError;
  }

  'grile_monthly_job_api_grile_monthly_job__job_id__get': {
    '200': RetailGrileMonthlyJobResponse;
    '422': RetailHTTPValidationError;
  }

  'grile_monthly_manifest_approve_api_grile_monthly_manifests__manifest_id__approve_post': {
    '200': RetailGrileMonthlyManifestEnvelope;
    '422': RetailHTTPValidationError;
  }

  'grile_monthly_manifest_api_grile_monthly_manifests__month__get': {
    '200': RetailGrileMonthlyManifestEnvelope;
    '422': RetailHTTPValidationError;
  }

  'grile_monthly_permissions_api_grile_monthly_permissions_get': {
    '200': RetailGrilePermissionsResponse;
  }

  'grile_monthly_run_api_grile_monthly_run_post': {
    '200': RetailGrileMonthlyRunResponse;
    '422': RetailHTTPValidationError;
  }

  'grile_overview_api_grile_overview_get': {
    '200': RetailGrileOverviewResponse;
    '422': RetailHTTPValidationError;
  }

  'grile_run_api_grile_run_post': {
    '200': RetailGrileRunEnqueueResponse;
    '422': RetailHTTPValidationError;
  }

  'grile_run_status_api_grile_run_status_get': {
    '200': RetailGrileRunStatusResponse;
    '422': RetailHTTPValidationError;
  }

  'grile_store_refresh_operation_api_grile_store_refreshes__operation_id__get': {
    '200': RetailGrileStoreRefreshOperationEnvelope;
    '422': RetailHTTPValidationError;
  }

  'grile_store_refresh_api_grile_stores__site_code__refresh_post': {
    '202': RetailGrileStoreRefreshEnqueueResponse;
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
    '200': RetailImportJobStatus;
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
    '200': RetailImportJobStatus;
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
    '200': RetailStoreTargetsSaveResponse;
    '422': RetailHTTPValidationError;
  }

  'change_store_activity_api_stores__site_code__activity_post': {
    '200': RetailStoreActivityChangeResponse;
    '422': RetailHTTPValidationError;
  }

  'get_context_api_target_calculator_context_get': {
    '200': RetailTargetContextResponse;
    '404': RetailTargetApiErrorResponse;
  }

  'list_scenarios_api_target_calculator_scenarios_get': {
    '200': Array<RetailTargetScenarioSummaryResponse>;
  }

  'calculate_scenario_api_target_calculator_scenarios_calculate_post': {
    '200': RetailTargetScenarioResponse;
    '400': RetailTargetApiErrorResponse;
    '409': RetailTargetApiErrorResponse;
    '422': RetailHTTPValidationError;
  }

  'get_scenario_api_target_calculator_scenarios__scenario_id__get': {
    '200': RetailTargetScenarioResponse;
    '404': RetailTargetApiErrorResponse;
    '409': RetailTargetApiErrorResponse;
    '422': RetailHTTPValidationError;
  }

  'export_scenario_api_target_calculator_scenarios__scenario_id__export_get': {
    '200': Blob;
    '404': RetailTargetApiErrorResponse;
    '409': RetailTargetApiErrorResponse;
    '422': RetailHTTPValidationError;
  }

  'finalize_scenario_api_target_calculator_scenarios__scenario_id__finalize_post': {
    '200': RetailTargetScenarioResponse;
    '400': RetailTargetApiErrorResponse;
    '404': RetailTargetApiErrorResponse;
    '409': RetailTargetApiErrorResponse;
    '422': RetailHTTPValidationError;
  }

  'update_final_targets_api_target_calculator_scenarios__scenario_id__rows_patch': {
    '200': RetailTargetScenarioResponse;
    '400': RetailTargetApiErrorResponse;
    '404': RetailTargetApiErrorResponse;
    '409': RetailTargetApiErrorResponse;
    '422': RetailHTTPValidationError;
  }

  'get_store_detail_api_target_calculator_scenarios__scenario_id__stores__site_code__get': {
    '200': RetailTargetStoreDetailResponse;
    '404': RetailTargetApiErrorResponse;
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
    '200': RetailSessionStatusResponse;
  }

  'session_login_auth_session_login_get': {
    '200': unknown;
  }

  'session_logout_auth_session_logout_post': {
    '200': RetailSessionLogoutResponse;
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

export interface RetailOperationSuccesses {
  'get_agent_evaluation_api_agents_evaluation_get': RetailAgentEvaluationResponse;
  'get_agent_evaluation_v2_api_agents_evaluation_v2_get': RetailAgentEvaluationV2Response;
  'get_agent_history_api_agents_history_get': RetailAgentHistoryResponse;
  'get_agents_list_api_agents_list_get': RetailAgentListResponse;
  'get_agents_movement_api_agents_movement_get': RetailAgentMovementResponse;
  'get_agents_overview_api_agents_overview_get': RetailAgentsOverviewResponse;
  'get_agent_profile_api_agents_profile_get': RetailAgentProfileResponse;
  'get_stores_coverage_api_agents_stores_coverage_get': RetailStoreCoverageResponse;
  'get_current_ai_forecast_api_ai_forecast_current_get': RetailAiForecastResponse;
  'get_rolling_12_ai_forecast_api_ai_forecast_rolling_12_get': RetailAiForecastRollingResponse;
  'get_focus_history_api_campaigns_history_get': RetailFocusHistoryResponse;
  'get_campaign_overview_api_campaigns_overview_get': RetailCampaignSnapshot;
  'get_promotions_incentives_api_campaigns_promotions_incentives_get': RetailCampaignsPromotionsResponse;
  'get_active_contest_api_contests_active_get': RetailContestResponse | null;
  'get_active_contests_api_contests_active_all_get': Array<RetailContestResponse>;
  'get_alerts_api_crm_alerts_get': Array<RetailCrmAlertResponse>;
  'get_scores_api_crm_scores_get': Array<RetailCrmScoreResponse>;
  'recalculate_scores_api_crm_scores_recalculate_post': RetailCrmRecalculateResponse;
  'get_dashboard_all_api_dashboard_all_get': RetailDashboardAllResponse;
  'get_dashboard_all_batch_api_dashboard_all_batch_post': RetailDashboardAllBatchResponse;
  'get_daily_sales_api_dashboard_daily_get': Array<RetailDailySalesPoint>;
  'get_monthly_history_api_dashboard_history_get': RetailDashboardHistoryResponse;
  'get_dashboard_history_details_batch_api_dashboard_history_details_batch_post': RetailDashboardAllBatchResponse;
  'get_history_by_year_api_dashboard_history_year_get': RetailYearHistoryResponse;
  'get_performance_detail_api_dashboard_performance_detail_get': RetailPerformanceDetailResponse;
  'get_premium_glass_api_dashboard_premium_glass_get': RetailPremiumGlassAnalysis;
  'get_special_cards_api_dashboard_special_cards_get': RetailDashboardSpecialCardsResponse;
  'get_summary_api_dashboard_summary_get': RetailDashboardSummary;
  'get_catalog_api_exports_catalog_get': RetailExportCatalogResponse;
  'download_export_api_exports_download_post': Blob;
  'create_export_operation_api_exports_operations_post': RetailExportOperationResponse;
  'get_resumable_export_operation_api_exports_operations_resumable_get': RetailExportOperationResponse | null;
  'get_export_operation_api_exports_operations__operation_id__get': RetailExportOperationResponse;
  'cancel_export_operation_api_exports_operations__operation_id__cancel_post': RetailExportOperationResponse;
  'download_export_operation_api_exports_operations__operation_id__download_get': Blob;
  'preview_export_api_exports_preview_post': RetailExportPreviewResponse;
  'get_available_months_api_filters_months_get': Array<string>;
  'get_filter_options_api_filters_options_get': RetailFilterOptions;
  'grile_agent_targets_diff_api_grile_agent_targets_diff_post': RetailGrileAgentTargetEnqueueResponse;
  'grile_agent_targets_operation_api_grile_agent_targets_operations__operation_id__get': RetailGrileAgentTargetOperationEnvelope;
  'grile_agent_targets_sync_api_grile_agent_targets_sync_post': RetailGrileAgentTargetEnqueueResponse;
  'grile_monthly_download_api_grile_monthly_download__kind___month__get': unknown;
  'grile_monthly_job_api_grile_monthly_job__job_id__get': RetailGrileMonthlyJobResponse;
  'grile_monthly_manifest_approve_api_grile_monthly_manifests__manifest_id__approve_post': RetailGrileMonthlyManifestEnvelope;
  'grile_monthly_manifest_api_grile_monthly_manifests__month__get': RetailGrileMonthlyManifestEnvelope;
  'grile_monthly_permissions_api_grile_monthly_permissions_get': RetailGrilePermissionsResponse;
  'grile_monthly_run_api_grile_monthly_run_post': RetailGrileMonthlyRunResponse;
  'grile_overview_api_grile_overview_get': RetailGrileOverviewResponse;
  'grile_run_api_grile_run_post': RetailGrileRunEnqueueResponse;
  'grile_run_status_api_grile_run_status_get': RetailGrileRunStatusResponse;
  'grile_store_refresh_operation_api_grile_store_refreshes__operation_id__get': RetailGrileStoreRefreshOperationEnvelope;
  'grile_store_refresh_api_grile_stores__site_code__refresh_post': RetailGrileStoreRefreshEnqueueResponse;
  'get_asm_perf_api_hr_asm_performance_get': Array<RetailHrAsmPerformanceItem>;
  'get_asm_perf_history_api_hr_asm_performance__asm_name__history_get': Array<RetailHrAsmHistoryItem>;
  'get_asm_salary_api_hr_asm_salary__asm_name__get': RetailHrAsmSalaryBreakdown;
  'get_leave_requests_api_hr_leave_requests_get': RetailLeaveRequestListResponse;
  'post_leave_request_api_hr_leave_requests_post': RetailLeaveRequestItem;
  'patch_leave_request_api_hr_leave_requests__request_id__patch': RetailLeaveRequestItem;
  'get_manager_overview_api_hr_manager_overview_get': Array<RetailHrManagerOverviewItem>;
  'get_performance_api_hr_performance__agent_name__get': Array<RetailHrAgentPerformanceItem>;
  'reconcile_erp_report_file_api_import_erp_reconciliation_post': RetailImportJobStatus;
  'get_import_history_api_import_history_get': Array<RetailImportHistoryEntry>;
  'get_import_job_status_api_import_jobs__job_id__get': RetailImportJobStatus;
  'upload_promo_actuals_file_api_import_promo_actuals_post': RetailImportJobStatus;
  'upload_sales_file_api_import_sales_post': RetailImportJobStatus;
  'promote_sales_generation_api_import_sales__snapshot_id__promote_post': RetailImportJobStatus;
  'annual_api_store_pnl_annual_get': RetailPnlAnnualResponse;
  'months_api_store_pnl_months_get': RetailPnlMonthsResponse;
  'overview_api_store_pnl_overview_get': RetailPnlOverviewResponse;
  'pnl_permissions_api_store_pnl_permissions_get': RetailPnlPermissionsResponse;
  'regions_api_store_pnl_regions_get': RetailPnlRegionsResponse;
  'stores_api_store_pnl_stores_get': RetailPnlStoresResponse;
  'list_stores_api_stores_get': Array<RetailStoreOption>;
  'save_targets_api_stores_targets_post': RetailStoreTargetsSaveResponse;
  'change_store_activity_api_stores__site_code__activity_post': RetailStoreActivityChangeResponse;
  'get_context_api_target_calculator_context_get': RetailTargetContextResponse;
  'list_scenarios_api_target_calculator_scenarios_get': Array<RetailTargetScenarioSummaryResponse>;
  'calculate_scenario_api_target_calculator_scenarios_calculate_post': RetailTargetScenarioResponse;
  'get_scenario_api_target_calculator_scenarios__scenario_id__get': RetailTargetScenarioResponse;
  'export_scenario_api_target_calculator_scenarios__scenario_id__export_get': Blob;
  'finalize_scenario_api_target_calculator_scenarios__scenario_id__finalize_post': RetailTargetScenarioResponse;
  'update_final_targets_api_target_calculator_scenarios__scenario_id__rows_patch': RetailTargetScenarioResponse;
  'get_store_detail_api_target_calculator_scenarios__scenario_id__stores__site_code__get': RetailTargetStoreDetailResponse;
  'get_tasks_api_tasks_get': RetailTaskListResponse;
  'post_task_api_tasks_post': RetailTaskItem;
  'remove_task_api_tasks__task_id__delete': RetailTaskDeleteResponse;
  'patch_task_api_tasks__task_id__patch': RetailTaskItem;
  'get_visits_report_api_visits_report_get': RetailVisitReportResponse;
  'get_visit_photo_api_visits_report_photo__visit_id___filename__get': Blob;
  'get_visits_tree_api_visits_report_tree_get': RetailVisitTreeResponse;
  'get_visit_detail_api_visits_report_visit__visit_id__get': RetailVisitDetail;
  'session_status_auth_session_get': RetailSessionStatusResponse;
  'session_login_auth_session_login_get': unknown;
  'session_logout_auth_session_logout_post': RetailSessionLogoutResponse;
  'metrics_metrics_get': unknown;
  'agent_history_by_retail_code_salarii_agents_history_by_retail_code_get': RetailSalaryHistoryResponse;
  'agents_summary_salarii_agents_summary_get': RetailSalaryAgentsSummaryResponse;
  'agent_history_salarii_agents__person_id__history_get': RetailSalaryHistoryResponse;
  'audit_salary_export_salarii_audit_export_post': void;
  'salarii_evolution_salarii_evolution_get': Array<RetailSalaryEvolutionPoint>;
  'salarii_overview_salarii_overview_get': RetailSalaryOverviewResponse;
  'list_records_salarii_records_get': Array<RetailSalaryRecordPublic>;
  'salarii_stores_salarii_stores_get': Array<RetailSalaryStoreOption>;
  'salarii_summary_salarii_summary_get': RetailSalarySummaryResponse;
  'salarii_trend_salarii_trend_get': Array<RetailSalaryTrendPoint>;
}

export interface RetailOperationErrors {
  'get_agent_evaluation_api_agents_evaluation_get': { '422': RetailHTTPValidationError };
  'get_agent_evaluation_v2_api_agents_evaluation_v2_get': { '422': RetailHTTPValidationError };
  'get_agent_history_api_agents_history_get': { '422': RetailHTTPValidationError };
  'get_agents_list_api_agents_list_get': { '422': RetailHTTPValidationError };
  'get_agents_movement_api_agents_movement_get': { '422': RetailHTTPValidationError };
  'get_agents_overview_api_agents_overview_get': { '422': RetailHTTPValidationError };
  'get_agent_profile_api_agents_profile_get': { '422': RetailHTTPValidationError };
  'get_stores_coverage_api_agents_stores_coverage_get': { '422': RetailHTTPValidationError };
  'get_current_ai_forecast_api_ai_forecast_current_get': { '422': RetailHTTPValidationError };
  'get_rolling_12_ai_forecast_api_ai_forecast_rolling_12_get': { '422': RetailHTTPValidationError };
  'get_focus_history_api_campaigns_history_get': { '422': RetailHTTPValidationError };
  'get_campaign_overview_api_campaigns_overview_get': { '422': RetailHTTPValidationError };
  'get_promotions_incentives_api_campaigns_promotions_incentives_get': { '422': RetailHTTPValidationError };
  'get_active_contest_api_contests_active_get': { '422': RetailHTTPValidationError };
  'get_active_contests_api_contests_active_all_get': { '422': RetailHTTPValidationError };
  'get_alerts_api_crm_alerts_get': { '422': RetailHTTPValidationError };
  'get_scores_api_crm_scores_get': { '422': RetailHTTPValidationError };
  'recalculate_scores_api_crm_scores_recalculate_post': { '422': RetailHTTPValidationError };
  'get_dashboard_all_api_dashboard_all_get': { '422': RetailHTTPValidationError };
  'get_dashboard_all_batch_api_dashboard_all_batch_post': { '422': RetailHTTPValidationError };
  'get_daily_sales_api_dashboard_daily_get': { '422': RetailHTTPValidationError };
  'get_monthly_history_api_dashboard_history_get': { '422': RetailHTTPValidationError };
  'get_dashboard_history_details_batch_api_dashboard_history_details_batch_post': { '422': RetailHTTPValidationError };
  'get_history_by_year_api_dashboard_history_year_get': { '422': RetailHTTPValidationError };
  'get_performance_detail_api_dashboard_performance_detail_get': { '422': RetailHTTPValidationError };
  'get_premium_glass_api_dashboard_premium_glass_get': { '422': RetailHTTPValidationError };
  'get_special_cards_api_dashboard_special_cards_get': { '422': RetailHTTPValidationError };
  'get_summary_api_dashboard_summary_get': { '422': RetailHTTPValidationError };
  'get_catalog_api_exports_catalog_get': Record<never, never>;
  'download_export_api_exports_download_post': { '422': RetailHTTPValidationError };
  'create_export_operation_api_exports_operations_post': { '400': void; '409': void; '422': RetailHTTPValidationError; '503': RetailExportOperationUnavailableResponse };
  'get_resumable_export_operation_api_exports_operations_resumable_get': Record<never, never>;
  'get_export_operation_api_exports_operations__operation_id__get': { '404': void; '422': RetailHTTPValidationError };
  'cancel_export_operation_api_exports_operations__operation_id__cancel_post': { '404': void; '409': void; '422': RetailHTTPValidationError };
  'download_export_operation_api_exports_operations__operation_id__download_get': { '404': void; '409': void; '410': void; '422': RetailHTTPValidationError };
  'preview_export_api_exports_preview_post': { '422': RetailHTTPValidationError };
  'get_available_months_api_filters_months_get': Record<never, never>;
  'get_filter_options_api_filters_options_get': { '422': RetailHTTPValidationError };
  'grile_agent_targets_diff_api_grile_agent_targets_diff_post': { '422': RetailHTTPValidationError };
  'grile_agent_targets_operation_api_grile_agent_targets_operations__operation_id__get': { '422': RetailHTTPValidationError };
  'grile_agent_targets_sync_api_grile_agent_targets_sync_post': { '422': RetailHTTPValidationError };
  'grile_monthly_download_api_grile_monthly_download__kind___month__get': { '422': RetailHTTPValidationError };
  'grile_monthly_job_api_grile_monthly_job__job_id__get': { '422': RetailHTTPValidationError };
  'grile_monthly_manifest_approve_api_grile_monthly_manifests__manifest_id__approve_post': { '422': RetailHTTPValidationError };
  'grile_monthly_manifest_api_grile_monthly_manifests__month__get': { '422': RetailHTTPValidationError };
  'grile_monthly_permissions_api_grile_monthly_permissions_get': Record<never, never>;
  'grile_monthly_run_api_grile_monthly_run_post': { '422': RetailHTTPValidationError };
  'grile_overview_api_grile_overview_get': { '422': RetailHTTPValidationError };
  'grile_run_api_grile_run_post': { '422': RetailHTTPValidationError };
  'grile_run_status_api_grile_run_status_get': { '422': RetailHTTPValidationError };
  'grile_store_refresh_operation_api_grile_store_refreshes__operation_id__get': { '422': RetailHTTPValidationError };
  'grile_store_refresh_api_grile_stores__site_code__refresh_post': { '422': RetailHTTPValidationError };
  'get_asm_perf_api_hr_asm_performance_get': { '422': RetailHTTPValidationError };
  'get_asm_perf_history_api_hr_asm_performance__asm_name__history_get': { '422': RetailHTTPValidationError };
  'get_asm_salary_api_hr_asm_salary__asm_name__get': { '422': RetailHTTPValidationError };
  'get_leave_requests_api_hr_leave_requests_get': { '422': RetailHTTPValidationError };
  'post_leave_request_api_hr_leave_requests_post': { '422': RetailHTTPValidationError };
  'patch_leave_request_api_hr_leave_requests__request_id__patch': { '422': RetailHTTPValidationError };
  'get_manager_overview_api_hr_manager_overview_get': { '422': RetailHTTPValidationError };
  'get_performance_api_hr_performance__agent_name__get': { '422': RetailHTTPValidationError };
  'reconcile_erp_report_file_api_import_erp_reconciliation_post': { '422': RetailHTTPValidationError };
  'get_import_history_api_import_history_get': Record<never, never>;
  'get_import_job_status_api_import_jobs__job_id__get': { '422': RetailHTTPValidationError };
  'upload_promo_actuals_file_api_import_promo_actuals_post': { '422': RetailHTTPValidationError };
  'upload_sales_file_api_import_sales_post': { '422': RetailHTTPValidationError };
  'promote_sales_generation_api_import_sales__snapshot_id__promote_post': { '422': RetailHTTPValidationError };
  'annual_api_store_pnl_annual_get': { '422': RetailHTTPValidationError };
  'months_api_store_pnl_months_get': Record<never, never>;
  'overview_api_store_pnl_overview_get': { '422': RetailHTTPValidationError };
  'pnl_permissions_api_store_pnl_permissions_get': Record<never, never>;
  'regions_api_store_pnl_regions_get': { '422': RetailHTTPValidationError };
  'stores_api_store_pnl_stores_get': { '422': RetailHTTPValidationError };
  'list_stores_api_stores_get': Record<never, never>;
  'save_targets_api_stores_targets_post': { '422': RetailHTTPValidationError };
  'change_store_activity_api_stores__site_code__activity_post': { '422': RetailHTTPValidationError };
  'get_context_api_target_calculator_context_get': { '404': RetailTargetApiErrorResponse };
  'list_scenarios_api_target_calculator_scenarios_get': Record<never, never>;
  'calculate_scenario_api_target_calculator_scenarios_calculate_post': { '400': RetailTargetApiErrorResponse; '409': RetailTargetApiErrorResponse; '422': RetailHTTPValidationError };
  'get_scenario_api_target_calculator_scenarios__scenario_id__get': { '404': RetailTargetApiErrorResponse; '409': RetailTargetApiErrorResponse; '422': RetailHTTPValidationError };
  'export_scenario_api_target_calculator_scenarios__scenario_id__export_get': { '404': RetailTargetApiErrorResponse; '409': RetailTargetApiErrorResponse; '422': RetailHTTPValidationError };
  'finalize_scenario_api_target_calculator_scenarios__scenario_id__finalize_post': { '400': RetailTargetApiErrorResponse; '404': RetailTargetApiErrorResponse; '409': RetailTargetApiErrorResponse; '422': RetailHTTPValidationError };
  'update_final_targets_api_target_calculator_scenarios__scenario_id__rows_patch': { '400': RetailTargetApiErrorResponse; '404': RetailTargetApiErrorResponse; '409': RetailTargetApiErrorResponse; '422': RetailHTTPValidationError };
  'get_store_detail_api_target_calculator_scenarios__scenario_id__stores__site_code__get': { '404': RetailTargetApiErrorResponse; '422': RetailHTTPValidationError };
  'get_tasks_api_tasks_get': { '422': RetailHTTPValidationError };
  'post_task_api_tasks_post': { '422': RetailHTTPValidationError };
  'remove_task_api_tasks__task_id__delete': { '422': RetailHTTPValidationError };
  'patch_task_api_tasks__task_id__patch': { '422': RetailHTTPValidationError };
  'get_visits_report_api_visits_report_get': { '422': RetailHTTPValidationError };
  'get_visit_photo_api_visits_report_photo__visit_id___filename__get': { '422': RetailHTTPValidationError };
  'get_visits_tree_api_visits_report_tree_get': { '422': RetailHTTPValidationError };
  'get_visit_detail_api_visits_report_visit__visit_id__get': { '422': RetailHTTPValidationError };
  'session_status_auth_session_get': Record<never, never>;
  'session_login_auth_session_login_get': Record<never, never>;
  'session_logout_auth_session_logout_post': Record<never, never>;
  'metrics_metrics_get': Record<never, never>;
  'agent_history_by_retail_code_salarii_agents_history_by_retail_code_get': { '422': RetailHTTPValidationError };
  'agents_summary_salarii_agents_summary_get': { '422': RetailHTTPValidationError };
  'agent_history_salarii_agents__person_id__history_get': { '422': RetailHTTPValidationError };
  'audit_salary_export_salarii_audit_export_post': { '422': RetailHTTPValidationError };
  'salarii_evolution_salarii_evolution_get': { '422': RetailHTTPValidationError };
  'salarii_overview_salarii_overview_get': { '422': RetailHTTPValidationError };
  'list_records_salarii_records_get': { '422': RetailHTTPValidationError };
  'salarii_stores_salarii_stores_get': { '422': RetailHTTPValidationError };
  'salarii_summary_salarii_summary_get': { '422': RetailHTTPValidationError };
  'salarii_trend_salarii_trend_get': { '422': RetailHTTPValidationError };
}

export const RETAIL_OPERATION_ERROR_STATUSES: { readonly [Id in RetailOperationId]: ReadonlySet<string> } = {
  'get_agent_evaluation_api_agents_evaluation_get': new Set<string>([
    '422',
  ]),
  'get_agent_evaluation_v2_api_agents_evaluation_v2_get': new Set<string>([
    '422',
  ]),
  'get_agent_history_api_agents_history_get': new Set<string>([
    '422',
  ]),
  'get_agents_list_api_agents_list_get': new Set<string>([
    '422',
  ]),
  'get_agents_movement_api_agents_movement_get': new Set<string>([
    '422',
  ]),
  'get_agents_overview_api_agents_overview_get': new Set<string>([
    '422',
  ]),
  'get_agent_profile_api_agents_profile_get': new Set<string>([
    '422',
  ]),
  'get_stores_coverage_api_agents_stores_coverage_get': new Set<string>([
    '422',
  ]),
  'get_current_ai_forecast_api_ai_forecast_current_get': new Set<string>([
    '422',
  ]),
  'get_rolling_12_ai_forecast_api_ai_forecast_rolling_12_get': new Set<string>([
    '422',
  ]),
  'get_focus_history_api_campaigns_history_get': new Set<string>([
    '422',
  ]),
  'get_campaign_overview_api_campaigns_overview_get': new Set<string>([
    '422',
  ]),
  'get_promotions_incentives_api_campaigns_promotions_incentives_get': new Set<string>([
    '422',
  ]),
  'get_active_contest_api_contests_active_get': new Set<string>([
    '422',
  ]),
  'get_active_contests_api_contests_active_all_get': new Set<string>([
    '422',
  ]),
  'get_alerts_api_crm_alerts_get': new Set<string>([
    '422',
  ]),
  'get_scores_api_crm_scores_get': new Set<string>([
    '422',
  ]),
  'recalculate_scores_api_crm_scores_recalculate_post': new Set<string>([
    '422',
  ]),
  'get_dashboard_all_api_dashboard_all_get': new Set<string>([
    '422',
  ]),
  'get_dashboard_all_batch_api_dashboard_all_batch_post': new Set<string>([
    '422',
  ]),
  'get_daily_sales_api_dashboard_daily_get': new Set<string>([
    '422',
  ]),
  'get_monthly_history_api_dashboard_history_get': new Set<string>([
    '422',
  ]),
  'get_dashboard_history_details_batch_api_dashboard_history_details_batch_post': new Set<string>([
    '422',
  ]),
  'get_history_by_year_api_dashboard_history_year_get': new Set<string>([
    '422',
  ]),
  'get_performance_detail_api_dashboard_performance_detail_get': new Set<string>([
    '422',
  ]),
  'get_premium_glass_api_dashboard_premium_glass_get': new Set<string>([
    '422',
  ]),
  'get_special_cards_api_dashboard_special_cards_get': new Set<string>([
    '422',
  ]),
  'get_summary_api_dashboard_summary_get': new Set<string>([
    '422',
  ]),
  'get_catalog_api_exports_catalog_get': new Set<string>([
  ]),
  'download_export_api_exports_download_post': new Set<string>([
    '422',
  ]),
  'create_export_operation_api_exports_operations_post': new Set<string>([
    '400',
    '409',
    '422',
    '503',
  ]),
  'get_resumable_export_operation_api_exports_operations_resumable_get': new Set<string>([
  ]),
  'get_export_operation_api_exports_operations__operation_id__get': new Set<string>([
    '404',
    '422',
  ]),
  'cancel_export_operation_api_exports_operations__operation_id__cancel_post': new Set<string>([
    '404',
    '409',
    '422',
  ]),
  'download_export_operation_api_exports_operations__operation_id__download_get': new Set<string>([
    '404',
    '409',
    '410',
    '422',
  ]),
  'preview_export_api_exports_preview_post': new Set<string>([
    '422',
  ]),
  'get_available_months_api_filters_months_get': new Set<string>([
  ]),
  'get_filter_options_api_filters_options_get': new Set<string>([
    '422',
  ]),
  'grile_agent_targets_diff_api_grile_agent_targets_diff_post': new Set<string>([
    '422',
  ]),
  'grile_agent_targets_operation_api_grile_agent_targets_operations__operation_id__get': new Set<string>([
    '422',
  ]),
  'grile_agent_targets_sync_api_grile_agent_targets_sync_post': new Set<string>([
    '422',
  ]),
  'grile_monthly_download_api_grile_monthly_download__kind___month__get': new Set<string>([
    '422',
  ]),
  'grile_monthly_job_api_grile_monthly_job__job_id__get': new Set<string>([
    '422',
  ]),
  'grile_monthly_manifest_approve_api_grile_monthly_manifests__manifest_id__approve_post': new Set<string>([
    '422',
  ]),
  'grile_monthly_manifest_api_grile_monthly_manifests__month__get': new Set<string>([
    '422',
  ]),
  'grile_monthly_permissions_api_grile_monthly_permissions_get': new Set<string>([
  ]),
  'grile_monthly_run_api_grile_monthly_run_post': new Set<string>([
    '422',
  ]),
  'grile_overview_api_grile_overview_get': new Set<string>([
    '422',
  ]),
  'grile_run_api_grile_run_post': new Set<string>([
    '422',
  ]),
  'grile_run_status_api_grile_run_status_get': new Set<string>([
    '422',
  ]),
  'grile_store_refresh_operation_api_grile_store_refreshes__operation_id__get': new Set<string>([
    '422',
  ]),
  'grile_store_refresh_api_grile_stores__site_code__refresh_post': new Set<string>([
    '422',
  ]),
  'get_asm_perf_api_hr_asm_performance_get': new Set<string>([
    '422',
  ]),
  'get_asm_perf_history_api_hr_asm_performance__asm_name__history_get': new Set<string>([
    '422',
  ]),
  'get_asm_salary_api_hr_asm_salary__asm_name__get': new Set<string>([
    '422',
  ]),
  'get_leave_requests_api_hr_leave_requests_get': new Set<string>([
    '422',
  ]),
  'post_leave_request_api_hr_leave_requests_post': new Set<string>([
    '422',
  ]),
  'patch_leave_request_api_hr_leave_requests__request_id__patch': new Set<string>([
    '422',
  ]),
  'get_manager_overview_api_hr_manager_overview_get': new Set<string>([
    '422',
  ]),
  'get_performance_api_hr_performance__agent_name__get': new Set<string>([
    '422',
  ]),
  'reconcile_erp_report_file_api_import_erp_reconciliation_post': new Set<string>([
    '422',
  ]),
  'get_import_history_api_import_history_get': new Set<string>([
  ]),
  'get_import_job_status_api_import_jobs__job_id__get': new Set<string>([
    '422',
  ]),
  'upload_promo_actuals_file_api_import_promo_actuals_post': new Set<string>([
    '422',
  ]),
  'upload_sales_file_api_import_sales_post': new Set<string>([
    '422',
  ]),
  'promote_sales_generation_api_import_sales__snapshot_id__promote_post': new Set<string>([
    '422',
  ]),
  'annual_api_store_pnl_annual_get': new Set<string>([
    '422',
  ]),
  'months_api_store_pnl_months_get': new Set<string>([
  ]),
  'overview_api_store_pnl_overview_get': new Set<string>([
    '422',
  ]),
  'pnl_permissions_api_store_pnl_permissions_get': new Set<string>([
  ]),
  'regions_api_store_pnl_regions_get': new Set<string>([
    '422',
  ]),
  'stores_api_store_pnl_stores_get': new Set<string>([
    '422',
  ]),
  'list_stores_api_stores_get': new Set<string>([
  ]),
  'save_targets_api_stores_targets_post': new Set<string>([
    '422',
  ]),
  'change_store_activity_api_stores__site_code__activity_post': new Set<string>([
    '422',
  ]),
  'get_context_api_target_calculator_context_get': new Set<string>([
    '404',
  ]),
  'list_scenarios_api_target_calculator_scenarios_get': new Set<string>([
  ]),
  'calculate_scenario_api_target_calculator_scenarios_calculate_post': new Set<string>([
    '400',
    '409',
    '422',
  ]),
  'get_scenario_api_target_calculator_scenarios__scenario_id__get': new Set<string>([
    '404',
    '409',
    '422',
  ]),
  'export_scenario_api_target_calculator_scenarios__scenario_id__export_get': new Set<string>([
    '404',
    '409',
    '422',
  ]),
  'finalize_scenario_api_target_calculator_scenarios__scenario_id__finalize_post': new Set<string>([
    '400',
    '404',
    '409',
    '422',
  ]),
  'update_final_targets_api_target_calculator_scenarios__scenario_id__rows_patch': new Set<string>([
    '400',
    '404',
    '409',
    '422',
  ]),
  'get_store_detail_api_target_calculator_scenarios__scenario_id__stores__site_code__get': new Set<string>([
    '404',
    '422',
  ]),
  'get_tasks_api_tasks_get': new Set<string>([
    '422',
  ]),
  'post_task_api_tasks_post': new Set<string>([
    '422',
  ]),
  'remove_task_api_tasks__task_id__delete': new Set<string>([
    '422',
  ]),
  'patch_task_api_tasks__task_id__patch': new Set<string>([
    '422',
  ]),
  'get_visits_report_api_visits_report_get': new Set<string>([
    '422',
  ]),
  'get_visit_photo_api_visits_report_photo__visit_id___filename__get': new Set<string>([
    '422',
  ]),
  'get_visits_tree_api_visits_report_tree_get': new Set<string>([
    '422',
  ]),
  'get_visit_detail_api_visits_report_visit__visit_id__get': new Set<string>([
    '422',
  ]),
  'session_status_auth_session_get': new Set<string>([
  ]),
  'session_login_auth_session_login_get': new Set<string>([
  ]),
  'session_logout_auth_session_logout_post': new Set<string>([
  ]),
  'metrics_metrics_get': new Set<string>([
  ]),
  'agent_history_by_retail_code_salarii_agents_history_by_retail_code_get': new Set<string>([
    '422',
  ]),
  'agents_summary_salarii_agents_summary_get': new Set<string>([
    '422',
  ]),
  'agent_history_salarii_agents__person_id__history_get': new Set<string>([
    '422',
  ]),
  'audit_salary_export_salarii_audit_export_post': new Set<string>([
    '422',
  ]),
  'salarii_evolution_salarii_evolution_get': new Set<string>([
    '422',
  ]),
  'salarii_overview_salarii_overview_get': new Set<string>([
    '422',
  ]),
  'list_records_salarii_records_get': new Set<string>([
    '422',
  ]),
  'salarii_stores_salarii_stores_get': new Set<string>([
    '422',
  ]),
  'salarii_summary_salarii_summary_get': new Set<string>([
    '422',
  ]),
  'salarii_trend_salarii_trend_get': new Set<string>([
    '422',
  ]),
};

export interface RetailOperationQueries {
  'get_agent_evaluation_api_agents_evaluation_get': { "month"?: string | null; "months"?: string | null; "firma"?: string | null; "asm"?: string | null; "site_code"?: string | null };
  'get_agent_evaluation_v2_api_agents_evaluation_v2_get': { "month"?: string | null; "months"?: string | null; "firma"?: string | null; "asm"?: string | null; "site_code"?: string | null };
  'get_agent_history_api_agents_history_get': { "agent": string };
  'get_agents_list_api_agents_list_get': { "selected_month": string; "search"?: string | null; "firma"?: string | null; "regional"?: string | null; "asm"?: string | null; "site_code"?: string | null };
  'get_agents_movement_api_agents_movement_get': { "selected_month": string; "firma"?: string | null; "regional"?: string | null; "asm"?: string | null; "site_code"?: string | null; "agent"?: string | null };
  'get_agents_overview_api_agents_overview_get': { "selected_month": string; "firma"?: string | null; "regional"?: string | null; "asm"?: string | null; "site_code"?: string | null; "agent"?: string | null };
  'get_agent_profile_api_agents_profile_get': { "agent": string; "selected_month": string };
  'get_stores_coverage_api_agents_stores_coverage_get': { "selected_month": string; "firma"?: string | null; "regional"?: string | null; "asm"?: string | null };
  'get_current_ai_forecast_api_ai_forecast_current_get': { "month": string; "metric"?: string; "firma"?: string | null; "regional"?: string | null; "asm"?: string | null; "site_code"?: string | null };
  'get_rolling_12_ai_forecast_api_ai_forecast_rolling_12_get': { "month": string; "metric"?: string; "firma"?: string | null; "regional"?: string | null; "asm"?: string | null; "site_code"?: string | null };
  'get_focus_history_api_campaigns_history_get': { "month": string; "months_back"?: number; "firma"?: string | null; "regional"?: string | null; "asm"?: string | null; "site_code"?: string | null; "agent"?: string | null };
  'get_campaign_overview_api_campaigns_overview_get': { "month": string; "firma"?: string | null; "regional"?: string | null; "asm"?: string | null; "site_code"?: string | null; "agent"?: string | null };
  'get_promotions_incentives_api_campaigns_promotions_incentives_get': { "start_date": string; "end_date": string; "firma"?: string | null; "regional"?: string | null; "asm"?: string | null; "site_code"?: string | null; "agent"?: string | null; "promotion_key"?: string | null; "view"?: "all" | "promo" | "incentive"; "current_scope"?: boolean; "include_closed_stores"?: boolean };
  'get_active_contest_api_contests_active_get': { "month": string; "site_codes"?: string | null };
  'get_active_contests_api_contests_active_all_get': { "month": string; "site_codes"?: string | null };
  'get_alerts_api_crm_alerts_get': { "month": string };
  'get_scores_api_crm_scores_get': { "month": string };
  'recalculate_scores_api_crm_scores_recalculate_post': { "month": string };
  'get_dashboard_all_api_dashboard_all_get': { "month": string; "firma"?: string | null; "regional"?: string | null; "asm"?: string | null; "site_code"?: string | null; "agent"?: string | null; "current_scope"?: boolean; "include_closed_stores"?: boolean };
  'get_dashboard_all_batch_api_dashboard_all_batch_post': Record<never, never>;
  'get_daily_sales_api_dashboard_daily_get': { "month": string; "firma"?: string | null; "regional"?: string | null; "asm"?: string | null; "site_code"?: string | null; "agent"?: string | null };
  'get_monthly_history_api_dashboard_history_get': { "month": string; "months_back"?: number; "firma"?: string | null; "regional"?: string | null; "asm"?: string | null; "site_code"?: string | null; "agent"?: string | null; "current_scope"?: boolean; "include_closed_stores"?: boolean };
  'get_dashboard_history_details_batch_api_dashboard_history_details_batch_post': Record<never, never>;
  'get_history_by_year_api_dashboard_history_year_get': { "year": number; "firma"?: string | null; "regional"?: string | null; "asm"?: string | null; "site_code"?: string | null; "agent"?: string | null; "current_scope"?: boolean; "include_closed_stores"?: boolean };
  'get_performance_detail_api_dashboard_performance_detail_get': { "month": string; "level": "regional" | "store" | "agent"; "key": string; "firma"?: string | null; "regional"?: string | null; "asm"?: string | null; "site_code"?: string | null; "agent"?: string | null; "current_scope"?: boolean; "include_closed_stores"?: boolean };
  'get_premium_glass_api_dashboard_premium_glass_get': { "month": string; "firma"?: string | null; "regional"?: string | null; "asm"?: string | null; "site_code"?: string | null; "agent"?: string | null; "surface"?: "all" | "screen" | "camera"; "current_scope"?: boolean; "include_closed_stores"?: boolean };
  'get_special_cards_api_dashboard_special_cards_get': { "month": string; "firma"?: string | null; "regional"?: string | null; "asm"?: string | null; "site_code"?: string | null; "agent"?: string | null };
  'get_summary_api_dashboard_summary_get': { "month": string; "firma"?: string | null; "regional"?: string | null; "asm"?: string | null; "site_code"?: string | null; "agent"?: string | null };
  'get_catalog_api_exports_catalog_get': Record<never, never>;
  'download_export_api_exports_download_post': Record<never, never>;
  'create_export_operation_api_exports_operations_post': Record<never, never>;
  'get_resumable_export_operation_api_exports_operations_resumable_get': Record<never, never>;
  'get_export_operation_api_exports_operations__operation_id__get': Record<never, never>;
  'cancel_export_operation_api_exports_operations__operation_id__cancel_post': Record<never, never>;
  'download_export_operation_api_exports_operations__operation_id__download_get': Record<never, never>;
  'preview_export_api_exports_preview_post': Record<never, never>;
  'get_available_months_api_filters_months_get': Record<never, never>;
  'get_filter_options_api_filters_options_get': { "month": string };
  'grile_agent_targets_diff_api_grile_agent_targets_diff_post': Record<never, never>;
  'grile_agent_targets_operation_api_grile_agent_targets_operations__operation_id__get': Record<never, never>;
  'grile_agent_targets_sync_api_grile_agent_targets_sync_post': Record<never, never>;
  'grile_monthly_download_api_grile_monthly_download__kind___month__get': Record<never, never>;
  'grile_monthly_job_api_grile_monthly_job__job_id__get': Record<never, never>;
  'grile_monthly_manifest_approve_api_grile_monthly_manifests__manifest_id__approve_post': Record<never, never>;
  'grile_monthly_manifest_api_grile_monthly_manifests__month__get': Record<never, never>;
  'grile_monthly_permissions_api_grile_monthly_permissions_get': Record<never, never>;
  'grile_monthly_run_api_grile_monthly_run_post': Record<never, never>;
  'grile_overview_api_grile_overview_get': { "month"?: string | null };
  'grile_run_api_grile_run_post': { "month"?: string | null };
  'grile_run_status_api_grile_run_status_get': { "month"?: string | null };
  'grile_store_refresh_operation_api_grile_store_refreshes__operation_id__get': Record<never, never>;
  'grile_store_refresh_api_grile_stores__site_code__refresh_post': { "month"?: string | null };
  'get_asm_perf_api_hr_asm_performance_get': { "month": string; "regional"?: string | null };
  'get_asm_perf_history_api_hr_asm_performance__asm_name__history_get': { "months"?: number };
  'get_asm_salary_api_hr_asm_salary__asm_name__get': { "month": string };
  'get_leave_requests_api_hr_leave_requests_get': { "status"?: string | null; "agent_name"?: string | null; "limit"?: number; "offset"?: number };
  'post_leave_request_api_hr_leave_requests_post': Record<never, never>;
  'patch_leave_request_api_hr_leave_requests__request_id__patch': Record<never, never>;
  'get_manager_overview_api_hr_manager_overview_get': { "month": string };
  'get_performance_api_hr_performance__agent_name__get': Record<never, never>;
  'reconcile_erp_report_file_api_import_erp_reconciliation_post': Record<never, never>;
  'get_import_history_api_import_history_get': Record<never, never>;
  'get_import_job_status_api_import_jobs__job_id__get': Record<never, never>;
  'upload_promo_actuals_file_api_import_promo_actuals_post': Record<never, never>;
  'upload_sales_file_api_import_sales_post': Record<never, never>;
  'promote_sales_generation_api_import_sales__snapshot_id__promote_post': Record<never, never>;
  'annual_api_store_pnl_annual_get': { "company"?: string | null; "site_code"?: string | null; "site_company"?: string | null; "regional"?: string | null };
  'months_api_store_pnl_months_get': Record<never, never>;
  'overview_api_store_pnl_overview_get': { "start_month": string; "end_month": string; "company"?: string | null; "site_code"?: string | null; "site_company"?: string | null; "regional"?: string | null };
  'pnl_permissions_api_store_pnl_permissions_get': Record<never, never>;
  'regions_api_store_pnl_regions_get': { "company"?: string | null };
  'stores_api_store_pnl_stores_get': { "company"?: string | null; "regional"?: string | null };
  'list_stores_api_stores_get': Record<never, never>;
  'save_targets_api_stores_targets_post': Record<never, never>;
  'change_store_activity_api_stores__site_code__activity_post': Record<never, never>;
  'get_context_api_target_calculator_context_get': Record<never, never>;
  'list_scenarios_api_target_calculator_scenarios_get': Record<never, never>;
  'calculate_scenario_api_target_calculator_scenarios_calculate_post': Record<never, never>;
  'get_scenario_api_target_calculator_scenarios__scenario_id__get': Record<never, never>;
  'export_scenario_api_target_calculator_scenarios__scenario_id__export_get': Record<never, never>;
  'finalize_scenario_api_target_calculator_scenarios__scenario_id__finalize_post': Record<never, never>;
  'update_final_targets_api_target_calculator_scenarios__scenario_id__rows_patch': Record<never, never>;
  'get_store_detail_api_target_calculator_scenarios__scenario_id__stores__site_code__get': Record<never, never>;
  'get_tasks_api_tasks_get': { "status"?: string | null; "assignee"?: string | null; "site_code"?: string | null; "limit"?: number; "offset"?: number };
  'post_task_api_tasks_post': Record<never, never>;
  'remove_task_api_tasks__task_id__delete': Record<never, never>;
  'patch_task_api_tasks__task_id__patch': Record<never, never>;
  'get_visits_report_api_visits_report_get': { "month": string; "firma"?: string | null; "rm"?: string | null; "asm"?: string | null; "magazin"?: string | null };
  'get_visit_photo_api_visits_report_photo__visit_id___filename__get': Record<never, never>;
  'get_visits_tree_api_visits_report_tree_get': { "month": string; "firma"?: string | null; "rm"?: string | null; "asm"?: string | null; "magazin"?: string | null };
  'get_visit_detail_api_visits_report_visit__visit_id__get': Record<never, never>;
  'session_status_auth_session_get': Record<never, never>;
  'session_login_auth_session_login_get': Record<never, never>;
  'session_logout_auth_session_logout_post': Record<never, never>;
  'metrics_metrics_get': Record<never, never>;
  'agent_history_by_retail_code_salarii_agents_history_by_retail_code_get': { "agent_code": string; "site_code": string };
  'agents_summary_salarii_agents_summary_get': { "q"?: string | null; "company_name"?: string | null; "site_code"?: string | null; "regional"?: string | null; "asm"?: string | null; "year"?: number | null; "month"?: number | null; "limit"?: number; "offset"?: number };
  'agent_history_salarii_agents__person_id__history_get': Record<never, never>;
  'audit_salary_export_salarii_audit_export_post': Record<never, never>;
  'salarii_evolution_salarii_evolution_get': { "company_name"?: string | null; "site_code"?: string | null; "regional"?: string | null; "asm"?: string | null };
  'salarii_overview_salarii_overview_get': { "company_name"?: string | null; "site_code"?: string | null; "regional"?: string | null; "asm"?: string | null };
  'list_records_salarii_records_get': { "company_name"?: string | null; "year"?: number | null; "month"?: number | null; "site_code"?: string | null; "limit"?: number; "offset"?: number };
  'salarii_stores_salarii_stores_get': { "company_name"?: string | null };
  'salarii_summary_salarii_summary_get': { "company_name"?: string | null; "site_code"?: string | null; "regional"?: string | null; "asm"?: string | null; "year"?: number | null; "month"?: number | null };
  'salarii_trend_salarii_trend_get': { "company_name"?: string | null; "site_code"?: string | null; "regional"?: string | null; "asm"?: string | null };
}

export interface RetailOperationPaths {
  'get_agent_evaluation_api_agents_evaluation_get': Record<never, never>;
  'get_agent_evaluation_v2_api_agents_evaluation_v2_get': Record<never, never>;
  'get_agent_history_api_agents_history_get': Record<never, never>;
  'get_agents_list_api_agents_list_get': Record<never, never>;
  'get_agents_movement_api_agents_movement_get': Record<never, never>;
  'get_agents_overview_api_agents_overview_get': Record<never, never>;
  'get_agent_profile_api_agents_profile_get': Record<never, never>;
  'get_stores_coverage_api_agents_stores_coverage_get': Record<never, never>;
  'get_current_ai_forecast_api_ai_forecast_current_get': Record<never, never>;
  'get_rolling_12_ai_forecast_api_ai_forecast_rolling_12_get': Record<never, never>;
  'get_focus_history_api_campaigns_history_get': Record<never, never>;
  'get_campaign_overview_api_campaigns_overview_get': Record<never, never>;
  'get_promotions_incentives_api_campaigns_promotions_incentives_get': Record<never, never>;
  'get_active_contest_api_contests_active_get': Record<never, never>;
  'get_active_contests_api_contests_active_all_get': Record<never, never>;
  'get_alerts_api_crm_alerts_get': Record<never, never>;
  'get_scores_api_crm_scores_get': Record<never, never>;
  'recalculate_scores_api_crm_scores_recalculate_post': Record<never, never>;
  'get_dashboard_all_api_dashboard_all_get': Record<never, never>;
  'get_dashboard_all_batch_api_dashboard_all_batch_post': Record<never, never>;
  'get_daily_sales_api_dashboard_daily_get': Record<never, never>;
  'get_monthly_history_api_dashboard_history_get': Record<never, never>;
  'get_dashboard_history_details_batch_api_dashboard_history_details_batch_post': Record<never, never>;
  'get_history_by_year_api_dashboard_history_year_get': Record<never, never>;
  'get_performance_detail_api_dashboard_performance_detail_get': Record<never, never>;
  'get_premium_glass_api_dashboard_premium_glass_get': Record<never, never>;
  'get_special_cards_api_dashboard_special_cards_get': Record<never, never>;
  'get_summary_api_dashboard_summary_get': Record<never, never>;
  'get_catalog_api_exports_catalog_get': Record<never, never>;
  'download_export_api_exports_download_post': Record<never, never>;
  'create_export_operation_api_exports_operations_post': Record<never, never>;
  'get_resumable_export_operation_api_exports_operations_resumable_get': Record<never, never>;
  'get_export_operation_api_exports_operations__operation_id__get': { "operation_id": number };
  'cancel_export_operation_api_exports_operations__operation_id__cancel_post': { "operation_id": number };
  'download_export_operation_api_exports_operations__operation_id__download_get': { "operation_id": number };
  'preview_export_api_exports_preview_post': Record<never, never>;
  'get_available_months_api_filters_months_get': Record<never, never>;
  'get_filter_options_api_filters_options_get': Record<never, never>;
  'grile_agent_targets_diff_api_grile_agent_targets_diff_post': Record<never, never>;
  'grile_agent_targets_operation_api_grile_agent_targets_operations__operation_id__get': { "operation_id": number };
  'grile_agent_targets_sync_api_grile_agent_targets_sync_post': Record<never, never>;
  'grile_monthly_download_api_grile_monthly_download__kind___month__get': { "kind": "final" | "archive"; "month": string };
  'grile_monthly_job_api_grile_monthly_job__job_id__get': { "job_id": string };
  'grile_monthly_manifest_approve_api_grile_monthly_manifests__manifest_id__approve_post': { "manifest_id": number };
  'grile_monthly_manifest_api_grile_monthly_manifests__month__get': { "month": string };
  'grile_monthly_permissions_api_grile_monthly_permissions_get': Record<never, never>;
  'grile_monthly_run_api_grile_monthly_run_post': Record<never, never>;
  'grile_overview_api_grile_overview_get': Record<never, never>;
  'grile_run_api_grile_run_post': Record<never, never>;
  'grile_run_status_api_grile_run_status_get': Record<never, never>;
  'grile_store_refresh_operation_api_grile_store_refreshes__operation_id__get': { "operation_id": number };
  'grile_store_refresh_api_grile_stores__site_code__refresh_post': { "site_code": string };
  'get_asm_perf_api_hr_asm_performance_get': Record<never, never>;
  'get_asm_perf_history_api_hr_asm_performance__asm_name__history_get': { "asm_name": string };
  'get_asm_salary_api_hr_asm_salary__asm_name__get': { "asm_name": string };
  'get_leave_requests_api_hr_leave_requests_get': Record<never, never>;
  'post_leave_request_api_hr_leave_requests_post': Record<never, never>;
  'patch_leave_request_api_hr_leave_requests__request_id__patch': { "request_id": number };
  'get_manager_overview_api_hr_manager_overview_get': Record<never, never>;
  'get_performance_api_hr_performance__agent_name__get': { "agent_name": string };
  'reconcile_erp_report_file_api_import_erp_reconciliation_post': Record<never, never>;
  'get_import_history_api_import_history_get': Record<never, never>;
  'get_import_job_status_api_import_jobs__job_id__get': { "job_id": string };
  'upload_promo_actuals_file_api_import_promo_actuals_post': Record<never, never>;
  'upload_sales_file_api_import_sales_post': Record<never, never>;
  'promote_sales_generation_api_import_sales__snapshot_id__promote_post': { "snapshot_id": number };
  'annual_api_store_pnl_annual_get': Record<never, never>;
  'months_api_store_pnl_months_get': Record<never, never>;
  'overview_api_store_pnl_overview_get': Record<never, never>;
  'pnl_permissions_api_store_pnl_permissions_get': Record<never, never>;
  'regions_api_store_pnl_regions_get': Record<never, never>;
  'stores_api_store_pnl_stores_get': Record<never, never>;
  'list_stores_api_stores_get': Record<never, never>;
  'save_targets_api_stores_targets_post': Record<never, never>;
  'change_store_activity_api_stores__site_code__activity_post': { "site_code": string };
  'get_context_api_target_calculator_context_get': Record<never, never>;
  'list_scenarios_api_target_calculator_scenarios_get': Record<never, never>;
  'calculate_scenario_api_target_calculator_scenarios_calculate_post': Record<never, never>;
  'get_scenario_api_target_calculator_scenarios__scenario_id__get': { "scenario_id": number };
  'export_scenario_api_target_calculator_scenarios__scenario_id__export_get': { "scenario_id": number };
  'finalize_scenario_api_target_calculator_scenarios__scenario_id__finalize_post': { "scenario_id": number };
  'update_final_targets_api_target_calculator_scenarios__scenario_id__rows_patch': { "scenario_id": number };
  'get_store_detail_api_target_calculator_scenarios__scenario_id__stores__site_code__get': { "scenario_id": number; "site_code": string };
  'get_tasks_api_tasks_get': Record<never, never>;
  'post_task_api_tasks_post': Record<never, never>;
  'remove_task_api_tasks__task_id__delete': { "task_id": number };
  'patch_task_api_tasks__task_id__patch': { "task_id": number };
  'get_visits_report_api_visits_report_get': Record<never, never>;
  'get_visit_photo_api_visits_report_photo__visit_id___filename__get': { "visit_id": string; "filename": string };
  'get_visits_tree_api_visits_report_tree_get': Record<never, never>;
  'get_visit_detail_api_visits_report_visit__visit_id__get': { "visit_id": string };
  'session_status_auth_session_get': Record<never, never>;
  'session_login_auth_session_login_get': Record<never, never>;
  'session_logout_auth_session_logout_post': Record<never, never>;
  'metrics_metrics_get': Record<never, never>;
  'agent_history_by_retail_code_salarii_agents_history_by_retail_code_get': Record<never, never>;
  'agents_summary_salarii_agents_summary_get': Record<never, never>;
  'agent_history_salarii_agents__person_id__history_get': { "person_id": string };
  'audit_salary_export_salarii_audit_export_post': Record<never, never>;
  'salarii_evolution_salarii_evolution_get': Record<never, never>;
  'salarii_overview_salarii_overview_get': Record<never, never>;
  'list_records_salarii_records_get': Record<never, never>;
  'salarii_stores_salarii_stores_get': Record<never, never>;
  'salarii_summary_salarii_summary_get': Record<never, never>;
  'salarii_trend_salarii_trend_get': Record<never, never>;
}

export interface RetailOperationBodies {
  'get_agent_evaluation_api_agents_evaluation_get': undefined;
  'get_agent_evaluation_v2_api_agents_evaluation_v2_get': undefined;
  'get_agent_history_api_agents_history_get': undefined;
  'get_agents_list_api_agents_list_get': undefined;
  'get_agents_movement_api_agents_movement_get': undefined;
  'get_agents_overview_api_agents_overview_get': undefined;
  'get_agent_profile_api_agents_profile_get': undefined;
  'get_stores_coverage_api_agents_stores_coverage_get': undefined;
  'get_current_ai_forecast_api_ai_forecast_current_get': undefined;
  'get_rolling_12_ai_forecast_api_ai_forecast_rolling_12_get': undefined;
  'get_focus_history_api_campaigns_history_get': undefined;
  'get_campaign_overview_api_campaigns_overview_get': undefined;
  'get_promotions_incentives_api_campaigns_promotions_incentives_get': undefined;
  'get_active_contest_api_contests_active_get': undefined;
  'get_active_contests_api_contests_active_all_get': undefined;
  'get_alerts_api_crm_alerts_get': undefined;
  'get_scores_api_crm_scores_get': undefined;
  'recalculate_scores_api_crm_scores_recalculate_post': undefined;
  'get_dashboard_all_api_dashboard_all_get': undefined;
  'get_dashboard_all_batch_api_dashboard_all_batch_post': RetailDashboardAllBatchRequest;
  'get_daily_sales_api_dashboard_daily_get': undefined;
  'get_monthly_history_api_dashboard_history_get': undefined;
  'get_dashboard_history_details_batch_api_dashboard_history_details_batch_post': RetailDashboardAllBatchRequest;
  'get_history_by_year_api_dashboard_history_year_get': undefined;
  'get_performance_detail_api_dashboard_performance_detail_get': undefined;
  'get_premium_glass_api_dashboard_premium_glass_get': undefined;
  'get_special_cards_api_dashboard_special_cards_get': undefined;
  'get_summary_api_dashboard_summary_get': undefined;
  'get_catalog_api_exports_catalog_get': undefined;
  'download_export_api_exports_download_post': RetailExportRequest;
  'create_export_operation_api_exports_operations_post': RetailExportRequest;
  'get_resumable_export_operation_api_exports_operations_resumable_get': undefined;
  'get_export_operation_api_exports_operations__operation_id__get': undefined;
  'cancel_export_operation_api_exports_operations__operation_id__cancel_post': undefined;
  'download_export_operation_api_exports_operations__operation_id__download_get': undefined;
  'preview_export_api_exports_preview_post': RetailExportRequest;
  'get_available_months_api_filters_months_get': undefined;
  'get_filter_options_api_filters_options_get': undefined;
  'grile_agent_targets_diff_api_grile_agent_targets_diff_post': RetailAgentTargetRunRequest;
  'grile_agent_targets_operation_api_grile_agent_targets_operations__operation_id__get': undefined;
  'grile_agent_targets_sync_api_grile_agent_targets_sync_post': RetailAgentTargetRunRequest;
  'grile_monthly_download_api_grile_monthly_download__kind___month__get': undefined;
  'grile_monthly_job_api_grile_monthly_job__job_id__get': undefined;
  'grile_monthly_manifest_approve_api_grile_monthly_manifests__manifest_id__approve_post': undefined;
  'grile_monthly_manifest_api_grile_monthly_manifests__month__get': undefined;
  'grile_monthly_permissions_api_grile_monthly_permissions_get': undefined;
  'grile_monthly_run_api_grile_monthly_run_post': RetailMonthlyRunRequest;
  'grile_overview_api_grile_overview_get': undefined;
  'grile_run_api_grile_run_post': undefined;
  'grile_run_status_api_grile_run_status_get': undefined;
  'grile_store_refresh_operation_api_grile_store_refreshes__operation_id__get': undefined;
  'grile_store_refresh_api_grile_stores__site_code__refresh_post': undefined;
  'get_asm_perf_api_hr_asm_performance_get': undefined;
  'get_asm_perf_history_api_hr_asm_performance__asm_name__history_get': undefined;
  'get_asm_salary_api_hr_asm_salary__asm_name__get': undefined;
  'get_leave_requests_api_hr_leave_requests_get': undefined;
  'post_leave_request_api_hr_leave_requests_post': RetailLeaveRequestCreate;
  'patch_leave_request_api_hr_leave_requests__request_id__patch': RetailLeaveStatusUpdate;
  'get_manager_overview_api_hr_manager_overview_get': undefined;
  'get_performance_api_hr_performance__agent_name__get': undefined;
  'reconcile_erp_report_file_api_import_erp_reconciliation_post': FormData;
  'get_import_history_api_import_history_get': undefined;
  'get_import_job_status_api_import_jobs__job_id__get': undefined;
  'upload_promo_actuals_file_api_import_promo_actuals_post': FormData;
  'upload_sales_file_api_import_sales_post': FormData;
  'promote_sales_generation_api_import_sales__snapshot_id__promote_post': RetailSalesGenerationPromotionRequest;
  'annual_api_store_pnl_annual_get': undefined;
  'months_api_store_pnl_months_get': undefined;
  'overview_api_store_pnl_overview_get': undefined;
  'pnl_permissions_api_store_pnl_permissions_get': undefined;
  'regions_api_store_pnl_regions_get': undefined;
  'stores_api_store_pnl_stores_get': undefined;
  'list_stores_api_stores_get': undefined;
  'save_targets_api_stores_targets_post': Array<RetailStoreTargetInput>;
  'change_store_activity_api_stores__site_code__activity_post': RetailStoreActivityChangeRequest;
  'get_context_api_target_calculator_context_get': undefined;
  'list_scenarios_api_target_calculator_scenarios_get': undefined;
  'calculate_scenario_api_target_calculator_scenarios_calculate_post': RetailTargetCalculationRequest;
  'get_scenario_api_target_calculator_scenarios__scenario_id__get': undefined;
  'export_scenario_api_target_calculator_scenarios__scenario_id__export_get': undefined;
  'finalize_scenario_api_target_calculator_scenarios__scenario_id__finalize_post': RetailTargetFinalizeRequest;
  'update_final_targets_api_target_calculator_scenarios__scenario_id__rows_patch': RetailTargetFinalRowsRequest;
  'get_store_detail_api_target_calculator_scenarios__scenario_id__stores__site_code__get': undefined;
  'get_tasks_api_tasks_get': undefined;
  'post_task_api_tasks_post': RetailTaskCreate;
  'remove_task_api_tasks__task_id__delete': undefined;
  'patch_task_api_tasks__task_id__patch': RetailTaskUpdate;
  'get_visits_report_api_visits_report_get': undefined;
  'get_visit_photo_api_visits_report_photo__visit_id___filename__get': undefined;
  'get_visits_tree_api_visits_report_tree_get': undefined;
  'get_visit_detail_api_visits_report_visit__visit_id__get': undefined;
  'session_status_auth_session_get': undefined;
  'session_login_auth_session_login_get': undefined;
  'session_logout_auth_session_logout_post': undefined;
  'metrics_metrics_get': undefined;
  'agent_history_by_retail_code_salarii_agents_history_by_retail_code_get': undefined;
  'agents_summary_salarii_agents_summary_get': undefined;
  'agent_history_salarii_agents__person_id__history_get': undefined;
  'audit_salary_export_salarii_audit_export_post': RetailSalaryExportAudit;
  'salarii_evolution_salarii_evolution_get': undefined;
  'salarii_overview_salarii_overview_get': undefined;
  'list_records_salarii_records_get': undefined;
  'salarii_stores_salarii_stores_get': undefined;
  'salarii_summary_salarii_summary_get': undefined;
  'salarii_trend_salarii_trend_get': undefined;
}

export interface RetailOperationMeta {
  'get_agent_evaluation_api_agents_evaluation_get': { method: 'get'; path: '/api/agents/evaluation'; responseType: 'json' };
  'get_agent_evaluation_v2_api_agents_evaluation_v2_get': { method: 'get'; path: '/api/agents/evaluation-v2'; responseType: 'json' };
  'get_agent_history_api_agents_history_get': { method: 'get'; path: '/api/agents/history'; responseType: 'json' };
  'get_agents_list_api_agents_list_get': { method: 'get'; path: '/api/agents/list'; responseType: 'json' };
  'get_agents_movement_api_agents_movement_get': { method: 'get'; path: '/api/agents/movement'; responseType: 'json' };
  'get_agents_overview_api_agents_overview_get': { method: 'get'; path: '/api/agents/overview'; responseType: 'json' };
  'get_agent_profile_api_agents_profile_get': { method: 'get'; path: '/api/agents/profile'; responseType: 'json' };
  'get_stores_coverage_api_agents_stores_coverage_get': { method: 'get'; path: '/api/agents/stores-coverage'; responseType: 'json' };
  'get_current_ai_forecast_api_ai_forecast_current_get': { method: 'get'; path: '/api/ai-forecast/current'; responseType: 'json' };
  'get_rolling_12_ai_forecast_api_ai_forecast_rolling_12_get': { method: 'get'; path: '/api/ai-forecast/rolling-12'; responseType: 'json' };
  'get_focus_history_api_campaigns_history_get': { method: 'get'; path: '/api/campaigns/history'; responseType: 'json' };
  'get_campaign_overview_api_campaigns_overview_get': { method: 'get'; path: '/api/campaigns/overview'; responseType: 'json' };
  'get_promotions_incentives_api_campaigns_promotions_incentives_get': { method: 'get'; path: '/api/campaigns/promotions-incentives'; responseType: 'json' };
  'get_active_contest_api_contests_active_get': { method: 'get'; path: '/api/contests/active'; responseType: 'json' };
  'get_active_contests_api_contests_active_all_get': { method: 'get'; path: '/api/contests/active/all'; responseType: 'json' };
  'get_alerts_api_crm_alerts_get': { method: 'get'; path: '/api/crm/alerts'; responseType: 'json' };
  'get_scores_api_crm_scores_get': { method: 'get'; path: '/api/crm/scores'; responseType: 'json' };
  'recalculate_scores_api_crm_scores_recalculate_post': { method: 'post'; path: '/api/crm/scores/recalculate'; responseType: 'json' };
  'get_dashboard_all_api_dashboard_all_get': { method: 'get'; path: '/api/dashboard/all'; responseType: 'json' };
  'get_dashboard_all_batch_api_dashboard_all_batch_post': { method: 'post'; path: '/api/dashboard/all-batch'; responseType: 'json' };
  'get_daily_sales_api_dashboard_daily_get': { method: 'get'; path: '/api/dashboard/daily'; responseType: 'json' };
  'get_monthly_history_api_dashboard_history_get': { method: 'get'; path: '/api/dashboard/history'; responseType: 'json' };
  'get_dashboard_history_details_batch_api_dashboard_history_details_batch_post': { method: 'post'; path: '/api/dashboard/history-details-batch'; responseType: 'json' };
  'get_history_by_year_api_dashboard_history_year_get': { method: 'get'; path: '/api/dashboard/history-year'; responseType: 'json' };
  'get_performance_detail_api_dashboard_performance_detail_get': { method: 'get'; path: '/api/dashboard/performance-detail'; responseType: 'json' };
  'get_premium_glass_api_dashboard_premium_glass_get': { method: 'get'; path: '/api/dashboard/premium-glass'; responseType: 'json' };
  'get_special_cards_api_dashboard_special_cards_get': { method: 'get'; path: '/api/dashboard/special-cards'; responseType: 'json' };
  'get_summary_api_dashboard_summary_get': { method: 'get'; path: '/api/dashboard/summary'; responseType: 'json' };
  'get_catalog_api_exports_catalog_get': { method: 'get'; path: '/api/exports/catalog'; responseType: 'json' };
  'download_export_api_exports_download_post': { method: 'post'; path: '/api/exports/download'; responseType: 'blob' };
  'create_export_operation_api_exports_operations_post': { method: 'post'; path: '/api/exports/operations'; responseType: 'json' };
  'get_resumable_export_operation_api_exports_operations_resumable_get': { method: 'get'; path: '/api/exports/operations/resumable'; responseType: 'json' };
  'get_export_operation_api_exports_operations__operation_id__get': { method: 'get'; path: '/api/exports/operations/{operation_id}'; responseType: 'json' };
  'cancel_export_operation_api_exports_operations__operation_id__cancel_post': { method: 'post'; path: '/api/exports/operations/{operation_id}/cancel'; responseType: 'json' };
  'download_export_operation_api_exports_operations__operation_id__download_get': { method: 'get'; path: '/api/exports/operations/{operation_id}/download'; responseType: 'blob' };
  'preview_export_api_exports_preview_post': { method: 'post'; path: '/api/exports/preview'; responseType: 'json' };
  'get_available_months_api_filters_months_get': { method: 'get'; path: '/api/filters/months'; responseType: 'json' };
  'get_filter_options_api_filters_options_get': { method: 'get'; path: '/api/filters/options'; responseType: 'json' };
  'grile_agent_targets_diff_api_grile_agent_targets_diff_post': { method: 'post'; path: '/api/grile/agent-targets/diff'; responseType: 'json' };
  'grile_agent_targets_operation_api_grile_agent_targets_operations__operation_id__get': { method: 'get'; path: '/api/grile/agent-targets/operations/{operation_id}'; responseType: 'json' };
  'grile_agent_targets_sync_api_grile_agent_targets_sync_post': { method: 'post'; path: '/api/grile/agent-targets/sync'; responseType: 'json' };
  'grile_monthly_download_api_grile_monthly_download__kind___month__get': { method: 'get'; path: '/api/grile/monthly/download/{kind}/{month}'; responseType: 'json' };
  'grile_monthly_job_api_grile_monthly_job__job_id__get': { method: 'get'; path: '/api/grile/monthly/job/{job_id}'; responseType: 'json' };
  'grile_monthly_manifest_approve_api_grile_monthly_manifests__manifest_id__approve_post': { method: 'post'; path: '/api/grile/monthly/manifests/{manifest_id}/approve'; responseType: 'json' };
  'grile_monthly_manifest_api_grile_monthly_manifests__month__get': { method: 'get'; path: '/api/grile/monthly/manifests/{month}'; responseType: 'json' };
  'grile_monthly_permissions_api_grile_monthly_permissions_get': { method: 'get'; path: '/api/grile/monthly/permissions'; responseType: 'json' };
  'grile_monthly_run_api_grile_monthly_run_post': { method: 'post'; path: '/api/grile/monthly/run'; responseType: 'json' };
  'grile_overview_api_grile_overview_get': { method: 'get'; path: '/api/grile/overview'; responseType: 'json' };
  'grile_run_api_grile_run_post': { method: 'post'; path: '/api/grile/run'; responseType: 'json' };
  'grile_run_status_api_grile_run_status_get': { method: 'get'; path: '/api/grile/run-status'; responseType: 'json' };
  'grile_store_refresh_operation_api_grile_store_refreshes__operation_id__get': { method: 'get'; path: '/api/grile/store-refreshes/{operation_id}'; responseType: 'json' };
  'grile_store_refresh_api_grile_stores__site_code__refresh_post': { method: 'post'; path: '/api/grile/stores/{site_code}/refresh'; responseType: 'json' };
  'get_asm_perf_api_hr_asm_performance_get': { method: 'get'; path: '/api/hr/asm-performance'; responseType: 'json' };
  'get_asm_perf_history_api_hr_asm_performance__asm_name__history_get': { method: 'get'; path: '/api/hr/asm-performance/{asm_name}/history'; responseType: 'json' };
  'get_asm_salary_api_hr_asm_salary__asm_name__get': { method: 'get'; path: '/api/hr/asm-salary/{asm_name}'; responseType: 'json' };
  'get_leave_requests_api_hr_leave_requests_get': { method: 'get'; path: '/api/hr/leave-requests'; responseType: 'json' };
  'post_leave_request_api_hr_leave_requests_post': { method: 'post'; path: '/api/hr/leave-requests'; responseType: 'json' };
  'patch_leave_request_api_hr_leave_requests__request_id__patch': { method: 'patch'; path: '/api/hr/leave-requests/{request_id}'; responseType: 'json' };
  'get_manager_overview_api_hr_manager_overview_get': { method: 'get'; path: '/api/hr/manager-overview'; responseType: 'json' };
  'get_performance_api_hr_performance__agent_name__get': { method: 'get'; path: '/api/hr/performance/{agent_name}'; responseType: 'json' };
  'reconcile_erp_report_file_api_import_erp_reconciliation_post': { method: 'post'; path: '/api/import/erp-reconciliation'; responseType: 'json' };
  'get_import_history_api_import_history_get': { method: 'get'; path: '/api/import/history'; responseType: 'json' };
  'get_import_job_status_api_import_jobs__job_id__get': { method: 'get'; path: '/api/import/jobs/{job_id}'; responseType: 'json' };
  'upload_promo_actuals_file_api_import_promo_actuals_post': { method: 'post'; path: '/api/import/promo-actuals'; responseType: 'json' };
  'upload_sales_file_api_import_sales_post': { method: 'post'; path: '/api/import/sales'; responseType: 'json' };
  'promote_sales_generation_api_import_sales__snapshot_id__promote_post': { method: 'post'; path: '/api/import/sales/{snapshot_id}/promote'; responseType: 'json' };
  'annual_api_store_pnl_annual_get': { method: 'get'; path: '/api/store-pnl/annual'; responseType: 'json' };
  'months_api_store_pnl_months_get': { method: 'get'; path: '/api/store-pnl/months'; responseType: 'json' };
  'overview_api_store_pnl_overview_get': { method: 'get'; path: '/api/store-pnl/overview'; responseType: 'json' };
  'pnl_permissions_api_store_pnl_permissions_get': { method: 'get'; path: '/api/store-pnl/permissions'; responseType: 'json' };
  'regions_api_store_pnl_regions_get': { method: 'get'; path: '/api/store-pnl/regions'; responseType: 'json' };
  'stores_api_store_pnl_stores_get': { method: 'get'; path: '/api/store-pnl/stores'; responseType: 'json' };
  'list_stores_api_stores_get': { method: 'get'; path: '/api/stores'; responseType: 'json' };
  'save_targets_api_stores_targets_post': { method: 'post'; path: '/api/stores/targets'; responseType: 'json' };
  'change_store_activity_api_stores__site_code__activity_post': { method: 'post'; path: '/api/stores/{site_code}/activity'; responseType: 'json' };
  'get_context_api_target_calculator_context_get': { method: 'get'; path: '/api/target-calculator/context'; responseType: 'json' };
  'list_scenarios_api_target_calculator_scenarios_get': { method: 'get'; path: '/api/target-calculator/scenarios'; responseType: 'json' };
  'calculate_scenario_api_target_calculator_scenarios_calculate_post': { method: 'post'; path: '/api/target-calculator/scenarios/calculate'; responseType: 'json' };
  'get_scenario_api_target_calculator_scenarios__scenario_id__get': { method: 'get'; path: '/api/target-calculator/scenarios/{scenario_id}'; responseType: 'json' };
  'export_scenario_api_target_calculator_scenarios__scenario_id__export_get': { method: 'get'; path: '/api/target-calculator/scenarios/{scenario_id}/export'; responseType: 'blob' };
  'finalize_scenario_api_target_calculator_scenarios__scenario_id__finalize_post': { method: 'post'; path: '/api/target-calculator/scenarios/{scenario_id}/finalize'; responseType: 'json' };
  'update_final_targets_api_target_calculator_scenarios__scenario_id__rows_patch': { method: 'patch'; path: '/api/target-calculator/scenarios/{scenario_id}/rows'; responseType: 'json' };
  'get_store_detail_api_target_calculator_scenarios__scenario_id__stores__site_code__get': { method: 'get'; path: '/api/target-calculator/scenarios/{scenario_id}/stores/{site_code}'; responseType: 'json' };
  'get_tasks_api_tasks_get': { method: 'get'; path: '/api/tasks'; responseType: 'json' };
  'post_task_api_tasks_post': { method: 'post'; path: '/api/tasks'; responseType: 'json' };
  'remove_task_api_tasks__task_id__delete': { method: 'delete'; path: '/api/tasks/{task_id}'; responseType: 'json' };
  'patch_task_api_tasks__task_id__patch': { method: 'patch'; path: '/api/tasks/{task_id}'; responseType: 'json' };
  'get_visits_report_api_visits_report_get': { method: 'get'; path: '/api/visits-report'; responseType: 'json' };
  'get_visit_photo_api_visits_report_photo__visit_id___filename__get': { method: 'get'; path: '/api/visits-report/photo/{visit_id}/{filename}'; responseType: 'blob' };
  'get_visits_tree_api_visits_report_tree_get': { method: 'get'; path: '/api/visits-report/tree'; responseType: 'json' };
  'get_visit_detail_api_visits_report_visit__visit_id__get': { method: 'get'; path: '/api/visits-report/visit/{visit_id}'; responseType: 'json' };
  'session_status_auth_session_get': { method: 'get'; path: '/auth/session'; responseType: 'json' };
  'session_login_auth_session_login_get': { method: 'get'; path: '/auth/session/login'; responseType: 'json' };
  'session_logout_auth_session_logout_post': { method: 'post'; path: '/auth/session/logout'; responseType: 'json' };
  'metrics_metrics_get': { method: 'get'; path: '/metrics'; responseType: 'json' };
  'agent_history_by_retail_code_salarii_agents_history_by_retail_code_get': { method: 'get'; path: '/salarii/agents/history-by-retail-code'; responseType: 'json' };
  'agents_summary_salarii_agents_summary_get': { method: 'get'; path: '/salarii/agents/summary'; responseType: 'json' };
  'agent_history_salarii_agents__person_id__history_get': { method: 'get'; path: '/salarii/agents/{person_id}/history'; responseType: 'json' };
  'audit_salary_export_salarii_audit_export_post': { method: 'post'; path: '/salarii/audit/export'; responseType: 'json' };
  'salarii_evolution_salarii_evolution_get': { method: 'get'; path: '/salarii/evolution'; responseType: 'json' };
  'salarii_overview_salarii_overview_get': { method: 'get'; path: '/salarii/overview'; responseType: 'json' };
  'list_records_salarii_records_get': { method: 'get'; path: '/salarii/records'; responseType: 'json' };
  'salarii_stores_salarii_stores_get': { method: 'get'; path: '/salarii/stores'; responseType: 'json' };
  'salarii_summary_salarii_summary_get': { method: 'get'; path: '/salarii/summary'; responseType: 'json' };
  'salarii_trend_salarii_trend_get': { method: 'get'; path: '/salarii/trend'; responseType: 'json' };
}

export const RETAIL_DECIMAL_PATHS: { readonly [Id in RetailOperationId]: ReadonlySet<string> } = {
  'get_agent_evaluation_api_agents_evaluation_get': new Set<string>([
    'rows/*/bonuri_pct',
    'rows/*/daily_average',
    'rows/*/focus_pct',
    'rows/*/peer_daily_average',
    'rows/*/premium_glass_pct',
    'rows/*/store_target',
    'rows/*/target_pct',
    'rows/*/target_value',
    'rows/*/total_sales',
    'rows/*/value_reper',
  ]),
  'get_agent_evaluation_v2_api_agents_evaluation_v2_get': new Set<string>([
    'rows/*/bonuri_pct',
    'rows/*/bonuri_score',
    'rows/*/daily_average',
    'rows/*/daily_reference',
    'rows/*/daily_score',
    'rows/*/daily_vs_reference_pct',
    'rows/*/focus_pct',
    'rows/*/focus_score',
    'rows/*/forecast_factor',
    'rows/*/forecast_sales',
    'rows/*/premium_glass_pct',
    'rows/*/premium_glass_score',
    'rows/*/target_forecast_pct',
    'rows/*/target_pct',
    'rows/*/target_score',
    'rows/*/target_value',
    'rows/*/total_sales',
    'rows/*/total_score',
    'rows/*/trend_daily_pct',
    'rows/*/value_reper',
    'rows/*/value_reper_score',
  ]),
  'get_agent_history_api_agents_history_get': new Set<string>([
    'history/*/total_sales',
  ]),
  'get_agents_list_api_agents_list_get': new Set<string>([
    'items/*/total_sales',
  ]),
  'get_agents_movement_api_agents_movement_get': new Set<string>([
  ]),
  'get_agents_overview_api_agents_overview_get': new Set<string>([
    'avg_seniority_months',
    'retention_rate',
    'stability_rate',
  ]),
  'get_agent_profile_api_agents_profile_get': new Set<string>([
    'avg_monthly_sales',
    'best_month_sales',
    'career_total_sales',
  ]),
  'get_stores_coverage_api_agents_stores_coverage_get': new Set<string>([
  ]),
  'get_current_ai_forecast_api_ai_forecast_current_get': new Set<string>([
    'daily/*/actual_sales',
    'daily/*/cumulative_actual',
    'daily/*/cumulative_forecast',
    'daily/*/forecast_sales',
    'managers/*/actual_sales',
    'managers/*/delta_pct',
    'managers/*/delta_sales',
    'managers/*/expected_sales_to_date',
    'managers/*/forecast_sales',
    'stores/*/actual_sales',
    'stores/*/delta_pct',
    'stores/*/delta_sales',
    'stores/*/expected_sales_to_date',
    'stores/*/forecast_sales',
    'summary/actual_sales',
    'summary/delta_pct',
    'summary/delta_sales',
    'summary/expected_sales_to_date',
    'summary/forecast_sales',
  ]),
  'get_rolling_12_ai_forecast_api_ai_forecast_rolling_12_get': new Set<string>([
    'managers/*/actual_sales',
    'managers/*/delta_pct',
    'managers/*/delta_sales',
    'managers/*/forecast_sales',
    'months/*/actual_sales',
    'months/*/delta_pct',
    'months/*/delta_sales',
    'months/*/forecast_sales',
    'stores/*/actual_sales',
    'stores/*/delta_pct',
    'stores/*/delta_sales',
    'stores/*/forecast_sales',
    'summary/actual_sales',
    'summary/delta_pct',
    'summary/delta_sales',
    'summary/forecast_sales',
  ]),
  'get_focus_history_api_campaigns_history_get': new Set<string>([
    'history/*/focus_share_pct',
    'history/*/total_focus_sales',
  ]),
  'get_campaign_overview_api_campaigns_overview_get': new Set<string>([
    'overview/focus_share_pct',
    'overview/total_focus_sales',
    'products/*/sales_total',
    'stores/*/sales_total',
  ]),
  'get_promotions_incentives_api_campaigns_promotions_incentives_get': new Set<string>([
    'promo_discount_value',
  ]),
  'get_active_contest_api_contests_active_get': new Set<string>([
  ]),
  'get_active_contests_api_contests_active_all_get': new Set<string>([
  ]),
  'get_alerts_api_crm_alerts_get': new Set<string>([
  ]),
  'get_scores_api_crm_scores_get': new Set<string>([
  ]),
  'recalculate_scores_api_crm_scores_recalculate_post': new Set<string>([
  ]),
  'get_dashboard_all_api_dashboard_all_get': new Set<string>([
    'agents/*/medie_produs',
    'agents/*/medie_zilnica',
    'agents/*/prc_focus_acc_qty',
    'agents/*/proc_bon2acc',
    'agents/*/proc_realizare_target',
    'agents/*/promo_discount_value',
    'agents/*/target',
    'agents/*/total_vanzari',
    'asms/*/medie_produs',
    'asms/*/medie_zilnica',
    'asms/*/prc_focus_acc_qty',
    'asms/*/proc_bon2acc',
    'asms/*/proc_realizare_target',
    'asms/*/promo_discount_value',
    'asms/*/target',
    'asms/*/total_vanzari',
    'brand_mix/*/sales_total',
    'brand_mix/*/share_pct',
    'category_mix/*/sales_total',
    'category_mix/*/share_pct',
    'daily/*/total_sales',
    'daily_last_year/*/total_sales',
    'focus_subcategory_mix/*/sales_total',
    'focus_subcategory_mix/*/share_pct',
    'period_comparison/current/avg_receipt_value',
    'period_comparison/current/daily_average',
    'period_comparison/current/medie_produs',
    'period_comparison/current/prc_focus_acc_qty',
    'period_comparison/current/proc_bon2acc',
    'period_comparison/current/total_sales',
    'period_comparison/previous/avg_receipt_value',
    'period_comparison/previous/daily_average',
    'period_comparison/previous/medie_produs',
    'period_comparison/previous/prc_focus_acc_qty',
    'period_comparison/previous/proc_bon2acc',
    'period_comparison/previous/total_sales',
    'period_comparison/year_over_year/avg_receipt_value',
    'period_comparison/year_over_year/daily_average',
    'period_comparison/year_over_year/medie_produs',
    'period_comparison/year_over_year/prc_focus_acc_qty',
    'period_comparison/year_over_year/proc_bon2acc',
    'period_comparison/year_over_year/total_sales',
    'premium_glass/agents/*/premium_qty_share_pct',
    'premium_glass/agents/*/premium_sales',
    'premium_glass/agents/*/regular_sales',
    'premium_glass/agents/*/total_sales',
    'premium_glass/managers/*/premium_qty_share_pct',
    'premium_glass/managers/*/premium_sales',
    'premium_glass/managers/*/regular_sales',
    'premium_glass/managers/*/total_sales',
    'premium_glass/models/*/premium_qty_share_pct',
    'premium_glass/models/*/premium_sales',
    'premium_glass/models/*/regular_sales',
    'premium_glass/models/*/total_sales',
    'premium_glass/products/*/sales',
    'premium_glass/stores/*/premium_qty_share_pct',
    'premium_glass/stores/*/premium_sales',
    'premium_glass/stores/*/regular_sales',
    'premium_glass/stores/*/total_sales',
    'premium_glass/summary/premium_qty_share_pct',
    'premium_glass/summary/premium_sales',
    'premium_glass/summary/premium_sales_share_pct',
    'premium_glass/summary/regular_sales',
    'premium_glass/summary/total_sales',
    'premium_glass/surfaces/*/premium_qty_share_pct',
    'premium_glass/surfaces/*/premium_sales',
    'premium_glass/surfaces/*/regular_sales',
    'premium_glass/surfaces/*/total_sales',
    'promo_incentive/incentive_potential',
    'promo_incentive/incentive_sales',
    'promo_incentive/incentive_value',
    'promo_incentive/promo_impact',
    'promo_incentive/promo_sales',
    'receipt_bucket_mix/*/share_pct',
    'regionals/*/forecast_target_pct',
    'regionals/*/medie_produs',
    'regionals/*/medie_zilnica',
    'regionals/*/prc_focus_acc_qty',
    'regionals/*/proc_bon2acc',
    'regionals/*/proc_realizare_target',
    'regionals/*/promo_discount_value',
    'regionals/*/target',
    'regionals/*/total_vanzari',
    'stores/*/forecast_target_pct',
    'stores/*/medie_produs',
    'stores/*/prc_focus_acc_qty',
    'stores/*/proc_bon2acc',
    'stores/*/proc_realizare_target',
    'stores/*/promo_discount_value',
    'stores/*/target',
    'stores/*/total_vanzari',
    'summary/daily_average',
    'summary/forecast_sales',
    'summary/forecast_target_progress_pct',
    'summary/medie_produs',
    'summary/prc_focus_acc_qty',
    'summary/proc_bon2acc',
    'summary/target_progress_pct',
    'summary/total_sales',
    'summary/total_target',
  ]),
  'get_dashboard_all_batch_api_dashboard_all_batch_post': new Set<string>([
    'results/*/agents/*/medie_produs',
    'results/*/agents/*/medie_zilnica',
    'results/*/agents/*/prc_focus_acc_qty',
    'results/*/agents/*/proc_bon2acc',
    'results/*/agents/*/proc_realizare_target',
    'results/*/agents/*/promo_discount_value',
    'results/*/agents/*/target',
    'results/*/agents/*/total_vanzari',
    'results/*/asms/*/medie_produs',
    'results/*/asms/*/medie_zilnica',
    'results/*/asms/*/prc_focus_acc_qty',
    'results/*/asms/*/proc_bon2acc',
    'results/*/asms/*/proc_realizare_target',
    'results/*/asms/*/promo_discount_value',
    'results/*/asms/*/target',
    'results/*/asms/*/total_vanzari',
    'results/*/brand_mix/*/sales_total',
    'results/*/brand_mix/*/share_pct',
    'results/*/category_mix/*/sales_total',
    'results/*/category_mix/*/share_pct',
    'results/*/daily/*/total_sales',
    'results/*/daily_last_year/*/total_sales',
    'results/*/focus_subcategory_mix/*/sales_total',
    'results/*/focus_subcategory_mix/*/share_pct',
    'results/*/period_comparison/current/avg_receipt_value',
    'results/*/period_comparison/current/daily_average',
    'results/*/period_comparison/current/medie_produs',
    'results/*/period_comparison/current/prc_focus_acc_qty',
    'results/*/period_comparison/current/proc_bon2acc',
    'results/*/period_comparison/current/total_sales',
    'results/*/period_comparison/previous/avg_receipt_value',
    'results/*/period_comparison/previous/daily_average',
    'results/*/period_comparison/previous/medie_produs',
    'results/*/period_comparison/previous/prc_focus_acc_qty',
    'results/*/period_comparison/previous/proc_bon2acc',
    'results/*/period_comparison/previous/total_sales',
    'results/*/period_comparison/year_over_year/avg_receipt_value',
    'results/*/period_comparison/year_over_year/daily_average',
    'results/*/period_comparison/year_over_year/medie_produs',
    'results/*/period_comparison/year_over_year/prc_focus_acc_qty',
    'results/*/period_comparison/year_over_year/proc_bon2acc',
    'results/*/period_comparison/year_over_year/total_sales',
    'results/*/premium_glass/agents/*/premium_qty_share_pct',
    'results/*/premium_glass/agents/*/premium_sales',
    'results/*/premium_glass/agents/*/regular_sales',
    'results/*/premium_glass/agents/*/total_sales',
    'results/*/premium_glass/managers/*/premium_qty_share_pct',
    'results/*/premium_glass/managers/*/premium_sales',
    'results/*/premium_glass/managers/*/regular_sales',
    'results/*/premium_glass/managers/*/total_sales',
    'results/*/premium_glass/models/*/premium_qty_share_pct',
    'results/*/premium_glass/models/*/premium_sales',
    'results/*/premium_glass/models/*/regular_sales',
    'results/*/premium_glass/models/*/total_sales',
    'results/*/premium_glass/products/*/sales',
    'results/*/premium_glass/stores/*/premium_qty_share_pct',
    'results/*/premium_glass/stores/*/premium_sales',
    'results/*/premium_glass/stores/*/regular_sales',
    'results/*/premium_glass/stores/*/total_sales',
    'results/*/premium_glass/summary/premium_qty_share_pct',
    'results/*/premium_glass/summary/premium_sales',
    'results/*/premium_glass/summary/premium_sales_share_pct',
    'results/*/premium_glass/summary/regular_sales',
    'results/*/premium_glass/summary/total_sales',
    'results/*/premium_glass/surfaces/*/premium_qty_share_pct',
    'results/*/premium_glass/surfaces/*/premium_sales',
    'results/*/premium_glass/surfaces/*/regular_sales',
    'results/*/premium_glass/surfaces/*/total_sales',
    'results/*/promo_incentive/incentive_potential',
    'results/*/promo_incentive/incentive_sales',
    'results/*/promo_incentive/incentive_value',
    'results/*/promo_incentive/promo_impact',
    'results/*/promo_incentive/promo_sales',
    'results/*/receipt_bucket_mix/*/share_pct',
    'results/*/regionals/*/forecast_target_pct',
    'results/*/regionals/*/medie_produs',
    'results/*/regionals/*/medie_zilnica',
    'results/*/regionals/*/prc_focus_acc_qty',
    'results/*/regionals/*/proc_bon2acc',
    'results/*/regionals/*/proc_realizare_target',
    'results/*/regionals/*/promo_discount_value',
    'results/*/regionals/*/target',
    'results/*/regionals/*/total_vanzari',
    'results/*/stores/*/forecast_target_pct',
    'results/*/stores/*/medie_produs',
    'results/*/stores/*/prc_focus_acc_qty',
    'results/*/stores/*/proc_bon2acc',
    'results/*/stores/*/proc_realizare_target',
    'results/*/stores/*/promo_discount_value',
    'results/*/stores/*/target',
    'results/*/stores/*/total_vanzari',
    'results/*/summary/daily_average',
    'results/*/summary/forecast_sales',
    'results/*/summary/forecast_target_progress_pct',
    'results/*/summary/medie_produs',
    'results/*/summary/prc_focus_acc_qty',
    'results/*/summary/proc_bon2acc',
    'results/*/summary/target_progress_pct',
    'results/*/summary/total_sales',
    'results/*/summary/total_target',
  ]),
  'get_daily_sales_api_dashboard_daily_get': new Set<string>([
    '*/total_sales',
  ]),
  'get_monthly_history_api_dashboard_history_get': new Set<string>([
    'history/*/daily_average',
    'history/*/medie_produs',
    'history/*/prc_focus_acc_qty',
    'history/*/proc_bon2acc',
    'history/*/target_progress_pct',
    'history/*/total_sales',
    'history/*/total_target',
  ]),
  'get_dashboard_history_details_batch_api_dashboard_history_details_batch_post': new Set<string>([
    'results/*/agents/*/medie_produs',
    'results/*/agents/*/medie_zilnica',
    'results/*/agents/*/prc_focus_acc_qty',
    'results/*/agents/*/proc_bon2acc',
    'results/*/agents/*/proc_realizare_target',
    'results/*/agents/*/promo_discount_value',
    'results/*/agents/*/target',
    'results/*/agents/*/total_vanzari',
    'results/*/asms/*/medie_produs',
    'results/*/asms/*/medie_zilnica',
    'results/*/asms/*/prc_focus_acc_qty',
    'results/*/asms/*/proc_bon2acc',
    'results/*/asms/*/proc_realizare_target',
    'results/*/asms/*/promo_discount_value',
    'results/*/asms/*/target',
    'results/*/asms/*/total_vanzari',
    'results/*/brand_mix/*/sales_total',
    'results/*/brand_mix/*/share_pct',
    'results/*/category_mix/*/sales_total',
    'results/*/category_mix/*/share_pct',
    'results/*/daily/*/total_sales',
    'results/*/daily_last_year/*/total_sales',
    'results/*/focus_subcategory_mix/*/sales_total',
    'results/*/focus_subcategory_mix/*/share_pct',
    'results/*/period_comparison/current/avg_receipt_value',
    'results/*/period_comparison/current/daily_average',
    'results/*/period_comparison/current/medie_produs',
    'results/*/period_comparison/current/prc_focus_acc_qty',
    'results/*/period_comparison/current/proc_bon2acc',
    'results/*/period_comparison/current/total_sales',
    'results/*/period_comparison/previous/avg_receipt_value',
    'results/*/period_comparison/previous/daily_average',
    'results/*/period_comparison/previous/medie_produs',
    'results/*/period_comparison/previous/prc_focus_acc_qty',
    'results/*/period_comparison/previous/proc_bon2acc',
    'results/*/period_comparison/previous/total_sales',
    'results/*/period_comparison/year_over_year/avg_receipt_value',
    'results/*/period_comparison/year_over_year/daily_average',
    'results/*/period_comparison/year_over_year/medie_produs',
    'results/*/period_comparison/year_over_year/prc_focus_acc_qty',
    'results/*/period_comparison/year_over_year/proc_bon2acc',
    'results/*/period_comparison/year_over_year/total_sales',
    'results/*/premium_glass/agents/*/premium_qty_share_pct',
    'results/*/premium_glass/agents/*/premium_sales',
    'results/*/premium_glass/agents/*/regular_sales',
    'results/*/premium_glass/agents/*/total_sales',
    'results/*/premium_glass/managers/*/premium_qty_share_pct',
    'results/*/premium_glass/managers/*/premium_sales',
    'results/*/premium_glass/managers/*/regular_sales',
    'results/*/premium_glass/managers/*/total_sales',
    'results/*/premium_glass/models/*/premium_qty_share_pct',
    'results/*/premium_glass/models/*/premium_sales',
    'results/*/premium_glass/models/*/regular_sales',
    'results/*/premium_glass/models/*/total_sales',
    'results/*/premium_glass/products/*/sales',
    'results/*/premium_glass/stores/*/premium_qty_share_pct',
    'results/*/premium_glass/stores/*/premium_sales',
    'results/*/premium_glass/stores/*/regular_sales',
    'results/*/premium_glass/stores/*/total_sales',
    'results/*/premium_glass/summary/premium_qty_share_pct',
    'results/*/premium_glass/summary/premium_sales',
    'results/*/premium_glass/summary/premium_sales_share_pct',
    'results/*/premium_glass/summary/regular_sales',
    'results/*/premium_glass/summary/total_sales',
    'results/*/premium_glass/surfaces/*/premium_qty_share_pct',
    'results/*/premium_glass/surfaces/*/premium_sales',
    'results/*/premium_glass/surfaces/*/regular_sales',
    'results/*/premium_glass/surfaces/*/total_sales',
    'results/*/promo_incentive/incentive_potential',
    'results/*/promo_incentive/incentive_sales',
    'results/*/promo_incentive/incentive_value',
    'results/*/promo_incentive/promo_impact',
    'results/*/promo_incentive/promo_sales',
    'results/*/receipt_bucket_mix/*/share_pct',
    'results/*/regionals/*/forecast_target_pct',
    'results/*/regionals/*/medie_produs',
    'results/*/regionals/*/medie_zilnica',
    'results/*/regionals/*/prc_focus_acc_qty',
    'results/*/regionals/*/proc_bon2acc',
    'results/*/regionals/*/proc_realizare_target',
    'results/*/regionals/*/promo_discount_value',
    'results/*/regionals/*/target',
    'results/*/regionals/*/total_vanzari',
    'results/*/stores/*/forecast_target_pct',
    'results/*/stores/*/medie_produs',
    'results/*/stores/*/prc_focus_acc_qty',
    'results/*/stores/*/proc_bon2acc',
    'results/*/stores/*/proc_realizare_target',
    'results/*/stores/*/promo_discount_value',
    'results/*/stores/*/target',
    'results/*/stores/*/total_vanzari',
    'results/*/summary/daily_average',
    'results/*/summary/forecast_sales',
    'results/*/summary/forecast_target_progress_pct',
    'results/*/summary/medie_produs',
    'results/*/summary/prc_focus_acc_qty',
    'results/*/summary/proc_bon2acc',
    'results/*/summary/target_progress_pct',
    'results/*/summary/total_sales',
    'results/*/summary/total_target',
  ]),
  'get_history_by_year_api_dashboard_history_year_get': new Set<string>([
    'points/*/total_sales',
    'points/*/total_target',
  ]),
  'get_performance_detail_api_dashboard_performance_detail_get': new Set<string>([
    'context_summary/daily_average',
    'context_summary/forecast_sales',
    'context_summary/forecast_target_progress_pct',
    'context_summary/medie_produs',
    'context_summary/prc_focus_acc_qty',
    'context_summary/proc_bon2acc',
    'context_summary/target_progress_pct',
    'context_summary/total_sales',
    'context_summary/total_target',
    'daily/*/total_sales',
    'history/*/daily_average',
    'history/*/medie_produs',
    'history/*/prc_focus_acc_qty',
    'history/*/proc_bon2acc',
    'history/*/target_progress_pct',
    'history/*/total_sales',
    'history/*/total_target',
    'peer_rows/*/forecast_target_pct',
    'peer_rows/*/prc_focus_acc_qty',
    'peer_rows/*/proc_bon2acc',
    'peer_rows/*/target_progress_pct',
    'peer_rows/*/total_sales',
    'score_breakdown/bon2acc_points',
    'score_breakdown/focus_points',
    'score_breakdown/target_points',
    'summary/daily_average',
    'summary/forecast_sales',
    'summary/forecast_target_progress_pct',
    'summary/medie_produs',
    'summary/prc_focus_acc_qty',
    'summary/proc_bon2acc',
    'summary/target_progress_pct',
    'summary/total_sales',
    'summary/total_target',
  ]),
  'get_premium_glass_api_dashboard_premium_glass_get': new Set<string>([
    'agents/*/premium_qty_share_pct',
    'agents/*/premium_sales',
    'agents/*/regular_sales',
    'agents/*/total_sales',
    'managers/*/premium_qty_share_pct',
    'managers/*/premium_sales',
    'managers/*/regular_sales',
    'managers/*/total_sales',
    'models/*/premium_qty_share_pct',
    'models/*/premium_sales',
    'models/*/regular_sales',
    'models/*/total_sales',
    'products/*/sales',
    'stores/*/premium_qty_share_pct',
    'stores/*/premium_sales',
    'stores/*/regular_sales',
    'stores/*/total_sales',
    'summary/premium_qty_share_pct',
    'summary/premium_sales',
    'summary/premium_sales_share_pct',
    'summary/regular_sales',
    'summary/total_sales',
    'surfaces/*/premium_qty_share_pct',
    'surfaces/*/premium_sales',
    'surfaces/*/regular_sales',
    'surfaces/*/total_sales',
  ]),
  'get_special_cards_api_dashboard_special_cards_get': new Set<string>([
  ]),
  'get_summary_api_dashboard_summary_get': new Set<string>([
    'daily_average',
    'forecast_sales',
    'forecast_target_progress_pct',
    'medie_produs',
    'prc_focus_acc_qty',
    'proc_bon2acc',
    'target_progress_pct',
    'total_sales',
    'total_target',
  ]),
  'get_catalog_api_exports_catalog_get': new Set<string>([
  ]),
  'download_export_api_exports_download_post': new Set<string>([
  ]),
  'create_export_operation_api_exports_operations_post': new Set<string>([
  ]),
  'get_resumable_export_operation_api_exports_operations_resumable_get': new Set<string>([
  ]),
  'get_export_operation_api_exports_operations__operation_id__get': new Set<string>([
  ]),
  'cancel_export_operation_api_exports_operations__operation_id__cancel_post': new Set<string>([
  ]),
  'download_export_operation_api_exports_operations__operation_id__download_get': new Set<string>([
  ]),
  'preview_export_api_exports_preview_post': new Set<string>([
  ]),
  'get_available_months_api_filters_months_get': new Set<string>([
  ]),
  'get_filter_options_api_filters_options_get': new Set<string>([
  ]),
  'grile_agent_targets_diff_api_grile_agent_targets_diff_post': new Set<string>([
  ]),
  'grile_agent_targets_operation_api_grile_agent_targets_operations__operation_id__get': new Set<string>([
  ]),
  'grile_agent_targets_sync_api_grile_agent_targets_sync_post': new Set<string>([
  ]),
  'grile_monthly_download_api_grile_monthly_download__kind___month__get': new Set<string>([
  ]),
  'grile_monthly_job_api_grile_monthly_job__job_id__get': new Set<string>([
  ]),
  'grile_monthly_manifest_approve_api_grile_monthly_manifests__manifest_id__approve_post': new Set<string>([
  ]),
  'grile_monthly_manifest_api_grile_monthly_manifests__month__get': new Set<string>([
  ]),
  'grile_monthly_permissions_api_grile_monthly_permissions_get': new Set<string>([
  ]),
  'grile_monthly_run_api_grile_monthly_run_post': new Set<string>([
  ]),
  'grile_overview_api_grile_overview_get': new Set<string>([
    'managers/*/team_leaders/*/firms/*/stores/*/db_sales_mtd',
    'managers/*/team_leaders/*/firms/*/stores/*/db_target',
    'managers/*/team_leaders/*/firms/*/stores/*/grila_sales',
    'managers/*/team_leaders/*/firms/*/stores/*/grila_target',
    'managers/*/team_leaders/*/firms/*/stores/*/sales_diff',
    'managers/*/team_leaders/*/firms/*/stores/*/target_diff',
  ]),
  'grile_run_api_grile_run_post': new Set<string>([
  ]),
  'grile_run_status_api_grile_run_status_get': new Set<string>([
  ]),
  'grile_store_refresh_operation_api_grile_store_refreshes__operation_id__get': new Set<string>([
  ]),
  'grile_store_refresh_api_grile_stores__site_code__refresh_post': new Set<string>([
  ]),
  'get_asm_perf_api_hr_asm_performance_get': new Set<string>([
  ]),
  'get_asm_perf_history_api_hr_asm_performance__asm_name__history_get': new Set<string>([
  ]),
  'get_asm_salary_api_hr_asm_salary__asm_name__get': new Set<string>([
  ]),
  'get_leave_requests_api_hr_leave_requests_get': new Set<string>([
  ]),
  'post_leave_request_api_hr_leave_requests_post': new Set<string>([
  ]),
  'patch_leave_request_api_hr_leave_requests__request_id__patch': new Set<string>([
  ]),
  'get_manager_overview_api_hr_manager_overview_get': new Set<string>([
  ]),
  'get_performance_api_hr_performance__agent_name__get': new Set<string>([
  ]),
  'reconcile_erp_report_file_api_import_erp_reconciliation_post': new Set<string>([
    'erp_result/app_only_metrics/*/value',
    'erp_result/issues/*/difference',
    'erp_result/issues/*/report_value',
    'erp_result/issues/*/retail_value',
    'erp_result/metrics/*/difference',
    'erp_result/metrics/*/report_value',
    'erp_result/metrics/*/retail_value',
  ]),
  'get_import_history_api_import_history_get': new Set<string>([
  ]),
  'get_import_job_status_api_import_jobs__job_id__get': new Set<string>([
    'erp_result/app_only_metrics/*/value',
    'erp_result/issues/*/difference',
    'erp_result/issues/*/report_value',
    'erp_result/issues/*/retail_value',
    'erp_result/metrics/*/difference',
    'erp_result/metrics/*/report_value',
    'erp_result/metrics/*/retail_value',
  ]),
  'upload_promo_actuals_file_api_import_promo_actuals_post': new Set<string>([
    'erp_result/app_only_metrics/*/value',
    'erp_result/issues/*/difference',
    'erp_result/issues/*/report_value',
    'erp_result/issues/*/retail_value',
    'erp_result/metrics/*/difference',
    'erp_result/metrics/*/report_value',
    'erp_result/metrics/*/retail_value',
  ]),
  'upload_sales_file_api_import_sales_post': new Set<string>([
    'erp_result/app_only_metrics/*/value',
    'erp_result/issues/*/difference',
    'erp_result/issues/*/report_value',
    'erp_result/issues/*/retail_value',
    'erp_result/metrics/*/difference',
    'erp_result/metrics/*/report_value',
    'erp_result/metrics/*/retail_value',
  ]),
  'promote_sales_generation_api_import_sales__snapshot_id__promote_post': new Set<string>([
    'erp_result/app_only_metrics/*/value',
    'erp_result/issues/*/difference',
    'erp_result/issues/*/report_value',
    'erp_result/issues/*/retail_value',
    'erp_result/metrics/*/difference',
    'erp_result/metrics/*/report_value',
    'erp_result/metrics/*/retail_value',
  ]),
  'annual_api_store_pnl_annual_get': new Set<string>([
    'annual/*/cogs',
    'annual/*/depreciation',
    'annual/*/ebit',
    'annual/*/ebitda',
    'annual/*/gross_margin',
    'annual/*/operating_costs',
    'annual/*/revenue',
  ]),
  'months_api_store_pnl_months_get': new Set<string>([
  ]),
  'overview_api_store_pnl_overview_get': new Set<string>([
    'categories/*',
    'monthly/*/cogs',
    'monthly/*/depreciation',
    'monthly/*/ebit',
    'monthly/*/ebitda',
    'monthly/*/gross_margin',
    'monthly/*/operating_costs',
    'monthly/*/revenue',
    'reconciliation/*/difference_to_net',
    'reconciliation/*/pnl_revenue',
    'reconciliation/*/pnl_to_net_sales_pct',
    'reconciliation/*/retail_sales_gross',
    'reconciliation/*/retail_sales_net',
    'stores/*/cogs',
    'stores/*/depreciation',
    'stores/*/ebit',
    'stores/*/ebitda',
    'stores/*/gross_margin',
    'stores/*/operating_costs',
    'stores/*/revenue',
    'summary/cogs',
    'summary/depreciation',
    'summary/ebit',
    'summary/ebitda',
    'summary/gross_margin',
    'summary/operating_costs',
    'summary/revenue',
  ]),
  'pnl_permissions_api_store_pnl_permissions_get': new Set<string>([
  ]),
  'regions_api_store_pnl_regions_get': new Set<string>([
  ]),
  'stores_api_store_pnl_stores_get': new Set<string>([
  ]),
  'list_stores_api_stores_get': new Set<string>([
  ]),
  'save_targets_api_stores_targets_post': new Set<string>([
  ]),
  'change_store_activity_api_stores__site_code__activity_post': new Set<string>([
  ]),
  'get_context_api_target_calculator_context_get': new Set<string>([
    'default_min_floor',
    'default_previous_month_cap_pct',
    'default_previous_month_floor_pct',
    'suggested_total_target',
  ]),
  'list_scenarios_api_target_calculator_scenarios_get': new Set<string>([
    '*/calculation_params/minimum_seasonality_base',
    '*/calculation_params/new_store_weights/*',
    '*/calculation_params/previous_month_cap_pct',
    '*/calculation_params/profitability/base_salary_default',
    '*/calculation_params/profitability/base_salary_high',
    '*/calculation_params/profitability/meal_vouchers_per_agent',
    '*/calculation_params/profitability/salary_assumed_attainment',
    '*/calculation_params/profitability/salary_pnl_factor',
    '*/calculation_params/profitability/sales_commission_rate',
    '*/calculation_params/profitability/vat_multiplier',
    '*/calculation_params/profitability/vat_rate',
    '*/calculation_params/profitability_summary/assumptions/base_salary_default',
    '*/calculation_params/profitability_summary/assumptions/base_salary_high',
    '*/calculation_params/profitability_summary/assumptions/meal_vouchers_per_agent',
    '*/calculation_params/profitability_summary/assumptions/salary_assumed_attainment',
    '*/calculation_params/profitability_summary/assumptions/salary_pnl_factor',
    '*/calculation_params/profitability_summary/assumptions/sales_commission_rate',
    '*/calculation_params/profitability_summary/assumptions/vat_multiplier',
    '*/calculation_params/profitability_summary/assumptions/vat_rate',
    '*/calculation_params/profitability_summary/break_even_total',
    '*/calculation_params/profitability_summary/forecast_total',
    '*/calculation_params/profitability_summary/operating_costs_total',
    '*/calculation_params/profitability_summary/salary_total',
    '*/calculation_params/seasonality_max',
    '*/calculation_params/seasonality_min',
    '*/calculation_params/strong_weights/*',
    '*/calculation_params/trend_adjustment_max',
    '*/calculation_params/trend_adjustment_min',
    '*/calculation_params/trend_weight',
    '*/calculation_params/weak_weights/*',
    '*/final_total',
    '*/min_floor',
    '*/previous_month_floor_pct',
    '*/proposed_total',
    '*/total_target',
  ]),
  'calculate_scenario_api_target_calculator_scenarios_calculate_post': new Set<string>([
    'calculation_params/minimum_seasonality_base',
    'calculation_params/new_store_weights/*',
    'calculation_params/previous_month_cap_pct',
    'calculation_params/profitability/base_salary_default',
    'calculation_params/profitability/base_salary_high',
    'calculation_params/profitability/meal_vouchers_per_agent',
    'calculation_params/profitability/salary_assumed_attainment',
    'calculation_params/profitability/salary_pnl_factor',
    'calculation_params/profitability/sales_commission_rate',
    'calculation_params/profitability/vat_multiplier',
    'calculation_params/profitability/vat_rate',
    'calculation_params/profitability_summary/assumptions/base_salary_default',
    'calculation_params/profitability_summary/assumptions/base_salary_high',
    'calculation_params/profitability_summary/assumptions/meal_vouchers_per_agent',
    'calculation_params/profitability_summary/assumptions/salary_assumed_attainment',
    'calculation_params/profitability_summary/assumptions/salary_pnl_factor',
    'calculation_params/profitability_summary/assumptions/sales_commission_rate',
    'calculation_params/profitability_summary/assumptions/vat_multiplier',
    'calculation_params/profitability_summary/assumptions/vat_rate',
    'calculation_params/profitability_summary/break_even_total',
    'calculation_params/profitability_summary/forecast_total',
    'calculation_params/profitability_summary/operating_costs_total',
    'calculation_params/profitability_summary/salary_total',
    'calculation_params/seasonality_max',
    'calculation_params/seasonality_min',
    'calculation_params/strong_weights/*',
    'calculation_params/trend_adjustment_max',
    'calculation_params/trend_adjustment_min',
    'calculation_params/trend_weight',
    'calculation_params/weak_weights/*',
    'final_total',
    'min_floor',
    'previous_month_floor_pct',
    'profitability_summary/assumptions/base_salary_default',
    'profitability_summary/assumptions/base_salary_high',
    'profitability_summary/assumptions/meal_vouchers_per_agent',
    'profitability_summary/assumptions/salary_assumed_attainment',
    'profitability_summary/assumptions/salary_pnl_factor',
    'profitability_summary/assumptions/sales_commission_rate',
    'profitability_summary/assumptions/vat_multiplier',
    'profitability_summary/assumptions/vat_rate',
    'profitability_summary/break_even_total',
    'profitability_summary/forecast_total',
    'profitability_summary/operating_costs_total',
    'profitability_summary/salary_total',
    'proposed_total',
    'regional_summary/*/current_forecast_total',
    'regional_summary/*/final_growth_vs_current_pct',
    'regional_summary/*/final_total',
    'regional_summary/*/floor_total',
    'regional_summary/*/last_year_base_total',
    'regional_summary/*/last_year_growth_pct',
    'regional_summary/*/last_year_target_total',
    'regional_summary/*/proposed_growth_vs_current_pct',
    'regional_summary/*/proposed_total',
    'remaining_difference',
    'rows/*/calculated_weight',
    'rows/*/calculation_details/cap_target',
    'rows/*/calculation_details/current_forecast',
    'rows/*/calculation_details/floor_target',
    'rows/*/calculation_details/raw_estimate',
    'rows/*/calculation_details/seasonality/blended_factor',
    'rows/*/calculation_details/seasonality/last_year_store_factor',
    'rows/*/calculation_details/seasonality/max',
    'rows/*/calculation_details/seasonality/min',
    'rows/*/calculation_details/seasonality/multiyear_store_factor',
    'rows/*/calculation_details/seasonality/network_factor',
    'rows/*/calculation_details/seasonality/network_years/*/base_value',
    'rows/*/calculation_details/seasonality/network_years/*/ratio',
    'rows/*/calculation_details/seasonality/network_years/*/target_value',
    'rows/*/calculation_details/seasonality/store_factor',
    'rows/*/calculation_details/seasonality/store_years/*/base_value',
    'rows/*/calculation_details/seasonality/store_years/*/ratio',
    'rows/*/calculation_details/seasonality/store_years/*/target_value',
    'rows/*/calculation_details/seasonality/used_factor',
    'rows/*/calculation_details/seasonality/weights/*',
    'rows/*/calculation_details/seasonality/zone_factor',
    'rows/*/calculation_details/seasonality/zone_years/*/base_value',
    'rows/*/calculation_details/seasonality/zone_years/*/ratio',
    'rows/*/calculation_details/seasonality/zone_years/*/target_value',
    'rows/*/calculation_details/trend/max',
    'rows/*/calculation_details/trend/min',
    'rows/*/calculation_details/trend/ratio',
    'rows/*/calculation_details/trend/raw_adjustment',
    'rows/*/calculation_details/trend/used_adjustment',
    'rows/*/calculation_details/trend/weight',
    'rows/*/cap_target',
    'rows/*/final_target',
    'rows/*/floor_target',
    'rows/*/history/*/actual_realized',
    'rows/*/history/*/attainment_pct',
    'rows/*/history/*/forecast_factor',
    'rows/*/history/*/realized',
    'rows/*/history/*/target',
    'rows/*/history/*/weight',
    'rows/*/manager_override_target',
    'rows/*/normalized_weight',
    'rows/*/profitability/accessory_margin_pct',
    'rows/*/profitability/base_salary_per_agent',
    'rows/*/profitability/break_even_gross_sales',
    'rows/*/profitability/forecast_sales',
    'rows/*/profitability/operating_costs',
    'rows/*/profitability/salary_cost_at_90_pct',
    'rows/*/proposed_target',
    'source_summary/*/actual_realized',
    'source_summary/*/attainment_pct',
    'source_summary/*/forecast_factor',
    'source_summary/*/realized',
    'source_summary/*/target',
    'total_target',
  ]),
  'get_scenario_api_target_calculator_scenarios__scenario_id__get': new Set<string>([
    'calculation_params/minimum_seasonality_base',
    'calculation_params/new_store_weights/*',
    'calculation_params/previous_month_cap_pct',
    'calculation_params/profitability/base_salary_default',
    'calculation_params/profitability/base_salary_high',
    'calculation_params/profitability/meal_vouchers_per_agent',
    'calculation_params/profitability/salary_assumed_attainment',
    'calculation_params/profitability/salary_pnl_factor',
    'calculation_params/profitability/sales_commission_rate',
    'calculation_params/profitability/vat_multiplier',
    'calculation_params/profitability/vat_rate',
    'calculation_params/profitability_summary/assumptions/base_salary_default',
    'calculation_params/profitability_summary/assumptions/base_salary_high',
    'calculation_params/profitability_summary/assumptions/meal_vouchers_per_agent',
    'calculation_params/profitability_summary/assumptions/salary_assumed_attainment',
    'calculation_params/profitability_summary/assumptions/salary_pnl_factor',
    'calculation_params/profitability_summary/assumptions/sales_commission_rate',
    'calculation_params/profitability_summary/assumptions/vat_multiplier',
    'calculation_params/profitability_summary/assumptions/vat_rate',
    'calculation_params/profitability_summary/break_even_total',
    'calculation_params/profitability_summary/forecast_total',
    'calculation_params/profitability_summary/operating_costs_total',
    'calculation_params/profitability_summary/salary_total',
    'calculation_params/seasonality_max',
    'calculation_params/seasonality_min',
    'calculation_params/strong_weights/*',
    'calculation_params/trend_adjustment_max',
    'calculation_params/trend_adjustment_min',
    'calculation_params/trend_weight',
    'calculation_params/weak_weights/*',
    'final_total',
    'min_floor',
    'previous_month_floor_pct',
    'profitability_summary/assumptions/base_salary_default',
    'profitability_summary/assumptions/base_salary_high',
    'profitability_summary/assumptions/meal_vouchers_per_agent',
    'profitability_summary/assumptions/salary_assumed_attainment',
    'profitability_summary/assumptions/salary_pnl_factor',
    'profitability_summary/assumptions/sales_commission_rate',
    'profitability_summary/assumptions/vat_multiplier',
    'profitability_summary/assumptions/vat_rate',
    'profitability_summary/break_even_total',
    'profitability_summary/forecast_total',
    'profitability_summary/operating_costs_total',
    'profitability_summary/salary_total',
    'proposed_total',
    'regional_summary/*/current_forecast_total',
    'regional_summary/*/final_growth_vs_current_pct',
    'regional_summary/*/final_total',
    'regional_summary/*/floor_total',
    'regional_summary/*/last_year_base_total',
    'regional_summary/*/last_year_growth_pct',
    'regional_summary/*/last_year_target_total',
    'regional_summary/*/proposed_growth_vs_current_pct',
    'regional_summary/*/proposed_total',
    'remaining_difference',
    'rows/*/calculated_weight',
    'rows/*/calculation_details/cap_target',
    'rows/*/calculation_details/current_forecast',
    'rows/*/calculation_details/floor_target',
    'rows/*/calculation_details/raw_estimate',
    'rows/*/calculation_details/seasonality/blended_factor',
    'rows/*/calculation_details/seasonality/last_year_store_factor',
    'rows/*/calculation_details/seasonality/max',
    'rows/*/calculation_details/seasonality/min',
    'rows/*/calculation_details/seasonality/multiyear_store_factor',
    'rows/*/calculation_details/seasonality/network_factor',
    'rows/*/calculation_details/seasonality/network_years/*/base_value',
    'rows/*/calculation_details/seasonality/network_years/*/ratio',
    'rows/*/calculation_details/seasonality/network_years/*/target_value',
    'rows/*/calculation_details/seasonality/store_factor',
    'rows/*/calculation_details/seasonality/store_years/*/base_value',
    'rows/*/calculation_details/seasonality/store_years/*/ratio',
    'rows/*/calculation_details/seasonality/store_years/*/target_value',
    'rows/*/calculation_details/seasonality/used_factor',
    'rows/*/calculation_details/seasonality/weights/*',
    'rows/*/calculation_details/seasonality/zone_factor',
    'rows/*/calculation_details/seasonality/zone_years/*/base_value',
    'rows/*/calculation_details/seasonality/zone_years/*/ratio',
    'rows/*/calculation_details/seasonality/zone_years/*/target_value',
    'rows/*/calculation_details/trend/max',
    'rows/*/calculation_details/trend/min',
    'rows/*/calculation_details/trend/ratio',
    'rows/*/calculation_details/trend/raw_adjustment',
    'rows/*/calculation_details/trend/used_adjustment',
    'rows/*/calculation_details/trend/weight',
    'rows/*/cap_target',
    'rows/*/final_target',
    'rows/*/floor_target',
    'rows/*/history/*/actual_realized',
    'rows/*/history/*/attainment_pct',
    'rows/*/history/*/forecast_factor',
    'rows/*/history/*/realized',
    'rows/*/history/*/target',
    'rows/*/history/*/weight',
    'rows/*/manager_override_target',
    'rows/*/normalized_weight',
    'rows/*/profitability/accessory_margin_pct',
    'rows/*/profitability/base_salary_per_agent',
    'rows/*/profitability/break_even_gross_sales',
    'rows/*/profitability/forecast_sales',
    'rows/*/profitability/operating_costs',
    'rows/*/profitability/salary_cost_at_90_pct',
    'rows/*/proposed_target',
    'source_summary/*/actual_realized',
    'source_summary/*/attainment_pct',
    'source_summary/*/forecast_factor',
    'source_summary/*/realized',
    'source_summary/*/target',
    'total_target',
  ]),
  'export_scenario_api_target_calculator_scenarios__scenario_id__export_get': new Set<string>([
  ]),
  'finalize_scenario_api_target_calculator_scenarios__scenario_id__finalize_post': new Set<string>([
    'calculation_params/minimum_seasonality_base',
    'calculation_params/new_store_weights/*',
    'calculation_params/previous_month_cap_pct',
    'calculation_params/profitability/base_salary_default',
    'calculation_params/profitability/base_salary_high',
    'calculation_params/profitability/meal_vouchers_per_agent',
    'calculation_params/profitability/salary_assumed_attainment',
    'calculation_params/profitability/salary_pnl_factor',
    'calculation_params/profitability/sales_commission_rate',
    'calculation_params/profitability/vat_multiplier',
    'calculation_params/profitability/vat_rate',
    'calculation_params/profitability_summary/assumptions/base_salary_default',
    'calculation_params/profitability_summary/assumptions/base_salary_high',
    'calculation_params/profitability_summary/assumptions/meal_vouchers_per_agent',
    'calculation_params/profitability_summary/assumptions/salary_assumed_attainment',
    'calculation_params/profitability_summary/assumptions/salary_pnl_factor',
    'calculation_params/profitability_summary/assumptions/sales_commission_rate',
    'calculation_params/profitability_summary/assumptions/vat_multiplier',
    'calculation_params/profitability_summary/assumptions/vat_rate',
    'calculation_params/profitability_summary/break_even_total',
    'calculation_params/profitability_summary/forecast_total',
    'calculation_params/profitability_summary/operating_costs_total',
    'calculation_params/profitability_summary/salary_total',
    'calculation_params/seasonality_max',
    'calculation_params/seasonality_min',
    'calculation_params/strong_weights/*',
    'calculation_params/trend_adjustment_max',
    'calculation_params/trend_adjustment_min',
    'calculation_params/trend_weight',
    'calculation_params/weak_weights/*',
    'final_total',
    'min_floor',
    'previous_month_floor_pct',
    'profitability_summary/assumptions/base_salary_default',
    'profitability_summary/assumptions/base_salary_high',
    'profitability_summary/assumptions/meal_vouchers_per_agent',
    'profitability_summary/assumptions/salary_assumed_attainment',
    'profitability_summary/assumptions/salary_pnl_factor',
    'profitability_summary/assumptions/sales_commission_rate',
    'profitability_summary/assumptions/vat_multiplier',
    'profitability_summary/assumptions/vat_rate',
    'profitability_summary/break_even_total',
    'profitability_summary/forecast_total',
    'profitability_summary/operating_costs_total',
    'profitability_summary/salary_total',
    'proposed_total',
    'regional_summary/*/current_forecast_total',
    'regional_summary/*/final_growth_vs_current_pct',
    'regional_summary/*/final_total',
    'regional_summary/*/floor_total',
    'regional_summary/*/last_year_base_total',
    'regional_summary/*/last_year_growth_pct',
    'regional_summary/*/last_year_target_total',
    'regional_summary/*/proposed_growth_vs_current_pct',
    'regional_summary/*/proposed_total',
    'remaining_difference',
    'rows/*/calculated_weight',
    'rows/*/calculation_details/cap_target',
    'rows/*/calculation_details/current_forecast',
    'rows/*/calculation_details/floor_target',
    'rows/*/calculation_details/raw_estimate',
    'rows/*/calculation_details/seasonality/blended_factor',
    'rows/*/calculation_details/seasonality/last_year_store_factor',
    'rows/*/calculation_details/seasonality/max',
    'rows/*/calculation_details/seasonality/min',
    'rows/*/calculation_details/seasonality/multiyear_store_factor',
    'rows/*/calculation_details/seasonality/network_factor',
    'rows/*/calculation_details/seasonality/network_years/*/base_value',
    'rows/*/calculation_details/seasonality/network_years/*/ratio',
    'rows/*/calculation_details/seasonality/network_years/*/target_value',
    'rows/*/calculation_details/seasonality/store_factor',
    'rows/*/calculation_details/seasonality/store_years/*/base_value',
    'rows/*/calculation_details/seasonality/store_years/*/ratio',
    'rows/*/calculation_details/seasonality/store_years/*/target_value',
    'rows/*/calculation_details/seasonality/used_factor',
    'rows/*/calculation_details/seasonality/weights/*',
    'rows/*/calculation_details/seasonality/zone_factor',
    'rows/*/calculation_details/seasonality/zone_years/*/base_value',
    'rows/*/calculation_details/seasonality/zone_years/*/ratio',
    'rows/*/calculation_details/seasonality/zone_years/*/target_value',
    'rows/*/calculation_details/trend/max',
    'rows/*/calculation_details/trend/min',
    'rows/*/calculation_details/trend/ratio',
    'rows/*/calculation_details/trend/raw_adjustment',
    'rows/*/calculation_details/trend/used_adjustment',
    'rows/*/calculation_details/trend/weight',
    'rows/*/cap_target',
    'rows/*/final_target',
    'rows/*/floor_target',
    'rows/*/history/*/actual_realized',
    'rows/*/history/*/attainment_pct',
    'rows/*/history/*/forecast_factor',
    'rows/*/history/*/realized',
    'rows/*/history/*/target',
    'rows/*/history/*/weight',
    'rows/*/manager_override_target',
    'rows/*/normalized_weight',
    'rows/*/profitability/accessory_margin_pct',
    'rows/*/profitability/base_salary_per_agent',
    'rows/*/profitability/break_even_gross_sales',
    'rows/*/profitability/forecast_sales',
    'rows/*/profitability/operating_costs',
    'rows/*/profitability/salary_cost_at_90_pct',
    'rows/*/proposed_target',
    'source_summary/*/actual_realized',
    'source_summary/*/attainment_pct',
    'source_summary/*/forecast_factor',
    'source_summary/*/realized',
    'source_summary/*/target',
    'total_target',
  ]),
  'update_final_targets_api_target_calculator_scenarios__scenario_id__rows_patch': new Set<string>([
    'calculation_params/minimum_seasonality_base',
    'calculation_params/new_store_weights/*',
    'calculation_params/previous_month_cap_pct',
    'calculation_params/profitability/base_salary_default',
    'calculation_params/profitability/base_salary_high',
    'calculation_params/profitability/meal_vouchers_per_agent',
    'calculation_params/profitability/salary_assumed_attainment',
    'calculation_params/profitability/salary_pnl_factor',
    'calculation_params/profitability/sales_commission_rate',
    'calculation_params/profitability/vat_multiplier',
    'calculation_params/profitability/vat_rate',
    'calculation_params/profitability_summary/assumptions/base_salary_default',
    'calculation_params/profitability_summary/assumptions/base_salary_high',
    'calculation_params/profitability_summary/assumptions/meal_vouchers_per_agent',
    'calculation_params/profitability_summary/assumptions/salary_assumed_attainment',
    'calculation_params/profitability_summary/assumptions/salary_pnl_factor',
    'calculation_params/profitability_summary/assumptions/sales_commission_rate',
    'calculation_params/profitability_summary/assumptions/vat_multiplier',
    'calculation_params/profitability_summary/assumptions/vat_rate',
    'calculation_params/profitability_summary/break_even_total',
    'calculation_params/profitability_summary/forecast_total',
    'calculation_params/profitability_summary/operating_costs_total',
    'calculation_params/profitability_summary/salary_total',
    'calculation_params/seasonality_max',
    'calculation_params/seasonality_min',
    'calculation_params/strong_weights/*',
    'calculation_params/trend_adjustment_max',
    'calculation_params/trend_adjustment_min',
    'calculation_params/trend_weight',
    'calculation_params/weak_weights/*',
    'final_total',
    'min_floor',
    'previous_month_floor_pct',
    'profitability_summary/assumptions/base_salary_default',
    'profitability_summary/assumptions/base_salary_high',
    'profitability_summary/assumptions/meal_vouchers_per_agent',
    'profitability_summary/assumptions/salary_assumed_attainment',
    'profitability_summary/assumptions/salary_pnl_factor',
    'profitability_summary/assumptions/sales_commission_rate',
    'profitability_summary/assumptions/vat_multiplier',
    'profitability_summary/assumptions/vat_rate',
    'profitability_summary/break_even_total',
    'profitability_summary/forecast_total',
    'profitability_summary/operating_costs_total',
    'profitability_summary/salary_total',
    'proposed_total',
    'regional_summary/*/current_forecast_total',
    'regional_summary/*/final_growth_vs_current_pct',
    'regional_summary/*/final_total',
    'regional_summary/*/floor_total',
    'regional_summary/*/last_year_base_total',
    'regional_summary/*/last_year_growth_pct',
    'regional_summary/*/last_year_target_total',
    'regional_summary/*/proposed_growth_vs_current_pct',
    'regional_summary/*/proposed_total',
    'remaining_difference',
    'rows/*/calculated_weight',
    'rows/*/calculation_details/cap_target',
    'rows/*/calculation_details/current_forecast',
    'rows/*/calculation_details/floor_target',
    'rows/*/calculation_details/raw_estimate',
    'rows/*/calculation_details/seasonality/blended_factor',
    'rows/*/calculation_details/seasonality/last_year_store_factor',
    'rows/*/calculation_details/seasonality/max',
    'rows/*/calculation_details/seasonality/min',
    'rows/*/calculation_details/seasonality/multiyear_store_factor',
    'rows/*/calculation_details/seasonality/network_factor',
    'rows/*/calculation_details/seasonality/network_years/*/base_value',
    'rows/*/calculation_details/seasonality/network_years/*/ratio',
    'rows/*/calculation_details/seasonality/network_years/*/target_value',
    'rows/*/calculation_details/seasonality/store_factor',
    'rows/*/calculation_details/seasonality/store_years/*/base_value',
    'rows/*/calculation_details/seasonality/store_years/*/ratio',
    'rows/*/calculation_details/seasonality/store_years/*/target_value',
    'rows/*/calculation_details/seasonality/used_factor',
    'rows/*/calculation_details/seasonality/weights/*',
    'rows/*/calculation_details/seasonality/zone_factor',
    'rows/*/calculation_details/seasonality/zone_years/*/base_value',
    'rows/*/calculation_details/seasonality/zone_years/*/ratio',
    'rows/*/calculation_details/seasonality/zone_years/*/target_value',
    'rows/*/calculation_details/trend/max',
    'rows/*/calculation_details/trend/min',
    'rows/*/calculation_details/trend/ratio',
    'rows/*/calculation_details/trend/raw_adjustment',
    'rows/*/calculation_details/trend/used_adjustment',
    'rows/*/calculation_details/trend/weight',
    'rows/*/cap_target',
    'rows/*/final_target',
    'rows/*/floor_target',
    'rows/*/history/*/actual_realized',
    'rows/*/history/*/attainment_pct',
    'rows/*/history/*/forecast_factor',
    'rows/*/history/*/realized',
    'rows/*/history/*/target',
    'rows/*/history/*/weight',
    'rows/*/manager_override_target',
    'rows/*/normalized_weight',
    'rows/*/profitability/accessory_margin_pct',
    'rows/*/profitability/base_salary_per_agent',
    'rows/*/profitability/break_even_gross_sales',
    'rows/*/profitability/forecast_sales',
    'rows/*/profitability/operating_costs',
    'rows/*/profitability/salary_cost_at_90_pct',
    'rows/*/proposed_target',
    'source_summary/*/actual_realized',
    'source_summary/*/attainment_pct',
    'source_summary/*/forecast_factor',
    'source_summary/*/realized',
    'source_summary/*/target',
    'total_target',
  ]),
  'get_store_detail_api_target_calculator_scenarios__scenario_id__stores__site_code__get': new Set<string>([
    'agents/*/avg_receipt',
    'agents/*/bon2acc_pct',
    'agents/*/focus_pct',
    'agents/*/sales_16m',
    'agents/*/sales_share_pct',
    'agents/*/total_sales',
    'avg_sales_16m',
    'best_month/avg_receipt',
    'best_month/bon2acc_pct',
    'best_month/focus_pct',
    'best_month/target_pct',
    'best_month/target_value',
    'best_month/total_sales',
    'final_target',
    'history/*/avg_receipt',
    'history/*/bon2acc_pct',
    'history/*/focus_pct',
    'history/*/target_pct',
    'history/*/target_value',
    'history/*/total_sales',
    'latest/avg_receipt',
    'latest/bon2acc_pct',
    'latest/focus_pct',
    'latest/target_pct',
    'latest/target_value',
    'latest/total_sales',
    'proposed_target',
  ]),
  'get_tasks_api_tasks_get': new Set<string>([
  ]),
  'post_task_api_tasks_post': new Set<string>([
  ]),
  'remove_task_api_tasks__task_id__delete': new Set<string>([
  ]),
  'patch_task_api_tasks__task_id__patch': new Set<string>([
  ]),
  'get_visits_report_api_visits_report_get': new Set<string>([
  ]),
  'get_visit_photo_api_visits_report_photo__visit_id___filename__get': new Set<string>([
  ]),
  'get_visits_tree_api_visits_report_tree_get': new Set<string>([
  ]),
  'get_visit_detail_api_visits_report_visit__visit_id__get': new Set<string>([
  ]),
  'session_status_auth_session_get': new Set<string>([
  ]),
  'session_login_auth_session_login_get': new Set<string>([
  ]),
  'session_logout_auth_session_logout_post': new Set<string>([
  ]),
  'metrics_metrics_get': new Set<string>([
  ]),
  'agent_history_by_retail_code_salarii_agents_history_by_retail_code_get': new Set<string>([
  ]),
  'agents_summary_salarii_agents_summary_get': new Set<string>([
  ]),
  'agent_history_salarii_agents__person_id__history_get': new Set<string>([
  ]),
  'audit_salary_export_salarii_audit_export_post': new Set<string>([
  ]),
  'salarii_evolution_salarii_evolution_get': new Set<string>([
  ]),
  'salarii_overview_salarii_overview_get': new Set<string>([
  ]),
  'list_records_salarii_records_get': new Set<string>([
  ]),
  'salarii_stores_salarii_stores_get': new Set<string>([
  ]),
  'salarii_summary_salarii_summary_get': new Set<string>([
  ]),
  'salarii_trend_salarii_trend_get': new Set<string>([
  ]),
};

export const RETAIL_DATE_PATHS: { readonly [Id in RetailOperationId]: ReadonlySet<string> } = {
  'get_agent_evaluation_api_agents_evaluation_get': new Set<string>([
  ]),
  'get_agent_evaluation_v2_api_agents_evaluation_v2_get': new Set<string>([
  ]),
  'get_agent_history_api_agents_history_get': new Set<string>([
  ]),
  'get_agents_list_api_agents_list_get': new Set<string>([
  ]),
  'get_agents_movement_api_agents_movement_get': new Set<string>([
  ]),
  'get_agents_overview_api_agents_overview_get': new Set<string>([
  ]),
  'get_agent_profile_api_agents_profile_get': new Set<string>([
  ]),
  'get_stores_coverage_api_agents_stores_coverage_get': new Set<string>([
  ]),
  'get_current_ai_forecast_api_ai_forecast_current_get': new Set<string>([
    'daily/*/forecast_date',
    'summary/actual_last_date',
  ]),
  'get_rolling_12_ai_forecast_api_ai_forecast_rolling_12_get': new Set<string>([
  ]),
  'get_focus_history_api_campaigns_history_get': new Set<string>([
  ]),
  'get_campaign_overview_api_campaigns_overview_get': new Set<string>([
  ]),
  'get_promotions_incentives_api_campaigns_promotions_incentives_get': new Set<string>([
  ]),
  'get_active_contest_api_contests_active_get': new Set<string>([
  ]),
  'get_active_contests_api_contests_active_all_get': new Set<string>([
  ]),
  'get_alerts_api_crm_alerts_get': new Set<string>([
  ]),
  'get_scores_api_crm_scores_get': new Set<string>([
  ]),
  'recalculate_scores_api_crm_scores_recalculate_post': new Set<string>([
  ]),
  'get_dashboard_all_api_dashboard_all_get': new Set<string>([
    'daily/*/sale_date',
    'daily_last_year/*/sale_date',
    'summary/last_sale_date',
  ]),
  'get_dashboard_all_batch_api_dashboard_all_batch_post': new Set<string>([
    'results/*/daily/*/sale_date',
    'results/*/daily_last_year/*/sale_date',
    'results/*/summary/last_sale_date',
  ]),
  'get_daily_sales_api_dashboard_daily_get': new Set<string>([
    '*/sale_date',
  ]),
  'get_monthly_history_api_dashboard_history_get': new Set<string>([
  ]),
  'get_dashboard_history_details_batch_api_dashboard_history_details_batch_post': new Set<string>([
    'results/*/daily/*/sale_date',
    'results/*/daily_last_year/*/sale_date',
    'results/*/summary/last_sale_date',
  ]),
  'get_history_by_year_api_dashboard_history_year_get': new Set<string>([
  ]),
  'get_performance_detail_api_dashboard_performance_detail_get': new Set<string>([
    'context_summary/last_sale_date',
    'daily/*/sale_date',
    'summary/last_sale_date',
  ]),
  'get_premium_glass_api_dashboard_premium_glass_get': new Set<string>([
  ]),
  'get_special_cards_api_dashboard_special_cards_get': new Set<string>([
  ]),
  'get_summary_api_dashboard_summary_get': new Set<string>([
    'last_sale_date',
  ]),
  'get_catalog_api_exports_catalog_get': new Set<string>([
  ]),
  'download_export_api_exports_download_post': new Set<string>([
  ]),
  'create_export_operation_api_exports_operations_post': new Set<string>([
  ]),
  'get_resumable_export_operation_api_exports_operations_resumable_get': new Set<string>([
  ]),
  'get_export_operation_api_exports_operations__operation_id__get': new Set<string>([
  ]),
  'cancel_export_operation_api_exports_operations__operation_id__cancel_post': new Set<string>([
  ]),
  'download_export_operation_api_exports_operations__operation_id__download_get': new Set<string>([
  ]),
  'preview_export_api_exports_preview_post': new Set<string>([
  ]),
  'get_available_months_api_filters_months_get': new Set<string>([
  ]),
  'get_filter_options_api_filters_options_get': new Set<string>([
  ]),
  'grile_agent_targets_diff_api_grile_agent_targets_diff_post': new Set<string>([
  ]),
  'grile_agent_targets_operation_api_grile_agent_targets_operations__operation_id__get': new Set<string>([
  ]),
  'grile_agent_targets_sync_api_grile_agent_targets_sync_post': new Set<string>([
  ]),
  'grile_monthly_download_api_grile_monthly_download__kind___month__get': new Set<string>([
  ]),
  'grile_monthly_job_api_grile_monthly_job__job_id__get': new Set<string>([
  ]),
  'grile_monthly_manifest_approve_api_grile_monthly_manifests__manifest_id__approve_post': new Set<string>([
  ]),
  'grile_monthly_manifest_api_grile_monthly_manifests__month__get': new Set<string>([
  ]),
  'grile_monthly_permissions_api_grile_monthly_permissions_get': new Set<string>([
  ]),
  'grile_monthly_run_api_grile_monthly_run_post': new Set<string>([
  ]),
  'grile_overview_api_grile_overview_get': new Set<string>([
    'managers/*/team_leaders/*/firms/*/stores/*/completion_as_of',
    'managers/*/team_leaders/*/firms/*/stores/*/db_max_sale_date',
  ]),
  'grile_run_api_grile_run_post': new Set<string>([
  ]),
  'grile_run_status_api_grile_run_status_get': new Set<string>([
  ]),
  'grile_store_refresh_operation_api_grile_store_refreshes__operation_id__get': new Set<string>([
  ]),
  'grile_store_refresh_api_grile_stores__site_code__refresh_post': new Set<string>([
  ]),
  'get_asm_perf_api_hr_asm_performance_get': new Set<string>([
  ]),
  'get_asm_perf_history_api_hr_asm_performance__asm_name__history_get': new Set<string>([
  ]),
  'get_asm_salary_api_hr_asm_salary__asm_name__get': new Set<string>([
  ]),
  'get_leave_requests_api_hr_leave_requests_get': new Set<string>([
  ]),
  'post_leave_request_api_hr_leave_requests_post': new Set<string>([
  ]),
  'patch_leave_request_api_hr_leave_requests__request_id__patch': new Set<string>([
  ]),
  'get_manager_overview_api_hr_manager_overview_get': new Set<string>([
  ]),
  'get_performance_api_hr_performance__agent_name__get': new Set<string>([
  ]),
  'reconcile_erp_report_file_api_import_erp_reconciliation_post': new Set<string>([
    'erp_result/report_cutoff_date',
    'erp_result/retail_cutoff_date',
    'promo_result/cutoff_date',
    'result/manifest/cutoff_date',
    'result/manifest/max_sale_date',
    'result/manifest/site_days/*/sale_date',
  ]),
  'get_import_history_api_import_history_get': new Set<string>([
    '*/upload_date',
  ]),
  'get_import_job_status_api_import_jobs__job_id__get': new Set<string>([
    'erp_result/report_cutoff_date',
    'erp_result/retail_cutoff_date',
    'promo_result/cutoff_date',
    'result/manifest/cutoff_date',
    'result/manifest/max_sale_date',
    'result/manifest/site_days/*/sale_date',
  ]),
  'upload_promo_actuals_file_api_import_promo_actuals_post': new Set<string>([
    'erp_result/report_cutoff_date',
    'erp_result/retail_cutoff_date',
    'promo_result/cutoff_date',
    'result/manifest/cutoff_date',
    'result/manifest/max_sale_date',
    'result/manifest/site_days/*/sale_date',
  ]),
  'upload_sales_file_api_import_sales_post': new Set<string>([
    'erp_result/report_cutoff_date',
    'erp_result/retail_cutoff_date',
    'promo_result/cutoff_date',
    'result/manifest/cutoff_date',
    'result/manifest/max_sale_date',
    'result/manifest/site_days/*/sale_date',
  ]),
  'promote_sales_generation_api_import_sales__snapshot_id__promote_post': new Set<string>([
    'erp_result/report_cutoff_date',
    'erp_result/retail_cutoff_date',
    'promo_result/cutoff_date',
    'result/manifest/cutoff_date',
    'result/manifest/max_sale_date',
    'result/manifest/site_days/*/sale_date',
  ]),
  'annual_api_store_pnl_annual_get': new Set<string>([
  ]),
  'months_api_store_pnl_months_get': new Set<string>([
  ]),
  'overview_api_store_pnl_overview_get': new Set<string>([
  ]),
  'pnl_permissions_api_store_pnl_permissions_get': new Set<string>([
  ]),
  'regions_api_store_pnl_regions_get': new Set<string>([
  ]),
  'stores_api_store_pnl_stores_get': new Set<string>([
  ]),
  'list_stores_api_stores_get': new Set<string>([
  ]),
  'save_targets_api_stores_targets_post': new Set<string>([
  ]),
  'change_store_activity_api_stores__site_code__activity_post': new Set<string>([
  ]),
  'get_context_api_target_calculator_context_get': new Set<string>([
  ]),
  'list_scenarios_api_target_calculator_scenarios_get': new Set<string>([
  ]),
  'calculate_scenario_api_target_calculator_scenarios_calculate_post': new Set<string>([
  ]),
  'get_scenario_api_target_calculator_scenarios__scenario_id__get': new Set<string>([
  ]),
  'export_scenario_api_target_calculator_scenarios__scenario_id__export_get': new Set<string>([
  ]),
  'finalize_scenario_api_target_calculator_scenarios__scenario_id__finalize_post': new Set<string>([
  ]),
  'update_final_targets_api_target_calculator_scenarios__scenario_id__rows_patch': new Set<string>([
  ]),
  'get_store_detail_api_target_calculator_scenarios__scenario_id__stores__site_code__get': new Set<string>([
  ]),
  'get_tasks_api_tasks_get': new Set<string>([
  ]),
  'post_task_api_tasks_post': new Set<string>([
  ]),
  'remove_task_api_tasks__task_id__delete': new Set<string>([
  ]),
  'patch_task_api_tasks__task_id__patch': new Set<string>([
  ]),
  'get_visits_report_api_visits_report_get': new Set<string>([
  ]),
  'get_visit_photo_api_visits_report_photo__visit_id___filename__get': new Set<string>([
  ]),
  'get_visits_tree_api_visits_report_tree_get': new Set<string>([
  ]),
  'get_visit_detail_api_visits_report_visit__visit_id__get': new Set<string>([
  ]),
  'session_status_auth_session_get': new Set<string>([
  ]),
  'session_login_auth_session_login_get': new Set<string>([
  ]),
  'session_logout_auth_session_logout_post': new Set<string>([
  ]),
  'metrics_metrics_get': new Set<string>([
  ]),
  'agent_history_by_retail_code_salarii_agents_history_by_retail_code_get': new Set<string>([
  ]),
  'agents_summary_salarii_agents_summary_get': new Set<string>([
  ]),
  'agent_history_salarii_agents__person_id__history_get': new Set<string>([
  ]),
  'audit_salary_export_salarii_audit_export_post': new Set<string>([
  ]),
  'salarii_evolution_salarii_evolution_get': new Set<string>([
  ]),
  'salarii_overview_salarii_overview_get': new Set<string>([
  ]),
  'list_records_salarii_records_get': new Set<string>([
  ]),
  'salarii_stores_salarii_stores_get': new Set<string>([
  ]),
  'salarii_summary_salarii_summary_get': new Set<string>([
  ]),
  'salarii_trend_salarii_trend_get': new Set<string>([
  ]),
};

export const RETAIL_DATETIME_PATHS: { readonly [Id in RetailOperationId]: ReadonlySet<string> } = {
  'get_agent_evaluation_api_agents_evaluation_get': new Set<string>([
  ]),
  'get_agent_evaluation_v2_api_agents_evaluation_v2_get': new Set<string>([
  ]),
  'get_agent_history_api_agents_history_get': new Set<string>([
  ]),
  'get_agents_list_api_agents_list_get': new Set<string>([
  ]),
  'get_agents_movement_api_agents_movement_get': new Set<string>([
  ]),
  'get_agents_overview_api_agents_overview_get': new Set<string>([
  ]),
  'get_agent_profile_api_agents_profile_get': new Set<string>([
  ]),
  'get_stores_coverage_api_agents_stores_coverage_get': new Set<string>([
  ]),
  'get_current_ai_forecast_api_ai_forecast_current_get': new Set<string>([
    'run/generated_at',
  ]),
  'get_rolling_12_ai_forecast_api_ai_forecast_rolling_12_get': new Set<string>([
    'runs/*/generated_at',
  ]),
  'get_focus_history_api_campaigns_history_get': new Set<string>([
  ]),
  'get_campaign_overview_api_campaigns_overview_get': new Set<string>([
  ]),
  'get_promotions_incentives_api_campaigns_promotions_incentives_get': new Set<string>([
  ]),
  'get_active_contest_api_contests_active_get': new Set<string>([
  ]),
  'get_active_contests_api_contests_active_all_get': new Set<string>([
  ]),
  'get_alerts_api_crm_alerts_get': new Set<string>([
  ]),
  'get_scores_api_crm_scores_get': new Set<string>([
  ]),
  'recalculate_scores_api_crm_scores_recalculate_post': new Set<string>([
  ]),
  'get_dashboard_all_api_dashboard_all_get': new Set<string>([
  ]),
  'get_dashboard_all_batch_api_dashboard_all_batch_post': new Set<string>([
  ]),
  'get_daily_sales_api_dashboard_daily_get': new Set<string>([
  ]),
  'get_monthly_history_api_dashboard_history_get': new Set<string>([
  ]),
  'get_dashboard_history_details_batch_api_dashboard_history_details_batch_post': new Set<string>([
  ]),
  'get_history_by_year_api_dashboard_history_year_get': new Set<string>([
  ]),
  'get_performance_detail_api_dashboard_performance_detail_get': new Set<string>([
  ]),
  'get_premium_glass_api_dashboard_premium_glass_get': new Set<string>([
  ]),
  'get_special_cards_api_dashboard_special_cards_get': new Set<string>([
  ]),
  'get_summary_api_dashboard_summary_get': new Set<string>([
  ]),
  'get_catalog_api_exports_catalog_get': new Set<string>([
  ]),
  'download_export_api_exports_download_post': new Set<string>([
  ]),
  'create_export_operation_api_exports_operations_post': new Set<string>([
    'created_at',
    'expires_at',
    'finished_at',
    'started_at',
  ]),
  'get_resumable_export_operation_api_exports_operations_resumable_get': new Set<string>([
    'created_at',
    'expires_at',
    'finished_at',
    'started_at',
  ]),
  'get_export_operation_api_exports_operations__operation_id__get': new Set<string>([
    'created_at',
    'expires_at',
    'finished_at',
    'started_at',
  ]),
  'cancel_export_operation_api_exports_operations__operation_id__cancel_post': new Set<string>([
    'created_at',
    'expires_at',
    'finished_at',
    'started_at',
  ]),
  'download_export_operation_api_exports_operations__operation_id__download_get': new Set<string>([
  ]),
  'preview_export_api_exports_preview_post': new Set<string>([
  ]),
  'get_available_months_api_filters_months_get': new Set<string>([
  ]),
  'get_filter_options_api_filters_options_get': new Set<string>([
  ]),
  'grile_agent_targets_diff_api_grile_agent_targets_diff_post': new Set<string>([
    'operation/created_at',
    'operation/finished_at',
    'operation/started_at',
  ]),
  'grile_agent_targets_operation_api_grile_agent_targets_operations__operation_id__get': new Set<string>([
    'operation/created_at',
    'operation/finished_at',
    'operation/started_at',
  ]),
  'grile_agent_targets_sync_api_grile_agent_targets_sync_post': new Set<string>([
    'operation/created_at',
    'operation/finished_at',
    'operation/started_at',
  ]),
  'grile_monthly_download_api_grile_monthly_download__kind___month__get': new Set<string>([
  ]),
  'grile_monthly_job_api_grile_monthly_job__job_id__get': new Set<string>([
  ]),
  'grile_monthly_manifest_approve_api_grile_monthly_manifests__manifest_id__approve_post': new Set<string>([
    'manifest/approved_at',
    'manifest/consumed_at',
    'manifest/created_at',
    'manifest/verified_at',
  ]),
  'grile_monthly_manifest_api_grile_monthly_manifests__month__get': new Set<string>([
    'manifest/approved_at',
    'manifest/consumed_at',
    'manifest/created_at',
    'manifest/verified_at',
  ]),
  'grile_monthly_permissions_api_grile_monthly_permissions_get': new Set<string>([
  ]),
  'grile_monthly_run_api_grile_monthly_run_post': new Set<string>([
  ]),
  'grile_overview_api_grile_overview_get': new Set<string>([
    'managers/*/team_leaders/*/firms/*/stores/*/checked_at',
    'managers/*/team_leaders/*/firms/*/stores/*/last_edit',
    'managers/*/team_leaders/*/firms/*/stores/*/provider_status/last_attempt_at',
    'managers/*/team_leaders/*/firms/*/stores/*/provider_status/last_error_at',
    'managers/*/team_leaders/*/firms/*/stores/*/provider_status/last_success_at',
    'run/created_at',
    'run/finished_at',
    'run/heartbeat_at',
    'run/started_at',
  ]),
  'grile_run_api_grile_run_post': new Set<string>([
    'run/created_at',
    'run/finished_at',
    'run/heartbeat_at',
    'run/started_at',
  ]),
  'grile_run_status_api_grile_run_status_get': new Set<string>([
    'run/created_at',
    'run/finished_at',
    'run/heartbeat_at',
    'run/started_at',
  ]),
  'grile_store_refresh_operation_api_grile_store_refreshes__operation_id__get': new Set<string>([
    'operation/created_at',
    'operation/finished_at',
    'operation/heartbeat_at',
    'operation/started_at',
  ]),
  'grile_store_refresh_api_grile_stores__site_code__refresh_post': new Set<string>([
  ]),
  'get_asm_perf_api_hr_asm_performance_get': new Set<string>([
  ]),
  'get_asm_perf_history_api_hr_asm_performance__asm_name__history_get': new Set<string>([
  ]),
  'get_asm_salary_api_hr_asm_salary__asm_name__get': new Set<string>([
  ]),
  'get_leave_requests_api_hr_leave_requests_get': new Set<string>([
  ]),
  'post_leave_request_api_hr_leave_requests_post': new Set<string>([
  ]),
  'patch_leave_request_api_hr_leave_requests__request_id__patch': new Set<string>([
  ]),
  'get_manager_overview_api_hr_manager_overview_get': new Set<string>([
  ]),
  'get_performance_api_hr_performance__agent_name__get': new Set<string>([
  ]),
  'reconcile_erp_report_file_api_import_erp_reconciliation_post': new Set<string>([
  ]),
  'get_import_history_api_import_history_get': new Set<string>([
    '*/created_at',
    '*/finished_at',
  ]),
  'get_import_job_status_api_import_jobs__job_id__get': new Set<string>([
  ]),
  'upload_promo_actuals_file_api_import_promo_actuals_post': new Set<string>([
  ]),
  'upload_sales_file_api_import_sales_post': new Set<string>([
  ]),
  'promote_sales_generation_api_import_sales__snapshot_id__promote_post': new Set<string>([
  ]),
  'annual_api_store_pnl_annual_get': new Set<string>([
  ]),
  'months_api_store_pnl_months_get': new Set<string>([
  ]),
  'overview_api_store_pnl_overview_get': new Set<string>([
  ]),
  'pnl_permissions_api_store_pnl_permissions_get': new Set<string>([
  ]),
  'regions_api_store_pnl_regions_get': new Set<string>([
  ]),
  'stores_api_store_pnl_stores_get': new Set<string>([
  ]),
  'list_stores_api_stores_get': new Set<string>([
  ]),
  'save_targets_api_stores_targets_post': new Set<string>([
  ]),
  'change_store_activity_api_stores__site_code__activity_post': new Set<string>([
  ]),
  'get_context_api_target_calculator_context_get': new Set<string>([
  ]),
  'list_scenarios_api_target_calculator_scenarios_get': new Set<string>([
  ]),
  'calculate_scenario_api_target_calculator_scenarios_calculate_post': new Set<string>([
  ]),
  'get_scenario_api_target_calculator_scenarios__scenario_id__get': new Set<string>([
  ]),
  'export_scenario_api_target_calculator_scenarios__scenario_id__export_get': new Set<string>([
  ]),
  'finalize_scenario_api_target_calculator_scenarios__scenario_id__finalize_post': new Set<string>([
  ]),
  'update_final_targets_api_target_calculator_scenarios__scenario_id__rows_patch': new Set<string>([
  ]),
  'get_store_detail_api_target_calculator_scenarios__scenario_id__stores__site_code__get': new Set<string>([
  ]),
  'get_tasks_api_tasks_get': new Set<string>([
  ]),
  'post_task_api_tasks_post': new Set<string>([
  ]),
  'remove_task_api_tasks__task_id__delete': new Set<string>([
  ]),
  'patch_task_api_tasks__task_id__patch': new Set<string>([
  ]),
  'get_visits_report_api_visits_report_get': new Set<string>([
  ]),
  'get_visit_photo_api_visits_report_photo__visit_id___filename__get': new Set<string>([
  ]),
  'get_visits_tree_api_visits_report_tree_get': new Set<string>([
  ]),
  'get_visit_detail_api_visits_report_visit__visit_id__get': new Set<string>([
  ]),
  'session_status_auth_session_get': new Set<string>([
  ]),
  'session_login_auth_session_login_get': new Set<string>([
  ]),
  'session_logout_auth_session_logout_post': new Set<string>([
  ]),
  'metrics_metrics_get': new Set<string>([
  ]),
  'agent_history_by_retail_code_salarii_agents_history_by_retail_code_get': new Set<string>([
  ]),
  'agents_summary_salarii_agents_summary_get': new Set<string>([
  ]),
  'agent_history_salarii_agents__person_id__history_get': new Set<string>([
  ]),
  'audit_salary_export_salarii_audit_export_post': new Set<string>([
  ]),
  'salarii_evolution_salarii_evolution_get': new Set<string>([
  ]),
  'salarii_overview_salarii_overview_get': new Set<string>([
  ]),
  'list_records_salarii_records_get': new Set<string>([
  ]),
  'salarii_stores_salarii_stores_get': new Set<string>([
  ]),
  'salarii_summary_salarii_summary_get': new Set<string>([
  ]),
  'salarii_trend_salarii_trend_get': new Set<string>([
  ]),
};

export const RETAIL_OPERATION_ROUTES = {
  'get_agent_evaluation_api_agents_evaluation_get': { method: 'get', path: '/api/agents/evaluation', responseType: 'json' },
  'get_agent_evaluation_v2_api_agents_evaluation_v2_get': { method: 'get', path: '/api/agents/evaluation-v2', responseType: 'json' },
  'get_agent_history_api_agents_history_get': { method: 'get', path: '/api/agents/history', responseType: 'json' },
  'get_agents_list_api_agents_list_get': { method: 'get', path: '/api/agents/list', responseType: 'json' },
  'get_agents_movement_api_agents_movement_get': { method: 'get', path: '/api/agents/movement', responseType: 'json' },
  'get_agents_overview_api_agents_overview_get': { method: 'get', path: '/api/agents/overview', responseType: 'json' },
  'get_agent_profile_api_agents_profile_get': { method: 'get', path: '/api/agents/profile', responseType: 'json' },
  'get_stores_coverage_api_agents_stores_coverage_get': { method: 'get', path: '/api/agents/stores-coverage', responseType: 'json' },
  'get_current_ai_forecast_api_ai_forecast_current_get': { method: 'get', path: '/api/ai-forecast/current', responseType: 'json' },
  'get_rolling_12_ai_forecast_api_ai_forecast_rolling_12_get': { method: 'get', path: '/api/ai-forecast/rolling-12', responseType: 'json' },
  'get_focus_history_api_campaigns_history_get': { method: 'get', path: '/api/campaigns/history', responseType: 'json' },
  'get_campaign_overview_api_campaigns_overview_get': { method: 'get', path: '/api/campaigns/overview', responseType: 'json' },
  'get_promotions_incentives_api_campaigns_promotions_incentives_get': { method: 'get', path: '/api/campaigns/promotions-incentives', responseType: 'json' },
  'get_active_contest_api_contests_active_get': { method: 'get', path: '/api/contests/active', responseType: 'json' },
  'get_active_contests_api_contests_active_all_get': { method: 'get', path: '/api/contests/active/all', responseType: 'json' },
  'get_alerts_api_crm_alerts_get': { method: 'get', path: '/api/crm/alerts', responseType: 'json' },
  'get_scores_api_crm_scores_get': { method: 'get', path: '/api/crm/scores', responseType: 'json' },
  'recalculate_scores_api_crm_scores_recalculate_post': { method: 'post', path: '/api/crm/scores/recalculate', responseType: 'json' },
  'get_dashboard_all_api_dashboard_all_get': { method: 'get', path: '/api/dashboard/all', responseType: 'json' },
  'get_dashboard_all_batch_api_dashboard_all_batch_post': { method: 'post', path: '/api/dashboard/all-batch', responseType: 'json' },
  'get_daily_sales_api_dashboard_daily_get': { method: 'get', path: '/api/dashboard/daily', responseType: 'json' },
  'get_monthly_history_api_dashboard_history_get': { method: 'get', path: '/api/dashboard/history', responseType: 'json' },
  'get_dashboard_history_details_batch_api_dashboard_history_details_batch_post': { method: 'post', path: '/api/dashboard/history-details-batch', responseType: 'json' },
  'get_history_by_year_api_dashboard_history_year_get': { method: 'get', path: '/api/dashboard/history-year', responseType: 'json' },
  'get_performance_detail_api_dashboard_performance_detail_get': { method: 'get', path: '/api/dashboard/performance-detail', responseType: 'json' },
  'get_premium_glass_api_dashboard_premium_glass_get': { method: 'get', path: '/api/dashboard/premium-glass', responseType: 'json' },
  'get_special_cards_api_dashboard_special_cards_get': { method: 'get', path: '/api/dashboard/special-cards', responseType: 'json' },
  'get_summary_api_dashboard_summary_get': { method: 'get', path: '/api/dashboard/summary', responseType: 'json' },
  'get_catalog_api_exports_catalog_get': { method: 'get', path: '/api/exports/catalog', responseType: 'json' },
  'download_export_api_exports_download_post': { method: 'post', path: '/api/exports/download', responseType: 'blob' },
  'create_export_operation_api_exports_operations_post': { method: 'post', path: '/api/exports/operations', responseType: 'json' },
  'get_resumable_export_operation_api_exports_operations_resumable_get': { method: 'get', path: '/api/exports/operations/resumable', responseType: 'json' },
  'get_export_operation_api_exports_operations__operation_id__get': { method: 'get', path: '/api/exports/operations/{operation_id}', responseType: 'json' },
  'cancel_export_operation_api_exports_operations__operation_id__cancel_post': { method: 'post', path: '/api/exports/operations/{operation_id}/cancel', responseType: 'json' },
  'download_export_operation_api_exports_operations__operation_id__download_get': { method: 'get', path: '/api/exports/operations/{operation_id}/download', responseType: 'blob' },
  'preview_export_api_exports_preview_post': { method: 'post', path: '/api/exports/preview', responseType: 'json' },
  'get_available_months_api_filters_months_get': { method: 'get', path: '/api/filters/months', responseType: 'json' },
  'get_filter_options_api_filters_options_get': { method: 'get', path: '/api/filters/options', responseType: 'json' },
  'grile_agent_targets_diff_api_grile_agent_targets_diff_post': { method: 'post', path: '/api/grile/agent-targets/diff', responseType: 'json' },
  'grile_agent_targets_operation_api_grile_agent_targets_operations__operation_id__get': { method: 'get', path: '/api/grile/agent-targets/operations/{operation_id}', responseType: 'json' },
  'grile_agent_targets_sync_api_grile_agent_targets_sync_post': { method: 'post', path: '/api/grile/agent-targets/sync', responseType: 'json' },
  'grile_monthly_download_api_grile_monthly_download__kind___month__get': { method: 'get', path: '/api/grile/monthly/download/{kind}/{month}', responseType: 'json' },
  'grile_monthly_job_api_grile_monthly_job__job_id__get': { method: 'get', path: '/api/grile/monthly/job/{job_id}', responseType: 'json' },
  'grile_monthly_manifest_approve_api_grile_monthly_manifests__manifest_id__approve_post': { method: 'post', path: '/api/grile/monthly/manifests/{manifest_id}/approve', responseType: 'json' },
  'grile_monthly_manifest_api_grile_monthly_manifests__month__get': { method: 'get', path: '/api/grile/monthly/manifests/{month}', responseType: 'json' },
  'grile_monthly_permissions_api_grile_monthly_permissions_get': { method: 'get', path: '/api/grile/monthly/permissions', responseType: 'json' },
  'grile_monthly_run_api_grile_monthly_run_post': { method: 'post', path: '/api/grile/monthly/run', responseType: 'json' },
  'grile_overview_api_grile_overview_get': { method: 'get', path: '/api/grile/overview', responseType: 'json' },
  'grile_run_api_grile_run_post': { method: 'post', path: '/api/grile/run', responseType: 'json' },
  'grile_run_status_api_grile_run_status_get': { method: 'get', path: '/api/grile/run-status', responseType: 'json' },
  'grile_store_refresh_operation_api_grile_store_refreshes__operation_id__get': { method: 'get', path: '/api/grile/store-refreshes/{operation_id}', responseType: 'json' },
  'grile_store_refresh_api_grile_stores__site_code__refresh_post': { method: 'post', path: '/api/grile/stores/{site_code}/refresh', responseType: 'json' },
  'get_asm_perf_api_hr_asm_performance_get': { method: 'get', path: '/api/hr/asm-performance', responseType: 'json' },
  'get_asm_perf_history_api_hr_asm_performance__asm_name__history_get': { method: 'get', path: '/api/hr/asm-performance/{asm_name}/history', responseType: 'json' },
  'get_asm_salary_api_hr_asm_salary__asm_name__get': { method: 'get', path: '/api/hr/asm-salary/{asm_name}', responseType: 'json' },
  'get_leave_requests_api_hr_leave_requests_get': { method: 'get', path: '/api/hr/leave-requests', responseType: 'json' },
  'post_leave_request_api_hr_leave_requests_post': { method: 'post', path: '/api/hr/leave-requests', responseType: 'json' },
  'patch_leave_request_api_hr_leave_requests__request_id__patch': { method: 'patch', path: '/api/hr/leave-requests/{request_id}', responseType: 'json' },
  'get_manager_overview_api_hr_manager_overview_get': { method: 'get', path: '/api/hr/manager-overview', responseType: 'json' },
  'get_performance_api_hr_performance__agent_name__get': { method: 'get', path: '/api/hr/performance/{agent_name}', responseType: 'json' },
  'reconcile_erp_report_file_api_import_erp_reconciliation_post': { method: 'post', path: '/api/import/erp-reconciliation', responseType: 'json' },
  'get_import_history_api_import_history_get': { method: 'get', path: '/api/import/history', responseType: 'json' },
  'get_import_job_status_api_import_jobs__job_id__get': { method: 'get', path: '/api/import/jobs/{job_id}', responseType: 'json' },
  'upload_promo_actuals_file_api_import_promo_actuals_post': { method: 'post', path: '/api/import/promo-actuals', responseType: 'json' },
  'upload_sales_file_api_import_sales_post': { method: 'post', path: '/api/import/sales', responseType: 'json' },
  'promote_sales_generation_api_import_sales__snapshot_id__promote_post': { method: 'post', path: '/api/import/sales/{snapshot_id}/promote', responseType: 'json' },
  'annual_api_store_pnl_annual_get': { method: 'get', path: '/api/store-pnl/annual', responseType: 'json' },
  'months_api_store_pnl_months_get': { method: 'get', path: '/api/store-pnl/months', responseType: 'json' },
  'overview_api_store_pnl_overview_get': { method: 'get', path: '/api/store-pnl/overview', responseType: 'json' },
  'pnl_permissions_api_store_pnl_permissions_get': { method: 'get', path: '/api/store-pnl/permissions', responseType: 'json' },
  'regions_api_store_pnl_regions_get': { method: 'get', path: '/api/store-pnl/regions', responseType: 'json' },
  'stores_api_store_pnl_stores_get': { method: 'get', path: '/api/store-pnl/stores', responseType: 'json' },
  'list_stores_api_stores_get': { method: 'get', path: '/api/stores', responseType: 'json' },
  'save_targets_api_stores_targets_post': { method: 'post', path: '/api/stores/targets', responseType: 'json' },
  'change_store_activity_api_stores__site_code__activity_post': { method: 'post', path: '/api/stores/{site_code}/activity', responseType: 'json' },
  'get_context_api_target_calculator_context_get': { method: 'get', path: '/api/target-calculator/context', responseType: 'json' },
  'list_scenarios_api_target_calculator_scenarios_get': { method: 'get', path: '/api/target-calculator/scenarios', responseType: 'json' },
  'calculate_scenario_api_target_calculator_scenarios_calculate_post': { method: 'post', path: '/api/target-calculator/scenarios/calculate', responseType: 'json' },
  'get_scenario_api_target_calculator_scenarios__scenario_id__get': { method: 'get', path: '/api/target-calculator/scenarios/{scenario_id}', responseType: 'json' },
  'export_scenario_api_target_calculator_scenarios__scenario_id__export_get': { method: 'get', path: '/api/target-calculator/scenarios/{scenario_id}/export', responseType: 'blob' },
  'finalize_scenario_api_target_calculator_scenarios__scenario_id__finalize_post': { method: 'post', path: '/api/target-calculator/scenarios/{scenario_id}/finalize', responseType: 'json' },
  'update_final_targets_api_target_calculator_scenarios__scenario_id__rows_patch': { method: 'patch', path: '/api/target-calculator/scenarios/{scenario_id}/rows', responseType: 'json' },
  'get_store_detail_api_target_calculator_scenarios__scenario_id__stores__site_code__get': { method: 'get', path: '/api/target-calculator/scenarios/{scenario_id}/stores/{site_code}', responseType: 'json' },
  'get_tasks_api_tasks_get': { method: 'get', path: '/api/tasks', responseType: 'json' },
  'post_task_api_tasks_post': { method: 'post', path: '/api/tasks', responseType: 'json' },
  'remove_task_api_tasks__task_id__delete': { method: 'delete', path: '/api/tasks/{task_id}', responseType: 'json' },
  'patch_task_api_tasks__task_id__patch': { method: 'patch', path: '/api/tasks/{task_id}', responseType: 'json' },
  'get_visits_report_api_visits_report_get': { method: 'get', path: '/api/visits-report', responseType: 'json' },
  'get_visit_photo_api_visits_report_photo__visit_id___filename__get': { method: 'get', path: '/api/visits-report/photo/{visit_id}/{filename}', responseType: 'blob' },
  'get_visits_tree_api_visits_report_tree_get': { method: 'get', path: '/api/visits-report/tree', responseType: 'json' },
  'get_visit_detail_api_visits_report_visit__visit_id__get': { method: 'get', path: '/api/visits-report/visit/{visit_id}', responseType: 'json' },
  'session_status_auth_session_get': { method: 'get', path: '/auth/session', responseType: 'json' },
  'session_login_auth_session_login_get': { method: 'get', path: '/auth/session/login', responseType: 'json' },
  'session_logout_auth_session_logout_post': { method: 'post', path: '/auth/session/logout', responseType: 'json' },
  'metrics_metrics_get': { method: 'get', path: '/metrics', responseType: 'json' },
  'agent_history_by_retail_code_salarii_agents_history_by_retail_code_get': { method: 'get', path: '/salarii/agents/history-by-retail-code', responseType: 'json' },
  'agents_summary_salarii_agents_summary_get': { method: 'get', path: '/salarii/agents/summary', responseType: 'json' },
  'agent_history_salarii_agents__person_id__history_get': { method: 'get', path: '/salarii/agents/{person_id}/history', responseType: 'json' },
  'audit_salary_export_salarii_audit_export_post': { method: 'post', path: '/salarii/audit/export', responseType: 'json' },
  'salarii_evolution_salarii_evolution_get': { method: 'get', path: '/salarii/evolution', responseType: 'json' },
  'salarii_overview_salarii_overview_get': { method: 'get', path: '/salarii/overview', responseType: 'json' },
  'list_records_salarii_records_get': { method: 'get', path: '/salarii/records', responseType: 'json' },
  'salarii_stores_salarii_stores_get': { method: 'get', path: '/salarii/stores', responseType: 'json' },
  'salarii_summary_salarii_summary_get': { method: 'get', path: '/salarii/summary', responseType: 'json' },
  'salarii_trend_salarii_trend_get': { method: 'get', path: '/salarii/trend', responseType: 'json' },
} as const;
