import { generatedGet, generatedPost } from './generated/client';
import type { RetailOperationQueries } from './generated/contracts';
import type { GeneratedRequest } from './generated/runtime-types';
import type {
  DashboardAllResponse,
  DashboardHistoryResponse,
  PerformanceDetailResponse,
  PremiumGlassAnalysis,
  YearHistoryResponse,
} from './generated/runtime-types';

export type DashboardQuery = RetailOperationQueries['get_dashboard_all_api_dashboard_all_get'];
export type DashboardBatchRequest = GeneratedRequest<'get_dashboard_all_batch_api_dashboard_all_batch_post'>;

export const MAX_DASHBOARD_BATCH_MONTHS = 12;

export async function getDashboardAll(query: DashboardQuery, signal?: AbortSignal): Promise<DashboardAllResponse> {
  return generatedGet('get_dashboard_all_api_dashboard_all_get', { params: query, signal });
}

export async function getDashboardAllBatch(queries: DashboardBatchRequest['queries'], signal?: AbortSignal): Promise<DashboardAllResponse[]> {
  const response = await generatedPost('get_dashboard_all_batch_api_dashboard_all_batch_post', { queries }, { signal });
  return response.results;
}

export async function getDashboardHistoryDetailsBatch(
  queries: GeneratedRequest<'get_dashboard_history_details_batch_api_dashboard_history_details_batch_post'>['queries'],
  signal?: AbortSignal,
): Promise<DashboardAllResponse[]> {
  const response = await generatedPost(
    'get_dashboard_history_details_batch_api_dashboard_history_details_batch_post',
    { queries },
    { signal },
  );
  return response.results;
}

export async function getDashboardHistory(
  query: RetailOperationQueries['get_monthly_history_api_dashboard_history_get'],
  signal?: AbortSignal,
): Promise<DashboardHistoryResponse> {
  return generatedGet('get_monthly_history_api_dashboard_history_get', { params: query, signal });
}

export async function getDashboardHistoryYear(
  query: RetailOperationQueries['get_history_by_year_api_dashboard_history_year_get'],
  signal?: AbortSignal,
): Promise<YearHistoryResponse> {
  return generatedGet('get_history_by_year_api_dashboard_history_year_get', { params: query, signal });
}

export async function getPremiumGlassAnalysis(query: RetailOperationQueries['get_premium_glass_api_dashboard_premium_glass_get'], signal?: AbortSignal): Promise<PremiumGlassAnalysis> {
  return generatedGet('get_premium_glass_api_dashboard_premium_glass_get', { params: query, signal });
}

export async function getPerformanceDetail(
  query: RetailOperationQueries['get_performance_detail_api_dashboard_performance_detail_get'],
  signal?: AbortSignal,
): Promise<PerformanceDetailResponse> {
  return generatedGet('get_performance_detail_api_dashboard_performance_detail_get', { params: query, signal });
}
