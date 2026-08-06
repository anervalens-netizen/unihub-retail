import { generatedGet, generatedPatch, generatedPost } from './generated/client';
import { downloadBlob } from '../lib/download';
import type { RetailOperationPaths } from './generated/contracts';
import type {
  TargetCalculationDetails,
  TargetCalculationInput,
  TargetCalculatorContext,
  TargetHistoryValue,
  TargetProfitability,
  TargetProfitabilitySummary,
  TargetRegionalSummary,
  TargetScenario,
  TargetScenarioRow,
  TargetScenarioSummary,
  TargetSeasonalityYear,
  TargetSourceMonth,
  TargetSourceSummary,
  TargetStoreAgent,
  TargetStoreDetail,
  TargetStoreHistoryPoint,
} from './generated/runtime-types';
import type { GeneratedRequest } from './generated/runtime-types';

export async function fetchTargetCalculatorContext(): Promise<TargetCalculatorContext> {
  return generatedGet('get_context_api_target_calculator_context_get');
}

export async function fetchTargetScenarios(): Promise<TargetScenarioSummary[]> {
  return generatedGet('list_scenarios_api_target_calculator_scenarios_get');
}

export async function fetchTargetScenario(id: RetailOperationPaths['get_scenario_api_target_calculator_scenarios__scenario_id__get']['scenario_id']): Promise<TargetScenario> {
  return await generatedGet('get_scenario_api_target_calculator_scenarios__scenario_id__get', {
    pathParams: { scenario_id: id },
  });
}

export async function calculateTargetScenario(input: TargetCalculationInput): Promise<TargetScenario> {
  return generatedPost('calculate_scenario_api_target_calculator_scenarios_calculate_post', input);
}

export async function saveTargetFinalValues(
  id: RetailOperationPaths['update_final_targets_api_target_calculator_scenarios__scenario_id__rows_patch']['scenario_id'],
  request: GeneratedRequest<'update_final_targets_api_target_calculator_scenarios__scenario_id__rows_patch'>,
): Promise<TargetScenario> {
  return await generatedPatch(
    'update_final_targets_api_target_calculator_scenarios__scenario_id__rows_patch',
    request,
    { pathParams: { scenario_id: id } },
  );
}

export async function fetchTargetStoreDetail(
  scenarioId: RetailOperationPaths['get_store_detail_api_target_calculator_scenarios__scenario_id__stores__site_code__get']['scenario_id'],
  siteCode: RetailOperationPaths['get_store_detail_api_target_calculator_scenarios__scenario_id__stores__site_code__get']['site_code'],
): Promise<TargetStoreDetail> {
  return await generatedGet('get_store_detail_api_target_calculator_scenarios__scenario_id__stores__site_code__get', {
    pathParams: { scenario_id: scenarioId, site_code: siteCode },
  });
}

export async function finalizeTargetScenario(
  id: RetailOperationPaths['finalize_scenario_api_target_calculator_scenarios__scenario_id__finalize_post']['scenario_id'],
  request: GeneratedRequest<'finalize_scenario_api_target_calculator_scenarios__scenario_id__finalize_post'>,
): Promise<TargetScenario> {
  return await generatedPost(
    'finalize_scenario_api_target_calculator_scenarios__scenario_id__finalize_post',
    request,
    { pathParams: { scenario_id: id } },
  );
}

export async function downloadTargetScenario(
  id: RetailOperationPaths['export_scenario_api_target_calculator_scenarios__scenario_id__export_get']['scenario_id'],
  filename: string,
): Promise<void> {
  const data = await generatedGet('export_scenario_api_target_calculator_scenarios__scenario_id__export_get', {
    pathParams: { scenario_id: id },
  });
  downloadBlob(data, filename);
}

export type {
  TargetCalculationDetails,
  TargetCalculationInput,
  TargetCalculatorContext,
  TargetHistoryValue,
  TargetProfitability,
  TargetProfitabilitySummary,
  TargetRegionalSummary,
  TargetScenario,
  TargetScenarioRow,
  TargetScenarioSummary,
  TargetSeasonalityYear,
  TargetSourceMonth,
  TargetSourceSummary,
  TargetStoreAgent,
  TargetStoreDetail,
  TargetStoreHistoryPoint,
};
