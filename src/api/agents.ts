import { generatedGet } from './generated/client';
import type { RetailOperationQueries } from './generated/contracts';
import type {
  AgentEvaluationOption,
  AgentEvaluationResponse,
  AgentEvaluationRow,
  AgentEvaluationV2Response,
  AgentEvaluationV2Row,
  AgentHistoryPoint,
  AgentHistoryResponse,
  AgentListItem,
  AgentListResponse,
  AgentMovementPoint,
  AgentMovementResponse,
  AgentProfileResponse,
  AgentsOverviewResponse,
  StoreCoverageItem,
  StoreCoverageResponse,
} from './generated/runtime-types';

export type AgentsQuery = RetailOperationQueries['get_agents_overview_api_agents_overview_get'];
export type AgentEvaluationQuery = RetailOperationQueries['get_agent_evaluation_api_agents_evaluation_get'];
export type AgentEvaluationV2Query = RetailOperationQueries['get_agent_evaluation_v2_api_agents_evaluation_v2_get'];

export async function fetchAgentsOverview(query: AgentsQuery, signal?: AbortSignal): Promise<AgentsOverviewResponse> {
  return generatedGet('get_agents_overview_api_agents_overview_get', { params: query, signal });
}

export async function fetchAgentsMovement(query: RetailOperationQueries['get_agents_movement_api_agents_movement_get'], signal?: AbortSignal): Promise<AgentMovementResponse> {
  return generatedGet('get_agents_movement_api_agents_movement_get', { params: query, signal });
}

export async function fetchAgentsList(query: RetailOperationQueries['get_agents_list_api_agents_list_get'], signal?: AbortSignal): Promise<AgentListResponse> {
  return generatedGet('get_agents_list_api_agents_list_get', { params: query, signal });
}

export async function fetchAgentProfile(agent: string, selectedMonth: string, signal?: AbortSignal): Promise<AgentProfileResponse> {
  return await generatedGet('get_agent_profile_api_agents_profile_get', {
    params: { agent, selected_month: selectedMonth },
    signal,
  });
}

export async function fetchAgentHistory(agent: string, signal?: AbortSignal): Promise<AgentHistoryResponse> {
  return await generatedGet('get_agent_history_api_agents_history_get', {
    params: { agent },
    signal,
  });
}

export async function fetchStoreCoverage(query: RetailOperationQueries['get_stores_coverage_api_agents_stores_coverage_get'], signal?: AbortSignal): Promise<StoreCoverageResponse> {
  return generatedGet('get_stores_coverage_api_agents_stores_coverage_get', { params: query, signal });
}

export async function fetchAgentEvaluation(params: AgentEvaluationQuery = {}): Promise<AgentEvaluationResponse> {
  return generatedGet('get_agent_evaluation_api_agents_evaluation_get', { params });
}

export async function fetchAgentEvaluationV2(params: AgentEvaluationV2Query = {}): Promise<AgentEvaluationV2Response> {
  return generatedGet('get_agent_evaluation_v2_api_agents_evaluation_v2_get', { params });
}

export type {
  AgentEvaluationOption,
  AgentEvaluationResponse,
  AgentEvaluationRow,
  AgentEvaluationV2Response,
  AgentEvaluationV2Row,
  AgentHistoryPoint,
  AgentHistoryResponse,
  AgentListItem,
  AgentListResponse,
  AgentMovementPoint,
  AgentMovementResponse,
  AgentProfileResponse,
  AgentsOverviewResponse,
  StoreCoverageItem,
  StoreCoverageResponse,
};
