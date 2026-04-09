import axios from 'axios';

const api = axios.create({ baseURL: '/api/crm' });

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('unihub_token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

export interface StoreScore {
  site_code: string;
  locatie: string;
  regional: string;
  asm: string;
  score: number;
  breakdown: {
    target_pct: number;
    trend_pct: number;
    active_days_pct: number;
    visits_pct: number;
    target_attainment: number;
    forecast_factor: number;
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
  const { data } = await api.get('/scores', { params: { month } });
  return data;
}

export async function recalculateScores(month: string): Promise<{ recalculated: number; month: string }> {
  const { data } = await api.post('/scores/recalculate', null, { params: { month } });
  return data;
}

export async function fetchAlerts(month: string): Promise<StoreAlert[]> {
  const { data } = await api.get('/alerts', { params: { month } });
  return data;
}
