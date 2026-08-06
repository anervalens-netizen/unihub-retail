import { generatedGet } from './generated/client';
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

export type AgentsQuery = {
  selected_month: string;
  firma?: string;
  regional?: string;
  asm?: string;
  site_code?: string;
  agent?: string;
  search?: string;
};

export async function fetchAgentsOverview(query: AgentsQuery, signal?: AbortSignal): Promise<AgentsOverviewResponse> {
  return await generatedGet('get_agents_overview_api_agents_overview_get', { params: query, signal }) as AgentsOverviewResponse;
}

export async function fetchAgentsMovement(query: AgentsQuery, signal?: AbortSignal): Promise<AgentMovementResponse> {
  return await generatedGet('get_agents_movement_api_agents_movement_get', { params: query, signal }) as AgentMovementResponse;
}

export async function fetchAgentsList(query: AgentsQuery, signal?: AbortSignal): Promise<AgentListResponse> {
  return await generatedGet('get_agents_list_api_agents_list_get', { params: query, signal }) as AgentListResponse;
}

export async function fetchAgentProfile(agent: string, selectedMonth: string, signal?: AbortSignal): Promise<AgentProfileResponse> {
  return await generatedGet('get_agent_profile_api_agents_profile_get', {
    params: { agent, selected_month: selectedMonth },
    signal,
  }) as AgentProfileResponse;
}

export async function fetchAgentHistory(agent: string, signal?: AbortSignal): Promise<AgentHistoryResponse> {
  return await generatedGet('get_agent_history_api_agents_history_get', {
    params: { agent },
    signal,
  }) as AgentHistoryResponse;
}

export async function fetchStoreCoverage(query: Partial<AgentsQuery>, signal?: AbortSignal): Promise<StoreCoverageResponse> {
  return await generatedGet('get_stores_coverage_api_agents_stores_coverage_get', { params: query, signal }) as StoreCoverageResponse;
}

export async function fetchAgentEvaluation(params: {
  month?: string;
  months?: string;
  firma?: string;
  asm?: string;
  site_code?: string;
} = {}): Promise<AgentEvaluationResponse> {
  return await generatedGet('get_agent_evaluation_api_agents_evaluation_get', { params }) as AgentEvaluationResponse;
}

export async function fetchAgentEvaluationV2(params: {
  month?: string;
  months?: string;
  firma?: string;
  asm?: string;
  site_code?: string;
} = {}): Promise<AgentEvaluationV2Response> {
  return await generatedGet('get_agent_evaluation_v2_api_agents_evaluation_v2_get', { params }) as AgentEvaluationV2Response;
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
