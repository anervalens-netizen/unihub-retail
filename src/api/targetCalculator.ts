import { client } from './client';

export interface TargetCalculatorContext {
  latest_sales_month: string;
  suggested_target_month: string;
  suggested_cohort_month: string;
  suggested_total_target: number;
  default_min_floor: number;
  default_previous_month_floor_pct: number;
  active_store_count: number;
  regionals: string[];
  can_finalize: boolean;
}

export interface TargetSourceMonth {
  month: string;
  label: string;
  role: string;
}

export interface TargetHistoryValue extends TargetSourceMonth {
  target: number;
  realized: number;
  actual_realized?: number;
  is_forecast?: boolean;
  forecast_factor?: number;
  attainment_pct: number | null;
  weight: number;
}

export interface TargetScenarioRow {
  site_code: string;
  locatie: string;
  firma: string;
  regional: string;
  asm: string;
  calculated_weight: number;
  floor_target: number;
  proposed_target: number;
  final_target: number | null;
  is_floor_limited: boolean;
  history: TargetHistoryValue[];
  note: string | null;
  updated_at: string;
}

export interface TargetRegionalSummary {
  regional: string;
  store_count: number;
  floor_total: number;
  proposed_total: number;
  final_total: number;
}

export interface TargetSourceSummary {
  month: string;
  label: string;
  target: number;
  realized: number;
  actual_realized: number;
  is_forecast: boolean;
  forecast_factor: number;
  attainment_pct: number | null;
}

export interface TargetScenarioSummary {
  id: number;
  target_month: string;
  cohort_month: string;
  total_target: number;
  min_floor: number;
  previous_month_floor_pct: number;
  status: 'draft' | 'finalized';
  calculation_method: string;
  source_months: TargetSourceMonth[];
  warnings: string[];
  store_count: number;
  proposed_total: number;
  final_total: number;
  created_at: string;
  updated_at: string;
  finalized_at: string | null;
}

export interface TargetScenario extends TargetScenarioSummary {
  remaining_difference: number;
  pending_final_count: number;
  floor_limited_count: number;
  manual_adjustments_count: number;
  rows: TargetScenarioRow[];
  regional_summary: TargetRegionalSummary[];
  source_summary: TargetSourceSummary[];
}

export interface TargetCalculationInput {
  target_month: string;
  total_target: number;
  min_floor: number;
  previous_month_floor_pct: number;
}

export async function fetchTargetCalculatorContext(): Promise<TargetCalculatorContext> {
  const { data } = await client.get<TargetCalculatorContext>('/api/target-calculator/context');
  return data;
}

export async function fetchTargetScenarios(): Promise<TargetScenarioSummary[]> {
  const { data } = await client.get<TargetScenarioSummary[]>('/api/target-calculator/scenarios');
  return data;
}

export async function fetchTargetScenario(id: number): Promise<TargetScenario> {
  const { data } = await client.get<TargetScenario>(`/api/target-calculator/scenarios/${id}`);
  return data;
}

export async function calculateTargetScenario(input: TargetCalculationInput): Promise<TargetScenario> {
  const { data } = await client.post<TargetScenario>('/api/target-calculator/scenarios/calculate', input);
  return data;
}

export async function saveTargetFinalValues(
  id: number,
  rows: Array<{ site_code: string; final_target: number | null; note: string | null }>,
): Promise<TargetScenario> {
  const { data } = await client.patch<TargetScenario>(`/api/target-calculator/scenarios/${id}/rows`, { rows });
  return data;
}

export interface TargetStoreHistoryPoint {
  month: string;
  total_sales: number;
  target_value: number;
  target_pct: number | null;
  total_quantity: number;
  receipt_count: number;
  cartele_qty: number;
  avg_receipt: number | null;
  bon2acc_pct: number | null;
  focus_pct: number | null;
  active_agents: number;
  working_days: number;
}

export interface TargetStoreAgent {
  agent: string;
  total_sales: number;
  sales_share_pct: number;
  total_quantity: number;
  receipt_count: number;
  avg_receipt: number | null;
  bon2acc_pct: number | null;
  focus_pct: number | null;
  active_months_16: number;
  sales_16m: number;
}

export interface TargetStoreDetail {
  site_code: string;
  locatie: string;
  firma: string;
  regional: string;
  asm: string;
  target_month: string;
  cohort_month: string;
  proposed_target: number;
  final_target: number | null;
  history: TargetStoreHistoryPoint[];
  latest: TargetStoreHistoryPoint | null;
  best_month: TargetStoreHistoryPoint | null;
  avg_sales_16m: number;
  agents: TargetStoreAgent[];
}

export async function fetchTargetStoreDetail(scenarioId: number, siteCode: string): Promise<TargetStoreDetail> {
  const { data } = await client.get<TargetStoreDetail>(
    `/api/target-calculator/scenarios/${scenarioId}/stores/${encodeURIComponent(siteCode)}`,
  );
  return data;
}

export async function finalizeTargetScenario(id: number): Promise<TargetScenario> {
  const { data } = await client.post<TargetScenario>(`/api/target-calculator/scenarios/${id}/finalize`);
  return data;
}

export async function downloadTargetScenario(id: number, filename: string): Promise<void> {
  const { data } = await client.get<Blob>(`/api/target-calculator/scenarios/${id}/export`, { responseType: 'blob' });
  const url = URL.createObjectURL(data);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}
