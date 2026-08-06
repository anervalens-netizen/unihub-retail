import { generatedGet, generatedPost } from './generated/client';
import type {
  AgentSalaryLink,
  SalariiOverview,
  SalaryAgentHistory,
  SalaryAgentHistoryRecord,
  SalaryAgentSummary,
  SalaryAgentsSummaryResponse,
  SalaryComparisonPoint,
  SalaryEvolutionPoint,
  SalaryStoreOption,
  SalarySummaryResponse,
  SalaryTrendMonth,
} from './generated/runtime-types';

export async function fetchSalariiOverview(params?: {
  company_name?: string;
  site_code?: string;
  regional?: string;
  asm?: string;
}): Promise<SalariiOverview> {
  return await generatedGet('salarii_overview_salarii_overview_get', { params }) as SalariiOverview;
}

export async function fetchSalaryEvolution(params?: {
  company_name?: string;
  site_code?: string;
  regional?: string;
  asm?: string;
}): Promise<SalaryEvolutionPoint[]> {
  return await generatedGet('salarii_evolution_salarii_evolution_get', { params }) as SalaryEvolutionPoint[];
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
  return await generatedGet('agents_summary_salarii_agents_summary_get', { params }) as SalaryAgentsSummaryResponse;
}

export async function fetchSalaryAgentHistory(personId: string): Promise<SalaryAgentHistory> {
  return await generatedGet('agent_history_salarii_agents__person_id__history_get', {
    pathParams: { person_id: personId },
  }) as SalaryAgentHistory;
}

export async function fetchSalaryAgentHistoryByRetailCode(params: {
  agent_code: string;
  site_code: string;
}): Promise<SalaryAgentHistory> {
  return await generatedGet('agent_history_by_retail_code_salarii_agents_history_by_retail_code_get', { params }) as SalaryAgentHistory;
}

export async function fetchSalarySummary(params: {
  company_name?: string;
  site_code?: string;
  regional?: string;
  asm?: string;
  year?: number;
  month?: number;
}): Promise<SalarySummaryResponse> {
  return await generatedGet('salarii_summary_salarii_summary_get', { params }) as SalarySummaryResponse;
}

export async function fetchSalaryTrend(params?: {
  company_name?: string;
  site_code?: string;
  regional?: string;
  asm?: string;
}): Promise<SalaryTrendMonth[]> {
  return await generatedGet('salarii_trend_salarii_trend_get', { params }) as SalaryTrendMonth[];
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

export type {
  AgentSalaryLink,
  SalariiOverview,
  SalaryAgentHistory,
  SalaryAgentHistoryRecord,
  SalaryAgentSummary,
  SalaryAgentsSummaryResponse,
  SalaryComparisonPoint,
  SalaryEvolutionPoint,
  SalaryStoreOption,
  SalarySummaryResponse,
  SalaryTrendMonth,
};
