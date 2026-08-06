import type * as Contract from './contracts';
import type { DecodeRetail } from './decoded';

/**
 * Runtime-facing types for the generated contract.
 *
 * Decimal values are decoded to numbers by generated/client.ts. Pydantic
 * defaults are emitted by the API, so the UI consumes the corresponding
 * fields as present while nullability remains intact.
 */
export type DeepRequired<T> = T extends (...args: never[]) => unknown
  ? T
  : T extends readonly unknown[]
    ? number extends T['length']
      ? Array<DeepRequired<T[number]>>
      : { [Key in keyof T]-?: DeepRequired<T[Key]> }
    : T extends object
      ? { [Key in keyof T]-?: DeepRequired<T[Key]> }
      : T;

export type Runtime<T> = DecodeRetail<T>;
export type RequiredRuntime<T> = DeepRequired<Runtime<T>>;

export type DashboardSummary = RequiredRuntime<Contract.RetailDashboardSummary>;
export type ReceiptBucketItem = RequiredRuntime<Contract.RetailReceiptBucketItem>;
export type DailySalesPoint = RequiredRuntime<Contract.RetailDailySalesPoint>;
export type AiForecastRunInfo = RequiredRuntime<Contract.RetailAiForecastRunInfo>;
export type AiForecastMetric = NonNullable<Contract.RetailAiForecastRunInfo['metric']>;
export type AiForecastHorizon = NonNullable<Contract.RetailAiForecastRunInfo['horizon']>;
export type AiForecastSummary = RequiredRuntime<Contract.RetailAiForecastSummary>;
export type AiForecastManagerRow = RequiredRuntime<Contract.RetailAiForecastManagerRow>;
export type AiForecastStoreRow = RequiredRuntime<Contract.RetailAiForecastStoreRow>;
export type AiForecastDailyPoint = RequiredRuntime<Contract.RetailAiForecastDailyPoint>;
export type AiForecastResponse = RequiredRuntime<Contract.RetailAiForecastResponse>;
export type AiForecastRollingSummary = RequiredRuntime<Contract.RetailAiForecastRollingSummary>;
export type AiForecastRollingMonthlyPoint = RequiredRuntime<Contract.RetailAiForecastRollingMonthlyPoint>;
export type AiForecastRollingManagerRow = RequiredRuntime<Contract.RetailAiForecastRollingManagerRow>;
export type AiForecastRollingStoreRow = RequiredRuntime<Contract.RetailAiForecastRollingStoreRow>;
export type AiForecastRollingResponse = RequiredRuntime<Contract.RetailAiForecastRollingResponse>;
export type MonthlyHistoryPoint = RequiredRuntime<Contract.RetailMonthlyHistoryPoint>;
export type DashboardSpecialCardMetric = RequiredRuntime<Contract.RetailDashboardSpecialCardMetric>;
export type DashboardSpecialCard = RequiredRuntime<Contract.RetailDashboardSpecialCard>;
export type PromoIncentiveSummary = RequiredRuntime<Contract.RetailPromoIncentiveSummary>;
export type PremiumGlassSummary = RequiredRuntime<Contract.RetailPremiumGlassSummary>;
export type PremiumGlassModelStat = RequiredRuntime<Contract.RetailPremiumGlassModelStat>;
export type PremiumGlassSurfaceStat = RequiredRuntime<Contract.RetailPremiumGlassSurfaceStat>;
export type PremiumGlassStoreStat = RequiredRuntime<Contract.RetailPremiumGlassStoreStat>;
export type PremiumGlassManagerStat = RequiredRuntime<Contract.RetailPremiumGlassManagerStat>;
export type PremiumGlassAgentStat = RequiredRuntime<Contract.RetailPremiumGlassAgentStat>;
export type PremiumGlassProductStat = RequiredRuntime<Contract.RetailPremiumGlassProductStat>;
export type PremiumGlassAnalysis = RequiredRuntime<Contract.RetailPremiumGlassAnalysis>;
export type PremiumGlassSurfaceMode = 'all' | 'screen' | 'camera';
export type CampaignOverview = RequiredRuntime<Contract.RetailCampaignOverview>;
export type CampaignProductStat = RequiredRuntime<Contract.RetailCampaignProductStat>;
export type CampaignStoreStat = RequiredRuntime<Contract.RetailCampaignStoreStat>;
export type CampaignSnapshot = RequiredRuntime<Contract.RetailCampaignSnapshot>;
export type FocusHistoryPoint = RequiredRuntime<Contract.RetailFocusHistoryPoint>;
export type FocusHistoryResponse = RequiredRuntime<Contract.RetailFocusHistoryResponse>;
export type AgentStat = Omit<RequiredRuntime<Contract.RetailAgentStats>, 'promo_discount_value'> & {
  promo_discount_value?: number;
};
export type StoreStat = Omit<RequiredRuntime<Contract.RetailStoreStats>, 'promo_discount_value' | 'proc_bon2acc' | 'prc_focus_acc_qty'> & {
  promo_discount_value?: number;
  proc_bon2acc?: number | null;
  prc_focus_acc_qty?: number | null;
};
export type RegionalStat = Omit<RequiredRuntime<Contract.RetailRegionalStats>, 'promo_discount_value'> & {
  promo_discount_value?: number;
};
export type PerformanceDetailLevel = 'regional' | 'store' | 'agent';
export type PerformancePeerRow = RequiredRuntime<Contract.RetailPerformancePeerRow>;
export type PerformanceScoreBreakdown = RequiredRuntime<Contract.RetailPerformanceScoreBreakdown>;
export type PerformanceDetailResponse = RequiredRuntime<Contract.RetailPerformanceDetailResponse>;
export type AsmStat = Omit<RequiredRuntime<Contract.RetailAsmStats>, 'promo_discount_value'> & {
  promo_discount_value?: number;
};
export type AgentOption = RequiredRuntime<Contract.RetailAgentOption>;
export type StoreOption = RequiredRuntime<Contract.RetailStoreOption>;
export type FilterOptions = RequiredRuntime<Contract.RetailFilterOptions>;
export type ImportHistoryEntry = RequiredRuntime<Contract.RetailImportHistoryEntry>;
export type ImportResponse = RequiredRuntime<Contract.RetailImportResponse>;
export type ImportJobStatus = RequiredRuntime<Contract.RetailImportJobStatus>;
export type ImportCoverageReport = RequiredRuntime<Contract.RetailImportCoverageReport>;
export type SalesGenerationManifest = RequiredRuntime<Contract.RetailSalesGenerationManifest>;
export type DashboardAllResponse = Omit<
  Runtime<Contract.RetailDashboardAllResponse>,
  'agents' | 'asms' | 'brand_mix' | 'category_mix' | 'daily' | 'daily_last_year'
    | 'focus_subcategory_mix' | 'period_comparison' | 'premium_glass' | 'promo_incentive'
    | 'receipt_bucket_mix' | 'regionals' | 'special_cards' | 'stores' | 'summary'
> & {
  agents: AgentStat[];
  asms: AsmStat[];
  brand_mix: BrandMixItem[];
  category_mix: CategoryMixItem[];
  daily: DailySalesPoint[];
  daily_last_year: DailySalesPoint[];
  focus_subcategory_mix: CategoryMixItem[];
  period_comparison: PeriodComparisonPayload | null;
  premium_glass: PremiumGlassAnalysis | null;
  promo_incentive: PromoIncentiveSummary;
  receipt_bucket_mix: ReceiptBucketItem[];
  regionals: RegionalStat[];
  special_cards: DashboardSpecialCard[];
  stores: StoreStat[];
  summary: DashboardSummary;
};
export type DashboardHistoryResponse = RequiredRuntime<Contract.RetailDashboardHistoryResponse>;
export type YearHistoryPoint = RequiredRuntime<Contract.RetailYearHistoryPoint>;
export type YearHistoryResponse = RequiredRuntime<Contract.RetailYearHistoryResponse>;
export type PeriodComparisonPoint = RequiredRuntime<Contract.RetailPeriodComparisonPoint>;
export type PeriodComparisonPayload = RequiredRuntime<Contract.RetailPeriodComparisonPayload>;
export type CategoryMixItem = RequiredRuntime<Contract.RetailCategoryMixItem>;
export type BrandMixItem = RequiredRuntime<Contract.RetailBrandMixItem>;
export type PromoTopStore = RequiredRuntime<Contract.RetailPromoTopStore>;
export type PromoTopAgent = RequiredRuntime<Contract.RetailPromoTopAgent>;
export type IncentiveTopAgent = RequiredRuntime<Contract.RetailIncentiveTopAgent>;
export type IncentiveCategory = RequiredRuntime<Contract.RetailIncentiveCategory>;
export type IncentivePeriodStat = RequiredRuntime<Contract.RetailIncentivePeriodStat>;
export type IncentiveCategoryBreakdown = RequiredRuntime<Contract.RetailIncentiveCategoryBreakdown>;
export type CampaignPromotionOption = RequiredRuntime<Contract.RetailCampaignPromotionOption>;
export type CampaignsPromotionsResponse = RequiredRuntime<Contract.RetailCampaignsPromotionsResponse>;

export type ContestRuleInfo = RequiredRuntime<Contract.RetailContestRuleInfo>;
export type ContestPrizeInfo = RequiredRuntime<Contract.RetailContestPrizeInfo>;
export type ContestLeaderboardRow = RequiredRuntime<Contract.RetailContestLeaderboardRow>;
export type ContestResponse = RequiredRuntime<Contract.RetailContestResponse>;

export type AgentsOverviewResponse = RequiredRuntime<Contract.RetailAgentsOverviewResponse>;
export type StoreCoverageItem = RequiredRuntime<Contract.RetailStoreCoverageItem>;
export type StoreCoverageResponse = RequiredRuntime<Contract.RetailStoreCoverageResponse>;
export type AgentMovementPoint = RequiredRuntime<Contract.RetailAgentMovementPoint>;
export type AgentMovementResponse = RequiredRuntime<Contract.RetailAgentMovementResponse>;
export type AgentListItem = RequiredRuntime<Contract.RetailAgentListItem>;
export type AgentListResponse = RequiredRuntime<Contract.RetailAgentListResponse>;
export type AgentProfileResponse = RequiredRuntime<Contract.RetailAgentProfileResponse>;
export type AgentHistoryPoint = RequiredRuntime<Contract.RetailAgentHistoryPoint>;
export type AgentHistoryResponse = RequiredRuntime<Contract.RetailAgentHistoryResponse>;
export type AgentEvaluationOption = RequiredRuntime<Contract.RetailAgentEvaluationOption>;
export type AgentEvaluationRow = RequiredRuntime<Contract.RetailAgentEvaluationRow>;
export type AgentEvaluationResponse = RequiredRuntime<Contract.RetailAgentEvaluationResponse>;
export type AgentEvaluationV2Row = RequiredRuntime<Contract.RetailAgentEvaluationV2Row>;
export type AgentEvaluationV2Response = RequiredRuntime<Contract.RetailAgentEvaluationV2Response>;

export type AsmPerformance = RequiredRuntime<Contract.RetailHrAsmPerformanceItem>;
export type AsmHistoryPoint = RequiredRuntime<Contract.RetailHrAsmHistoryItem>;
export type ManagerStoreOverview = RequiredRuntime<Contract.RetailHrManagerStoreItem>;
export type ManagerOverview = RequiredRuntime<Contract.RetailHrManagerOverviewItem>;
export type AsmSalaryIsland = RequiredRuntime<Contract.RetailHrAsmSalaryIsland>;
export type AsmSalaryBreakdown = RequiredRuntime<Contract.RetailHrAsmSalaryBreakdown>;

export type StoreScore = RequiredRuntime<Contract.RetailCrmScoreResponse>;

export type PromoActualImportResponse = RequiredRuntime<Contract.RetailPromoActualImportResponse>;
export type ErpReconciliationMetric = RequiredRuntime<Contract.RetailErpReconciliationMetric>;
export type ErpReconciliationIssue = RequiredRuntime<Contract.RetailErpReconciliationIssue>;
export type ErpReconciliationAppMetric = RequiredRuntime<Contract.RetailErpReconciliationAppMetric>;
export type ErpReconciliationResponse = RequiredRuntime<Contract.RetailErpReconciliationResponse>;

export type PnlMonth = RequiredRuntime<Contract.RetailPnlMonthResponse>;
export type PnlMetrics = RequiredRuntime<Contract.RetailPnlMetricsResponse>;
export type PnlMonthlyPoint = RequiredRuntime<Contract.RetailPnlMonthlyItemResponse>;
export type PnlAnnualPoint = RequiredRuntime<Contract.RetailPnlAnnualItemResponse>;
export type PnlStoreOption = RequiredRuntime<Contract.RetailPnlStoreOptionResponse>;
export type PnlPermissions = RequiredRuntime<Contract.RetailPnlPermissionsResponse>;
export type PnlStore = RequiredRuntime<Contract.RetailPnlStoreResponse>;
export type PnlReconciliation = RequiredRuntime<Contract.RetailPnlReconciliationResponse>;
export type PnlOverview = RequiredRuntime<Contract.RetailPnlOverviewResponse>;

export type SalaryEvolutionPoint = RequiredRuntime<Contract.RetailSalaryEvolutionPoint>;
export type SalaryAgentSummary = RequiredRuntime<Contract.RetailSalaryAgentSummaryPublic>;
export type SalaryAgentHistoryRecord = RequiredRuntime<Contract.RetailSalaryHistoryRecordPublic>;
export type AgentSalaryLink = RequiredRuntime<Contract.RetailAgentSalaryLinkPublic>;
export type SalaryAgentHistory = RequiredRuntime<Contract.RetailSalaryHistoryResponse>;
export type SalariiOverview = RequiredRuntime<Contract.RetailSalaryOverviewResponse>;
export type SalaryComparisonPoint = RequiredRuntime<Contract.RetailSalaryComparisonItem>;
export type SalarySummaryResponse = RequiredRuntime<Contract.RetailSalarySummaryResponse>;
export type SalaryTrendMonth = RequiredRuntime<Contract.RetailSalaryTrendPoint>;
export type SalaryAgentsSummaryResponse = RequiredRuntime<Contract.RetailSalaryAgentsSummaryResponse>;
export type SalaryStoreOption = RequiredRuntime<Contract.RetailSalaryStoreOption>;

export type TargetCalculatorContext = RequiredRuntime<Contract.RetailTargetContextResponse>;
export type TargetCalculationInput = Omit<Runtime<Contract.RetailTargetCalculationRequest>, 'min_floor' | 'previous_month_floor_pct' | 'target_month' | 'total_target'> & {
  target_month: string;
  total_target: number;
  min_floor: number;
  previous_month_floor_pct: number;
};
export type TargetSourceMonth = RequiredRuntime<Contract.RetailTargetSourceMonth>;
export type TargetHistoryValue = RequiredRuntime<Contract.RetailTargetHistoryValue>;
export type TargetScenarioRow = RequiredRuntime<Contract.RetailTargetScenarioRowResponse>;
export type TargetProfitability = RequiredRuntime<Contract.RetailTargetProfitabilityResponse>;
export type TargetProfitabilitySummary = RequiredRuntime<Contract.RetailTargetProfitabilitySummaryResponse>;
export type TargetSeasonalityYear = RequiredRuntime<Contract.RetailTargetSeasonalityYear>;
export type TargetCalculationDetails = RequiredRuntime<Contract.RetailTargetCalculationDetails>;
export type TargetRegionalSummary = RequiredRuntime<Contract.RetailTargetRegionalSummaryResponse>;
export type TargetSourceSummary = RequiredRuntime<Contract.RetailTargetSourceSummaryResponse>;
export type TargetScenarioSummary = RequiredRuntime<Contract.RetailTargetScenarioSummaryResponse>;
export type TargetScenario = RequiredRuntime<Contract.RetailTargetScenarioResponse>;
export type TargetStoreHistoryPoint = RequiredRuntime<Contract.RetailTargetStoreHistoryPointResponse>;
export type TargetStoreAgent = RequiredRuntime<Contract.RetailTargetStoreAgentResponse>;
export type TargetStoreDetail = RequiredRuntime<Contract.RetailTargetStoreDetailResponse>;
export type VisitReportRow = RequiredRuntime<Contract.RetailVisitReportRow>;
export type VisitReportResponse = RequiredRuntime<Contract.RetailVisitReportResponse>;
export type VisitSummaryItem = RequiredRuntime<Contract.RetailVisitSummaryItem>;
export type VisitDayGroup = RequiredRuntime<Contract.RetailVisitDayGroup>;
export type VisitMonthGroup = RequiredRuntime<Contract.RetailVisitMonthGroup>;
export type TeamLeaderGroup = RequiredRuntime<Contract.RetailTeamLeaderGroup>;
export type VisitTreeResponse = RequiredRuntime<Contract.RetailVisitTreeResponse>;
export type VisitDetail = RequiredRuntime<Contract.RetailVisitDetail>;
