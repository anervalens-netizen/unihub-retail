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
  has_changes: boolean;
  previous_agent_count: number;
  added_agents_count: number;
  removed_agents_count: number;
  change_reason: string | null;
}

export interface StoreCoverageResponse {
  active_stores_count: number;
  uncovered_stores_count: number;
  closed_stores_count: number;
  modified_stores_count: number;
  items: StoreCoverageItem[];
}

export interface AgentMovementPoint {
  month: string;
  active: number;
  new: number;
  reactivated: number;
  churned: number;
  net_growth: number;
  is_baseline: boolean;
}

export interface AgentMovementResponse {
  history: AgentMovementPoint[];
}

export interface AgentListItem {
  agent: string;
  store_name: string | null;
  firma: string | null;
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

export interface AgentEvaluationOption {
  value: string;
  label: string;
}

export interface AgentEvaluationRow {
  month: string;
  firma: string;
  site_code: string;
  locatie: string;
  regional: string;
  asm: string;
  agent: string;
  total_sales: number;
  total_quantity: number;
  working_days: number;
  store_target: number;
  store_working_days: number;
  target_value: number;
  target_pct: number | null;
  daily_average: number | null;
  peer_daily_average: number | null;
  value_reper: number | null;
  receipt_count: number;
  receipt_2plus_count: number;
  bonuri_pct: number | null;
  focus_quantity: number;
  focus_pct: number | null;
  glass_qty: number;
  premium_glass_qty: number;
  premium_glass_pct: number | null;
  target_points: number;
  daily_points: number;
  value_reper_points: number;
  bonuri_points: number;
  focus_points: number;
  premium_glass_points: number;
  total_points: number;
  has_red_segment: boolean;
  qualifier: string;
}

export interface AgentEvaluationResponse {
  months: AgentEvaluationOption[];
  firmas: AgentEvaluationOption[];
  asms: AgentEvaluationOption[];
  stores: AgentEvaluationOption[];
  rows: AgentEvaluationRow[];
}

export interface AgentEvaluationV2Row {
  month: string;
  firma: string;
  site_code: string;
  locatie: string;
  regional: string;
  asm: string;
  agent: string;
  total_sales: number;
  forecast_sales: number;
  total_quantity: number;
  working_days: number;
  receipt_count: number;
  target_value: number;
  target_source: string;
  target_pct: number | null;
  target_forecast_pct: number | null;
  is_partial: boolean;
  period_month_count: number;
  partial_month_count: number;
  final_month_count: number;
  forecast_factor: number;
  daily_average: number | null;
  daily_reference: number | null;
  daily_reference_type: string;
  daily_vs_reference_pct: number | null;
  value_reper: number | null;
  receipt_2plus_count: number;
  bonuri_pct: number | null;
  focus_quantity: number;
  focus_pct: number | null;
  glass_qty: number;
  premium_glass_qty: number;
  premium_glass_pct: number | null;
  trend_daily_pct: number | null;
  trend_direction: 'up' | 'down' | 'flat';
  eligibility_status: 'eligibil' | 'insuficient';
  confidence_flags: string[];
  target_score: number | null;
  daily_score: number | null;
  bonuri_score: number | null;
  focus_score: number | null;
  premium_glass_score: number | null;
  value_reper_score: number | null;
  total_score: number | null;
  max_score: number;
  rating: string;
}

export interface AgentEvaluationV2Response {
  months: AgentEvaluationOption[];
  firmas: AgentEvaluationOption[];
  asms: AgentEvaluationOption[];
  stores: AgentEvaluationOption[];
  rows: AgentEvaluationV2Row[];
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

export async function fetchAgentEvaluation(params: {
  month?: string;
  months?: string;
  firma?: string;
  asm?: string;
  site_code?: string;
} = {}): Promise<AgentEvaluationResponse> {
  const { data } = await client.get<AgentEvaluationResponse>('/api/agents/evaluation', { params });
  return data;
}

export async function fetchAgentEvaluationV2(params: {
  month?: string;
  months?: string;
  firma?: string;
  asm?: string;
  site_code?: string;
} = {}): Promise<AgentEvaluationV2Response> {
  const { data } = await client.get<AgentEvaluationV2Response>('/api/agents/evaluation-v2', { params });
  return data;
}
