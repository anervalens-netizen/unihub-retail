import { client } from './client';
import type {
  AgentStat,
  DailySalesPoint,
  DashboardAllResponse,
  DashboardHistoryResponse,
  DashboardSpecialCardsResponse,
  DashboardSummary,
  MonthlyHistoryPoint,
  StoreAgentStats,
  StoreStat,
} from './types';

export interface DashboardQuery {
  month: string;
  firma?: string;
  regional?: string;
  asm?: string;
  site_code?: string;
  agent?: string;
}

export async function getSummary(query: DashboardQuery): Promise<DashboardSummary> {
  const { data } = await client.get<DashboardSummary>('/api/dashboard/summary', {
    params: query,
  });
  return data;
}

export async function getAgentStats(query: DashboardQuery): Promise<AgentStat[]> {
  const { data } = await client.get<AgentStat[]>('/api/dashboard/agents', { params: query });
  return data;
}

export async function getStoreStats(query: Omit<DashboardQuery, 'site_code'>): Promise<StoreStat[]> {
  const { data } = await client.get<StoreStat[]>('/api/dashboard/stores', { params: query });
  return data;
}

export async function getDailySales(query: DashboardQuery): Promise<DailySalesPoint[]> {
  const { data } = await client.get<DailySalesPoint[]>('/api/dashboard/daily', { params: query });
  return data;
}

export async function getSpecialCards(query: DashboardQuery): Promise<DashboardSpecialCardsResponse> {
  const { data } = await client.get<DashboardSpecialCardsResponse>('/api/dashboard/special-cards', { params: query });
  return data;
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

export async function getMonthlyHistory(
  query: DashboardQuery & { months_back?: number }
): Promise<MonthlyHistoryPoint[]> {
  const { data } = await client.get<DashboardHistoryResponse>('/api/dashboard/history', { params: query });
  return data.history;
}

export async function getStoreAgentStats(siteCode: string, month: string): Promise<StoreAgentStats[]> {
  const { data } = await client.get<StoreAgentStats[]>('/api/dashboard/store-agent-stats', {
    params: { site_code: siteCode, month },
  });
  return data;
}
