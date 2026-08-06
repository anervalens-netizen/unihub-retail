import { generatedGet, generatedPost } from './generated/client';
import type {
  DashboardAllResponse,
  DashboardHistoryResponse,
  PerformanceDetailLevel,
  PerformanceDetailResponse,
  PremiumGlassAnalysis,
  PremiumGlassSurfaceMode,
  YearHistoryResponse,
} from './types';

export interface DashboardQuery {
  month: string;
  firma?: string;
  regional?: string;
  asm?: string;
  site_code?: string;
  agent?: string;
  current_scope?: boolean;
  include_closed_stores?: boolean;
  surface?: PremiumGlassSurfaceMode;
}

export const MAX_DASHBOARD_BATCH_MONTHS = 12;

export async function getDashboardAll(query: DashboardQuery, signal?: AbortSignal): Promise<DashboardAllResponse> {
  return generatedGet('get_dashboard_all_api_dashboard_all_get', { params: query, signal }) as unknown as DashboardAllResponse;
}

export async function getDashboardAllBatch(queries: DashboardQuery[], signal?: AbortSignal): Promise<DashboardAllResponse[]> {
  const response = await generatedPost('get_dashboard_all_batch_api_dashboard_all_batch_post', { queries }, { signal });
  return response.results as unknown as DashboardAllResponse[];
}

export async function getDashboardHistoryDetailsBatch(
  queries: DashboardQuery[],
  signal?: AbortSignal,
): Promise<DashboardAllResponse[]> {
  const response = await generatedPost(
    'get_dashboard_history_details_batch_api_dashboard_history_details_batch_post',
    { queries },
    { signal },
  );
  return response.results as unknown as DashboardAllResponse[];
}

export async function getDashboardHistory(
  query: DashboardQuery & { months_back?: number },
  signal?: AbortSignal,
): Promise<DashboardHistoryResponse> {
  return generatedGet('get_monthly_history_api_dashboard_history_get', { params: query, signal }) as unknown as DashboardHistoryResponse;
}

export async function getDashboardHistoryYear(
  query: Omit<DashboardQuery, 'month'> & { year: number },
  signal?: AbortSignal,
): Promise<YearHistoryResponse> {
  return generatedGet('get_history_by_year_api_dashboard_history_year_get', { params: query, signal }) as unknown as YearHistoryResponse;
}

export async function getPremiumGlassAnalysis(query: DashboardQuery, signal?: AbortSignal): Promise<PremiumGlassAnalysis> {
  return generatedGet('get_premium_glass_api_dashboard_premium_glass_get', { params: query, signal }) as unknown as PremiumGlassAnalysis;
}

export async function getPerformanceDetail(
  query: DashboardQuery & { level: PerformanceDetailLevel; key: string },
  signal?: AbortSignal,
): Promise<PerformanceDetailResponse> {
  return generatedGet('get_performance_detail_api_dashboard_performance_detail_get', { params: query, signal }) as unknown as PerformanceDetailResponse;
}
