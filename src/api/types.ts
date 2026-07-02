export interface DashboardSummary {
  month: string;
  total_sales: number;
  total_target: number;
  target_progress_pct: number | null;
  forecast_sales: number | null;
  forecast_target_progress_pct: number | null;
  total_quantity: number;
  total_receipts: number;
  proc_bon2acc: number | null;
  prc_focus_acc_qty: number | null;
  total_stores: number;
  total_agents: number;
  working_days: number;
  daily_average: number | null;
  is_month_final: boolean;
  last_sale_date: string | null;
  imported_day_of_month: number | null;
  days_in_month: number | null;
  cartele_qty: number;
}

export interface ReceiptBucketItem {
  bucket: string;
  receipt_count: number;
  share_pct: number | null;
}

export interface DailySalesPoint {
  sale_date: string;
  total_sales: number;
  total_quantity: number;
  receipt_count: number;
}

export interface AiForecastRunInfo {
  id: number;
  forecast_month: string;
  source_month: string;
  metric: AiForecastMetric;
  horizon: AiForecastHorizon;
  model_name: string;
  model_mode: string;
  variant: string;
  generated_at: string;
  metadata: Record<string, unknown>;
}

export type AiForecastMetric = 'sales_value' | 'units';
export type AiForecastHorizon = 'current_month' | 'rolling_12m';

export interface AiForecastSummary {
  forecast_month: string;
  source_month: string;
  actual_last_date: string | null;
  days_elapsed: number;
  days_in_month: number;
  store_count: number;
  forecast_sales: number;
  expected_sales_to_date: number;
  actual_sales: number;
  delta_sales: number;
  delta_pct: number | null;
}

export interface AiForecastManagerRow {
  manager: string;
  store_count: number;
  forecast_sales: number;
  expected_sales_to_date: number;
  actual_sales: number;
  delta_sales: number;
  delta_pct: number | null;
}

export interface AiForecastStoreRow {
  site_code: string;
  locatie: string;
  firma: string;
  regional: string;
  asm: string;
  forecast_sales: number;
  expected_sales_to_date: number;
  actual_sales: number;
  delta_sales: number;
  delta_pct: number | null;
}

export interface AiForecastDailyPoint {
  forecast_date: string;
  forecast_sales: number;
  actual_sales: number;
  cumulative_forecast: number;
  cumulative_actual: number;
}

export interface AiForecastResponse {
  run: AiForecastRunInfo;
  summary: AiForecastSummary;
  managers: AiForecastManagerRow[];
  stores: AiForecastStoreRow[];
  daily: AiForecastDailyPoint[];
}

export interface AiForecastRollingSummary {
  source_month: string;
  start_month: string;
  end_month: string;
  month_count: number;
  store_count: number;
  forecast_sales: number;
  actual_sales: number | null;
  delta_sales: number | null;
  delta_pct: number | null;
}

export interface AiForecastRollingMonthlyPoint {
  forecast_month: string;
  store_count: number;
  forecast_sales: number;
  actual_sales: number | null;
  delta_sales: number | null;
  delta_pct: number | null;
}

export interface AiForecastRollingManagerRow {
  manager: string;
  store_count: number;
  forecast_sales: number;
  actual_sales: number | null;
  delta_sales: number | null;
  delta_pct: number | null;
}

export interface AiForecastRollingStoreRow {
  site_code: string;
  locatie: string;
  firma: string;
  regional: string;
  asm: string;
  forecast_sales: number;
  actual_sales: number | null;
  delta_sales: number | null;
  delta_pct: number | null;
}

export interface AiForecastRollingResponse {
  runs: AiForecastRunInfo[];
  summary: AiForecastRollingSummary;
  months: AiForecastRollingMonthlyPoint[];
  managers: AiForecastRollingManagerRow[];
  stores: AiForecastRollingStoreRow[];
}

export interface MonthlyHistoryPoint {
  month: string;
  total_sales: number;
  total_target: number;
  target_progress_pct: number | null;
  total_quantity: number;
  total_receipts: number;
  proc_bon2acc: number | null;
  prc_focus_acc_qty: number | null;
  total_stores: number;
  total_agents: number;
  working_days: number;
  daily_average: number | null;
}

export interface DashboardSpecialCardMetric {
  label: string;
  value: string;
}

export interface DashboardSpecialCard {
  key: 'promotion' | 'incentive' | 'premium_glass';
  title: string;
  subtitle: string | null;
  status: 'ready' | 'inactive' | 'no_data' | 'missing_config' | 'missing_source' | 'limited_scope';
  status_label: string;
  highlight_value: string;
  description: string;
  coverage_note: string | null;
  metrics: DashboardSpecialCardMetric[];
}

export interface PromoIncentiveSummary {
  promo_qty: number;
  promo_sales: number;
  promo_impact: number;
  incentive_qty: number;
  incentive_value: number;
  incentive_qualified_stores: number;
  incentive_qualified_agents: number;
}

export interface PremiumGlassSummary {
  month: string;
  total_qty: number;
  total_sales: number;
  premium_qty: number;
  premium_sales: number;
  regular_qty: number;
  regular_sales: number;
  premium_qty_share_pct: number | null;
  premium_sales_share_pct: number | null;
  active_stores: number;
  active_agents: number;
  premium_active_stores: number;
  premium_active_agents: number;
  target_model_count: number;
}

export interface PremiumGlassModelStat {
  model_key: string;
  model_label: string;
  premium_qty: number;
  regular_qty: number;
  total_qty: number;
  premium_sales: number;
  regular_sales: number;
  total_sales: number;
  premium_qty_share_pct: number | null;
  premium_item_count: number;
  regular_item_count: number;
}

export interface PremiumGlassSurfaceStat {
  surface_key: 'screen' | 'camera';
  surface_label: string;
  premium_qty: number;
  regular_qty: number;
  total_qty: number;
  premium_sales: number;
  regular_sales: number;
  total_sales: number;
  premium_qty_share_pct: number | null;
}

export interface PremiumGlassStoreStat {
  site_code: string;
  locatie: string;
  firma: string;
  premium_qty: number;
  regular_qty: number;
  total_qty: number;
  premium_sales: number;
  regular_sales: number;
  total_sales: number;
  premium_qty_share_pct: number | null;
}

export interface PremiumGlassManagerStat {
  manager: string;
  premium_qty: number;
  regular_qty: number;
  total_qty: number;
  premium_sales: number;
  regular_sales: number;
  total_sales: number;
  premium_qty_share_pct: number | null;
  store_count: number;
  agent_count: number;
}

export interface PremiumGlassAgentStat {
  agent: string;
  site_code: string;
  locatie: string;
  firma: string;
  premium_qty: number;
  regular_qty: number;
  total_qty: number;
  premium_sales: number;
  regular_sales: number;
  total_sales: number;
  premium_qty_share_pct: number | null;
}

export interface PremiumGlassProductStat {
  item_code: string;
  item_name: string;
  is_premium: boolean;
  model_labels: string[];
  qty: number;
  sales: number;
  store_count: number;
}

export interface PremiumGlassAnalysis {
  summary: PremiumGlassSummary;
  models: PremiumGlassModelStat[];
  surfaces: PremiumGlassSurfaceStat[];
  managers: PremiumGlassManagerStat[];
  stores: PremiumGlassStoreStat[];
  agents: PremiumGlassAgentStat[];
  products: PremiumGlassProductStat[];
}

export type PremiumGlassSurfaceMode = 'all' | 'screen' | 'camera';

export interface CampaignOverview {
  month: string;
  total_focus_sales: number;
  total_focus_qty: number;
  focus_share_pct: number | null;
  active_focus_products: number;
  active_focus_stores: number;
}

export interface CampaignProductStat {
  item_code: string;
  item_name: string;
  qty_total: number;
  sales_total: number;
  store_count: number;
}

export interface CampaignStoreStat {
  site_code: string;
  locatie: string;
  qty_total: number;
  sales_total: number;
  active_products: number;
}

export interface CampaignSnapshot {
  overview: CampaignOverview;
  products: CampaignProductStat[];
  stores: CampaignStoreStat[];
}

export interface FocusHistoryPoint {
  month: string;
  total_focus_sales: number;
  total_focus_qty: number;
  focus_share_pct: number | null;
  active_focus_products: number;
  active_focus_stores: number;
}

export interface FocusHistoryResponse {
  history: FocusHistoryPoint[];
}

export interface AgentStat {
  import_month: string;
  agent: string;
  site_code: string;
  locatie: string;
  firma: string;
  regional: string;
  asm: string;
  acc_qty_realizat: number;
  nr_bonuri: number;
  nr_bon2acc: number;
  proc_bon2acc: number | null;
  total_vanzari: number;
  zile_lucrate: number;
  medie_zilnica: number | null;
  acc_focus_qty: number;
  prc_focus_acc_qty: number | null;
  target: number | null;
  proc_realizare_target: number | null;
  promo_qty: number;
  incentive_qty: number;
}

export interface StoreStat {
  import_month: string;
  site_code: string;
  locatie: string;
  firma: string;
  regional: string;
  asm: string;
  total_vanzari: number;
  qty_total: number | null;
  nr_bonuri: number;
  nr_agenti: number;
  zile_active: number;
  target: number;
  proc_realizare_target: number | null;
  forecast_target_pct: number | null;
  promo_qty: number;
  incentive_qty: number;
}

export interface RegionalStat {
  regional: string;
  total_vanzari: number;
  qty_total: number;
  nr_bonuri: number;
  nr_agenti: number;
  zile_active: number;
  target: number;
  proc_realizare_target: number | null;
  forecast_target_pct: number | null;
  promo_qty: number;
  incentive_qty: number;
  medie_zilnica: number | null;
  proc_bon2acc: number | null;
  prc_focus_acc_qty: number | null;
}

export type PerformanceDetailLevel = 'regional' | 'store' | 'agent';

export interface PerformancePeerRow {
  label: string;
  sublabel: string | null;
  total_sales: number;
  target_progress_pct: number | null;
  forecast_target_pct: number | null;
  proc_bon2acc: number | null;
  prc_focus_acc_qty: number | null;
  rank: number;
  is_selected: boolean;
}

export interface PerformanceDetailResponse {
  level: PerformanceDetailLevel;
  key: string;
  title: string;
  subtitle: string | null;
  month: string;
  summary: DashboardSummary;
  history: MonthlyHistoryPoint[];
  daily: DailySalesPoint[];
  score: number;
  score_label: string;
  note: string;
  strengths: string[];
  risks: string[];
  peer_rows: PerformancePeerRow[];
  context_summary: DashboardSummary | null;
}

export interface AsmStat {
  asm: string;
  regional: string;
  total_vanzari: number;
  qty_total: number;
  nr_bonuri: number;
  nr_agenti: number;
  zile_active: number;
  target: number;
  proc_realizare_target: number | null;
  promo_qty: number;
  incentive_qty: number;
  medie_zilnica: number | null;
  proc_bon2acc: number | null;
  prc_focus_acc_qty: number | null;
}

export interface AgentOption {
  agent: string;
  site_code: string;
  locatie: string;
  firma: string;
  regional: string;
  asm: string;
}

export interface FilterOptions {
  firme: string[];
  regionali: string[];
  asmi: string[];
  magazine: StoreOption[];
  agenti: AgentOption[];
}

export interface ImportHistoryEntry {
  id: number;
  import_month: string;
  filename: string;
  upload_date: string;
  is_month_final: boolean;
  rows_in_file: number | null;
  rows_imported: number | null;
  status: string;
  error_message: string | null;
  created_at: string;
}

export interface ImportResponse {
  import_month: string;
  rows_in_file: number;
  rows_imported: number;
  rows_filtered: number;
  store_count: number;
  agent_count: number;
  snapshot_id: number;
  filename: string;
  is_month_final: boolean;
}

export interface ImportJobStatus {
  job_id: string;
  status: 'queued' | 'in_progress' | 'complete' | 'not_found';
  result: ImportResponse | null;
  error: string | null;
}

export interface StoreOption {
  site_code: string;
  locatie: string;
  firma: string;
  regional: string;
  asm: string;
}

export interface DashboardAllResponse {
  summary: DashboardSummary;
  agents: AgentStat[];
  stores: StoreStat[];
  regionals: RegionalStat[];
  asms: AsmStat[];
  daily: DailySalesPoint[];
  daily_last_year: DailySalesPoint[];
  special_cards: DashboardSpecialCard[];
  period_comparison: PeriodComparisonPayload | null;
  category_mix: CategoryMixItem[];
  receipt_bucket_mix: ReceiptBucketItem[];
  focus_subcategory_mix: CategoryMixItem[];
  brand_mix: BrandMixItem[];
  promo_incentive: PromoIncentiveSummary;
  premium_glass: PremiumGlassAnalysis | null;
}

export interface DashboardHistoryResponse {
  history: MonthlyHistoryPoint[];
}

export interface YearHistoryPoint {
  label: string;
  sort_key: string;
  total_sales: number;
  total_target: number;
  total_quantity: number;
  is_aggregate: boolean;
}

export interface YearHistoryResponse {
  points: YearHistoryPoint[];
}

export interface PeriodComparisonPoint {
  label: string;
  month: string;
  day_range: string;
  total_sales: number;
  total_quantity: number;
  total_receipts: number;
  cartele_qty: number;
  working_days: number;
  daily_average: number | null;
  avg_receipt_value: number | null;
  proc_bon2acc: number | null;
  prc_focus_acc_qty: number | null;
}

export interface PeriodComparisonPayload {
  current: PeriodComparisonPoint;
  previous: PeriodComparisonPoint;
  year_over_year: PeriodComparisonPoint;
}

export interface CategoryMixItem {
  category: string;
  sales_total: number;
  quantity_total: number;
  share_pct: number | null;
}

export interface BrandMixItem {
  brand: string;
  sales_total: number;
  quantity_total: number;
  share_pct: number | null;
}

export interface PromoTopStore {
  store_name: string;
  qty: number;
  total_qty: number;
  category_qty: number;
  promo_bons: number;
  incentive_value: number;
  incentive_potential: number;
  achievement: number | null;
  firma: string;
}

export interface PromoTopAgent {
  agent_name: string;
  store_name: string;
  firma: string;
  promo_bons: number;
}

export interface IncentiveTopAgent {
  agent_name: string;
  store_name: string;
  firma: string;
  qty_sold: number;
  val_incentive: number;
  incentive_potential: number;
  achievement: number | null;
}

export interface IncentiveCategory {
  label: string;
  qty: number;
  value: number;
}

export interface CampaignPromotionOption {
  key: string;
  label: string;
}

export interface CampaignsPromotionsResponse {
  promotions: CampaignPromotionOption[];
  selected_promotion_key: string;
  promo_title: string;
  promo_description: string;
  promo_qty: number;
  promo_total_qty: number;
  promo_category_qty: number | null;
  promo_impact: number;
  promo_qualifying_bons: number;
  promo_discounted_units: number;
  promo_active_stores: number;
  promo_active_agents: number;
  incentive_title: string;
  incentive_description: string;
  incentive_qty: number;
  incentive_value: number;
  incentive_product_count: number;
  incentive_categories: IncentiveCategory[];
  has_active_promotion: boolean;
  top_stores: PromoTopStore[];
  promo_agents: PromoTopAgent[];
  top_agents: IncentiveTopAgent[];
}

export interface ContestRuleInfo {
  type: string;
  points: number;
  label: string;
  threshold: number | null;
}

export interface ContestPrizeInfo {
  rank_from: number;
  rank_to: number;
  label: string;
}

export interface ContestLeaderboardRow {
  rank: number;
  agent: string;
  site_code: string | null;
  store_name: string | null;
  firma: string | null;
  focus_units: number;
  promo_bonuri: number;
  price_units: number;
  focus_points: number;
  promo_points: number;
  price_points: number;
  total_points: number;
  prize: string | null;
}

export interface ContestResponse {
  key: string;
  title: string;
  subtitle: string;
  scope_label: string;
  month: string;
  start_date: string;
  end_date: string;
  store_count: number;
  rules: ContestRuleInfo[];
  prizes: ContestPrizeInfo[];
  leaderboard: ContestLeaderboardRow[];
}
