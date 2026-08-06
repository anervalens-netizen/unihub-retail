import { generatedGet, generatedPost } from './generated/client';

export interface SalariiOverview {
  total: number;
  by_company: { name: string; total: number }[];
  record_count: number;
  agent_count: number;
  agent_month_count: number;
  avg_agent_month_count: number;
  avg_salary: number;
  months_span: [number, number, number, number] | null; // [minY, minM, maxY, maxM], null when no data
}

export interface SalaryAgentSummary {
  person_id: string;
  full_name: string;
  company_name: string;
  locatie: string | null;
  month_count: number;
  avg_month_count: number;
  total_salary: number;
  avg_salary: number;
}

export interface SalaryEvolutionPoint {
  month: string;
  total: number;
  mobicell: number;
  mobiup: number;
}

export interface SalaryAgentHistoryRecord {
  year: number;
  month: number;
  company_name: string;
  total_salary: number;
  site_code: string | null;
  locatie: string | null;
}

export interface SalaryAgentHistory {
  link?: AgentSalaryLink | null;
  records: SalaryAgentHistoryRecord[];
  total: number;
  avg: number;
  month_count: number;
  avg_month_count: number;
}

export interface AgentSalaryLink {
  agent_code: string;
  site_code: string;
  salary_full_name: string | null;
  person_id: string | null;
  match_status: 'confirmed' | 'unknown';
  match_source: 'auto' | 'manual';
  confidence: 'high' | 'medium' | 'low' | 'unknown';
  effective_from_month: string | null;
  note: string | null;
}

export interface SalaryComparisonPoint {
  site_code: string;
  locatie: string | null;
  company_name: string;
  total_salary: number;
  agent_count: number;
  avg_agent_count: number;
  avg_salary: number;
  total_sales: number;
  ratio: number;
}

export interface SalarySummaryResponse {
  month: string | null;
  items: SalaryComparisonPoint[];
}

export interface SalaryTrendMonth {
  month: string;
  total_salary: number;
  total_sales: number;
  agent_count: number;
  avg_agent_count: number;
  avg_salary: number;
  by_company: Record<string, {
    total_salary: number;
    total_sales: number;
    agent_count: number;
  }>;
}

export interface SalaryAgentsSummaryResponse {
  items: SalaryAgentSummary[];
  total: number;
}

export async function fetchSalariiOverview(params?: {
  company_name?: string;
  site_code?: string;
  regional?: string;
  asm?: string;
}): Promise<SalariiOverview> {
  return generatedGet('salarii_overview_salarii_overview_get', { params }) as unknown as SalariiOverview;
}

export async function fetchSalaryEvolution(params?: {
  company_name?: string;
  site_code?: string;
  regional?: string;
  asm?: string;
}): Promise<SalaryEvolutionPoint[]> {
  return generatedGet('salarii_evolution_salarii_evolution_get', { params }) as unknown as SalaryEvolutionPoint[];
}

export async function fetchSalaryAgents(params: {
  q?: string;
  company_name?: string;
  site_code?: string;
  regional?: string;
  asm?: string;
  year?: number;
  month?: number;
  limit?: number;
  offset?: number;
}): Promise<SalaryAgentsSummaryResponse> {
  return generatedGet('agents_summary_salarii_agents_summary_get', { params }) as unknown as SalaryAgentsSummaryResponse;
}

export async function fetchSalaryAgentHistory(personId: string): Promise<SalaryAgentHistory> {
  return generatedGet('agent_history_salarii_agents__person_id__history_get', {
    pathParams: { person_id: personId },
  }) as unknown as SalaryAgentHistory;
}

export async function fetchSalaryAgentHistoryByRetailCode(params: {
  agent_code: string;
  site_code: string;
}): Promise<SalaryAgentHistory> {
  return generatedGet('agent_history_by_retail_code_salarii_agents_history_by_retail_code_get', { params }) as unknown as SalaryAgentHistory;
}

export async function fetchSalarySummary(params: {
  company_name?: string;
  site_code?: string;
  regional?: string;
  asm?: string;
  year?: number;
  month?: number;
}): Promise<SalarySummaryResponse> {
  return generatedGet('salarii_summary_salarii_summary_get', { params }) as unknown as SalarySummaryResponse;
}

export async function fetchSalaryTrend(params: {
  company_name?: string;
  site_code?: string;
  regional?: string;
  asm?: string;
}): Promise<SalaryTrendMonth[]> {
  return generatedGet('salarii_trend_salarii_trend_get', { params }) as unknown as SalaryTrendMonth[];
}

export async function auditSalaryExport(
  exportKind: 'store_summary' | 'monthly_trend' | 'agents_page',
  rowCount: number,
): Promise<void> {
  await generatedPost('audit_salary_export_salarii_audit_export_post', {
    export_kind: exportKind,
    row_count: rowCount,
  });
}
