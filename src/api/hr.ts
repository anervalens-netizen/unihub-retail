import { generatedGet } from './generated/client';

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
  return generatedGet('get_asm_perf_api_hr_asm_performance_get', { params: { month, regional } }) as unknown as AsmPerformance[];
}

export async function fetchAsmHistory(asmName: string, months = 6): Promise<AsmHistoryPoint[]> {
  return generatedGet('get_asm_perf_history_api_hr_asm_performance__asm_name__history_get', {
    pathParams: { asm_name: asmName },
    params: { months },
  }) as unknown as AsmHistoryPoint[];
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
  return generatedGet('get_manager_overview_api_hr_manager_overview_get', { params: { month }, signal }) as unknown as ManagerOverview[];
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
  return generatedGet('get_asm_salary_api_hr_asm_salary__asm_name__get', {
    pathParams: { asm_name: asm },
    params: { month },
  }) as unknown as AsmSalaryBreakdown;
}
