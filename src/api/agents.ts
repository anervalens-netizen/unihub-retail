import { client } from './client';

export type AgentsQuery = {
  selected_month: string;
  firma?: string;
  regional?: string;
  asm?: string;
  site_code?: string;
  agent?: string;
  search?: string;
};

export interface AgentsOverviewResponse {
  // Snapshot
  active_count: number;
  new_count: number;
  reactivated_count: number;
  left_this_month_count: number;
  retention_rate: number | null;
  
  // Health
  total_unique_agents: number;
  avg_seniority_months: number | null;
  stability_rate: number | null;
  churned_total_count: number;
}

export interface StoreCoverageItem {
  site_code: string;
  locatie: string;
  firma: string;
  regional: string;
  asm: string;
  status: 'covered' | 'uncovered' | 'closed' | 'inactive';
  agent_count: number;
}

export interface StoreCoverageResponse {
  active_stores_count: number;
  uncovered_stores_count: number;
  closed_stores_count: number;
  items: StoreCoverageItem[];
}

export interface AgentMovementPoint {
  month: string;
  active: number;
  new: number;
  reactivated: number;
  churned: number;
  net_growth: number;
}

export interface AgentMovementResponse {
  history: AgentMovementPoint[];
}

export interface AgentListItem {
  agent: string;
  store_name: string | null;
  active_in_month: boolean;
  is_new: boolean;
  is_reactivated: boolean;
  total_sales: number;
  total_quantity: number;
  current_status: string;
}

export interface AgentListResponse {
  items: AgentListItem[];
}

export interface AgentProfileResponse {
  agent: string;
  first_seen_month: string;
  last_seen_month: string;
  active_months_count: number;
  distinct_store_count: number;
  distinct_firma_count: number;
  distinct_regional_count: number;
  distinct_asm_count: number;
  months_since_last_seen: number;
  reactivation_count: number;
  longest_active_streak: number;
  career_total_sales: number;
  career_total_quantity: number;
  avg_monthly_sales: number;
  best_month: string | null;
  best_month_sales: number;
  current_status: string;
}

export interface AgentHistoryPoint {
  month: string;
  total_sales: number;
  total_quantity: number;
  receipt_count: number;
  active_store_count: number;
  is_active: boolean;
}

export interface AgentHistoryResponse {
  history: AgentHistoryPoint[];
}

export async function fetchAgentsOverview(query: AgentsQuery): Promise<AgentsOverviewResponse> {
  const { data } = await client.get<AgentsOverviewResponse>('/api/agents/overview', { params: query });
  return data;
}

export async function fetchAgentsMovement(query: AgentsQuery): Promise<AgentMovementResponse> {
  const { data } = await client.get<AgentMovementResponse>('/api/agents/movement', { params: query });
  return data;
}

export async function fetchAgentsList(query: AgentsQuery): Promise<AgentListResponse> {
  const { data } = await client.get<AgentListResponse>('/api/agents/list', { params: query });
  return data;
}

export async function fetchAgentProfile(agent: string, selectedMonth: string): Promise<AgentProfileResponse> {
  const { data } = await client.get<AgentProfileResponse>('/api/agents/profile', { 
    params: { agent, selected_month: selectedMonth } 
  });
  return data;
}

export async function fetchAgentHistory(agent: string): Promise<AgentHistoryResponse> {
  const { data } = await client.get<AgentHistoryResponse>('/api/agents/history', {
    params: { agent }
  });
  return data;
}

export async function fetchStoreCoverage(query: Partial<AgentsQuery>): Promise<StoreCoverageResponse> {
  const { data } = await client.get<StoreCoverageResponse>('/api/agents/stores-coverage', { params: query });
  return data;
}
