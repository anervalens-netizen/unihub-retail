import { client } from './client';

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

export interface StoreAlert {
  site_code: string;
  locatie: string;
  regional: string;
  asm: string;
  score: number;
  reasons: string[];
}

export async function fetchScores(month: string): Promise<StoreScore[]> {
  const { data } = await client.get<StoreScore[]>('/api/crm/scores', { params: { month } });
  return data;
}

export async function recalculateScores(month: string): Promise<{ recalculated: number; month: string }> {
  const { data } = await client.post<{ recalculated: number; month: string }>('/api/crm/scores/recalculate', null, { params: { month } });
  return data;
}

export async function fetchAlerts(month: string): Promise<StoreAlert[]> {
  const { data } = await client.get<StoreAlert[]>('/api/crm/alerts', { params: { month } });
  return data;
}
