import { client } from './client';
import type {
  DashboardAllResponse,
  DashboardHistoryResponse,
  YearHistoryResponse,
} from './types';

export interface DashboardQuery {
  month: string;
  firma?: string;
  regional?: string;
  asm?: string;
  site_code?: string;
  agent?: string;
}

export async function getDashboardAll(query: DashboardQuery): Promise<DashboardAllResponse> {
  const { data } = await client.get<DashboardAllResponse>('/api/dashboard/all', { params: query });
  return data;
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
