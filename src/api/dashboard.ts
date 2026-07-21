import { client } from './client';
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

export async function getDashboardAll(query: DashboardQuery): Promise<DashboardAllResponse> {
  const { data } = await client.get<DashboardAllResponse>('/api/dashboard/all', { params: query });
  return data;
}

export async function getDashboardAllBatch(queries: DashboardQuery[]): Promise<DashboardAllResponse[]> {
  const { data } = await client.post<{ results: DashboardAllResponse[] }>(
    '/api/dashboard/all-batch',
    { queries },
  );
  return data.results;
}

export async function getDashboardHistory(
  query: DashboardQuery & { months_back?: number }
): Promise<DashboardHistoryResponse> {
  const { data } = await client.get<DashboardHistoryResponse>('/api/dashboard/history', { params: query });
  return data;
}

export async function getDashboardHistoryYear(
  query: Omit<DashboardQuery, 'month'> & { year: number }
): Promise<YearHistoryResponse> {
  const { data } = await client.get<YearHistoryResponse>('/api/dashboard/history-year', { params: query });
  return data;
}

export async function getPremiumGlassAnalysis(query: DashboardQuery): Promise<PremiumGlassAnalysis> {
  const { data } = await client.get<PremiumGlassAnalysis>('/api/dashboard/premium-glass', { params: query });
  return data;
}

export async function getPerformanceDetail(
  query: DashboardQuery & { level: PerformanceDetailLevel; key: string }
): Promise<PerformanceDetailResponse> {
  const { data } = await client.get<PerformanceDetailResponse>('/api/dashboard/performance-detail', { params: query });
  return data;
}
