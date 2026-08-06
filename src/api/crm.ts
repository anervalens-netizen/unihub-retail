import { generatedGet } from './generated/client';

export interface StoreScore {
  site_code: string;
  locatie: string;
  regional: string;
  asm: string;
  score: number;
  breakdown: {
    target_pct: number;
    trend_pct: number;
    kpi_pct: number;
    kpi_bon2acc_score: number;
    kpi_focus_score: number;
    visits_pct: number;
    target_attainment: number;
    forecast_factor: number;
    kpi_bon2acc: number;
    kpi_focus: number;
    kpi_bon2acc_avg: number;
    kpi_focus_avg: number;
    nr_vizite: number;
    avg_completion: number;
  } | null;
  calculated_at: string;
}

export async function fetchScores(month: string): Promise<StoreScore[]> {
  return generatedGet('get_scores_api_crm_scores_get', { params: { month } }) as unknown as StoreScore[];
}
