import { generatedGet, generatedPost } from './generated/client';
import type { RetailOperationPaths, RetailOperationQueries } from './generated/contracts';
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
import type { GeneratedRequest } from './generated/runtime-types';

export type SalariiOverviewQuery = RetailOperationQueries['salarii_overview_salarii_overview_get'];
export type SalaryEvolutionQuery = RetailOperationQueries['salarii_evolution_salarii_evolution_get'];
export type SalaryAgentsQuery = RetailOperationQueries['agents_summary_salarii_agents_summary_get'];
export type SalaryHistoryByRetailCodeQuery = RetailOperationQueries['agent_history_by_retail_code_salarii_agents_history_by_retail_code_get'];
export type SalarySummaryQuery = RetailOperationQueries['salarii_summary_salarii_summary_get'];
export type SalaryTrendQuery = RetailOperationQueries['salarii_trend_salarii_trend_get'];

export async function fetchSalariiOverview(params?: SalariiOverviewQuery): Promise<SalariiOverview> {
  return generatedGet('salarii_overview_salarii_overview_get', { params });
}

export async function fetchSalaryEvolution(params?: SalaryEvolutionQuery): Promise<SalaryEvolutionPoint[]> {
  return generatedGet('salarii_evolution_salarii_evolution_get', { params });
}

export async function fetchSalaryAgents(params: SalaryAgentsQuery): Promise<SalaryAgentsSummaryResponse> {
  return generatedGet('agents_summary_salarii_agents_summary_get', { params });
}

export async function fetchSalaryAgentHistory(
  personId: RetailOperationPaths['agent_history_salarii_agents__person_id__history_get']['person_id'],
): Promise<SalaryAgentHistory> {
  return await generatedGet('agent_history_salarii_agents__person_id__history_get', {
    pathParams: { person_id: personId },
  });
}

export async function fetchSalaryAgentHistoryByRetailCode(params: SalaryHistoryByRetailCodeQuery): Promise<SalaryAgentHistory> {
  return generatedGet('agent_history_by_retail_code_salarii_agents_history_by_retail_code_get', { params });
}

export async function fetchSalarySummary(params: SalarySummaryQuery): Promise<SalarySummaryResponse> {
  return generatedGet('salarii_summary_salarii_summary_get', { params });
}

export async function fetchSalaryTrend(params?: SalaryTrendQuery): Promise<SalaryTrendMonth[]> {
  return generatedGet('salarii_trend_salarii_trend_get', { params });
}

export async function auditSalaryExport(
  request: GeneratedRequest<'audit_salary_export_salarii_audit_export_post'>,
): Promise<void> {
  await generatedPost('audit_salary_export_salarii_audit_export_post', request);
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
