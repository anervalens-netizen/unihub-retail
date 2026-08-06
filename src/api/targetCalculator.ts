import { generatedGet, generatedPatch, generatedPost } from './generated/client';
import { downloadBlob } from '../lib/download';
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

export async function fetchTargetCalculatorContext(): Promise<TargetCalculatorContext> {
  return await generatedGet('get_context_api_target_calculator_context_get') as TargetCalculatorContext;
}

export async function fetchTargetScenarios(): Promise<TargetScenarioSummary[]> {
  return await generatedGet('list_scenarios_api_target_calculator_scenarios_get') as TargetScenarioSummary[];
}

export async function fetchTargetScenario(id: number): Promise<TargetScenario> {
  return await generatedGet('get_scenario_api_target_calculator_scenarios__scenario_id__get', {
    pathParams: { scenario_id: id },
  }) as TargetScenario;
}

export async function calculateTargetScenario(input: TargetCalculationInput): Promise<TargetScenario> {
  return await generatedPost('calculate_scenario_api_target_calculator_scenarios_calculate_post', input) as TargetScenario;
}

export async function saveTargetFinalValues(
  id: number,
  expectedRevision: number,
  rows: Array<{ site_code: string; final_target: number | null; note: string | null }>,
): Promise<TargetScenario> {
  return await generatedPatch(
    'update_final_targets_api_target_calculator_scenarios__scenario_id__rows_patch',
    { expected_revision: expectedRevision, rows },
    { pathParams: { scenario_id: id } },
  ) as TargetScenario;
}

export async function fetchTargetStoreDetail(scenarioId: number, siteCode: string): Promise<TargetStoreDetail> {
  return await generatedGet('get_store_detail_api_target_calculator_scenarios__scenario_id__stores__site_code__get', {
    pathParams: { scenario_id: scenarioId, site_code: siteCode },
  }) as TargetStoreDetail;
}

export async function finalizeTargetScenario(id: number, expectedRevision: number): Promise<TargetScenario> {
  return await generatedPost(
    'finalize_scenario_api_target_calculator_scenarios__scenario_id__finalize_post',
    { expected_revision: expectedRevision },
    { pathParams: { scenario_id: id } },
  ) as TargetScenario;
}

export async function downloadTargetScenario(id: number, filename: string): Promise<void> {
  const data = await generatedGet('export_scenario_api_target_calculator_scenarios__scenario_id__export_get', {
    pathParams: { scenario_id: id },
    responseType: 'blob',
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
