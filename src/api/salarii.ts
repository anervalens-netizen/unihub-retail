import { generatedGet, generatedPost, isGeneratedApiError } from './generated/client';
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
import type { ExportOperation } from './exports';

export type SalariiOverviewQuery = RetailOperationQueries['salarii_overview_salarii_overview_get'];
export type SalaryEvolutionQuery = RetailOperationQueries['salarii_evolution_salarii_evolution_get'];
export type SalaryAgentsQuery = RetailOperationQueries['agents_summary_salarii_agents_summary_get'];
export type SalaryHistoryByRetailCodeQuery = RetailOperationQueries['agent_history_by_retail_code_salarii_agents_history_by_retail_code_get'];
export type SalarySummaryQuery = RetailOperationQueries['salarii_summary_salarii_summary_get'];
export type SalaryTrendQuery = RetailOperationQueries['salarii_trend_salarii_trend_get'];
export type SalaryExportRequest = GeneratedRequest<'create_salary_export_operation_salarii_exports_operations_post'>;
export type SalaryExportKind = SalaryExportRequest['export_kind'];

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

export async function createSalaryExportOperation(
  request: SalaryExportRequest,
): Promise<ExportOperation> {
  return generatedPost('create_salary_export_operation_salarii_exports_operations_post', request);
}

export function uncertainSalaryExportOperationId(error: unknown): number | null {
  const operationId = 'create_salary_export_operation_salarii_exports_operations_post';
  if (!isGeneratedApiError(error, operationId) || error.status !== 503) return null;
  const body = error.typedBody;
  if (!body || typeof body !== 'object' || !('detail' in body)) return null;
  const detail = body.detail;
  if (!detail || typeof detail !== 'object' || !('operation_id' in detail)) return null;
  const candidate = detail.operation_id;
  return typeof candidate === 'number' && Number.isInteger(candidate) && candidate > 0
    ? candidate
    : null;
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
