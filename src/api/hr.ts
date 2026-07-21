import { client } from './client';

export interface AsmPerformance {
  asm: string;
  regional: string;
  total_sales: number;
  total_target: number;
  target_pct: number | null;
  forecast_sales: number;
  forecast_target_pct: number | null;
  is_forecast: boolean;
  active_stores: number;
  active_agents: number;
  pct_bon2acc: number;
  pct_focus: number;
  total_visits: number;
  avg_completion: number | null;
  avg_duration: number | null;
  distinct_stores_visited: number;
  checklist_score: number | null;
  approved_pct: number | null;
}

export interface AsmHistoryPoint {
  month: string;
  total_sales: number;
  total_target: number;
  target_pct: number | null;
  forecast_sales: number;
  forecast_target_pct: number | null;
  is_forecast: boolean;
  active_stores: number;
  total_visits: number;
  avg_completion: number | null;
  avg_duration: number | null;
}

export async function fetchAsmPerformance(month: string, regional?: string): Promise<AsmPerformance[]> {
  const { data } = await client.get<AsmPerformance[]>('/api/hr/asm-performance', { params: { month, regional } });
  return data;
}

export async function fetchAsmHistory(asmName: string, months = 6): Promise<AsmHistoryPoint[]> {
  const { data } = await client.get<AsmHistoryPoint[]>(`/api/hr/asm-performance/${encodeURIComponent(asmName)}/history`, { params: { months } });
  return data;
}

export interface ManagerStoreOverview {
  site_code: string;
  locatie: string;
  firma: string;
  active_agents: number;
  previous_active_agents: number;
  agent_delta: number;
}

export interface ManagerOverview {
  manager: string;
  regional: string;
  month: string;
  reporting_available: boolean;
  active_stores: number;
  active_agents: number;
  previous_active_agents: number;
  agent_delta: number;
  agents_added: number;
  agents_left: number;
  stores_without_agents: number;
  agents_per_store: number;
  visits_available: boolean;
  total_visits: number;
  visited_stores: number;
  visit_coverage_pct: number | null;
  avg_visit_completion: number | null;
  checklist_score: number | null;
  approved_pct: number | null;
  stores: ManagerStoreOverview[];
}

export async function fetchManagerOverview(month: string, signal?: AbortSignal): Promise<ManagerOverview[]> {
  const { data } = await client.get<ManagerOverview[]>('/api/hr/manager-overview', { params: { month }, signal });
  return data;
}

export interface AsmSalaryIsland {
  site_code: string;
  locatie: string;
  firma: string;
  total_sales: number;
  total_target: number;
  target_pct: number | null;
  forecast_sales: number;
  forecast_target_pct: number | null;
  pct_used: number | null;
  commission: number;
}

export interface AsmSalaryBreakdown {
  asm: string;
  month: string;
  is_forecast: boolean;
  forecast_factor: number;
  fixed_salary: number;
  zone: {
    total_sales: number;
    total_target: number;
    target_pct: number | null;
    forecast_sales: number;
    forecast_target_pct: number | null;
    pct_used: number | null;
    commission: number;
  };
  islands: AsmSalaryIsland[];
  islands_commission: number;
  homogeneity: {
    islands_count: number;
    qualifying_count: number;
    qualifying_pct: number;
    min_pct: number;
    eligible: boolean;
    commission: number;
  };
  acc_focus: {
    pct: number;
    commission: number;
  };
  total_salary: number;
}

export async function fetchAsmSalary(asm: string, month: string): Promise<AsmSalaryBreakdown> {
  const { data } = await client.get<AsmSalaryBreakdown>(
    `/api/hr/asm-salary/${encodeURIComponent(asm)}`,
    { params: { month } },
  );
  return data;
}
