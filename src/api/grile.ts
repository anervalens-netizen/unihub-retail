import { client } from './client';

export interface GrileRun {
  id: number;
  run_month: string;
  source: 'manual' | 'auto';
  source_snapshot_id: number | null;
  status: 'queued' | 'running' | 'completed' | 'failed';
  progress_current: number;
  progress_total: number;
  ok_count: number;
  problem_count: number;
  error_count: number;
  duration_ms: number | null;
  triggered_by_email: string | null;
  error_message: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string | null;
}

export interface GrileStore {
  site_code: string;
  sheet_id: string | null;
  locatie: string;
  firma: string;
  regional: string;
  asm: string;
  team_leader_name: string;
  completion_pct: number | null;
  last_edit: string | null;
  grila_target: number | null;
  grila_sales: number | null;
  db_target: number | null;
  db_sales_mtd: number | null;
  target_diff: number | null;
  sales_diff: number | null;
  db_max_sale_date: string | null;
  fill_status: string | null;
  target_status: string | null;
  sales_status: string | null;
  missing_days: number[] | null;
  days_elapsed: number | null;
  error_code: string | null;
  error_message: string | null;
}

export interface GrileFirm {
  name: string;
  stores: GrileStore[];
}

export interface GrileTeamLeader {
  name: string;
  firms: GrileFirm[];
}

export interface GrileManager {
  name: string;
  store_count: number;
  ok: number;
  problems: number;
  avg_completion: number | null;
  team_leaders: GrileTeamLeader[];
}

export interface GrileOverview {
  month: string;
  total_sheets: number;
  run: GrileRun | null;
  managers: GrileManager[];
}

export async function getGrileOverview(month?: string): Promise<GrileOverview> {
  const { data } = await client.get<GrileOverview>('/api/grile/overview', {
    params: month ? { month } : {},
  });
  return data;
}

export async function runGrileCheck(
  month?: string,
): Promise<{ status: 'enqueued' | 'already_running'; run?: GrileRun; month?: string }> {
  const { data } = await client.post<{ status: 'enqueued' | 'already_running'; run?: GrileRun; month?: string }>(
    '/api/grile/run',
    {},
    { params: month ? { month } : {} },
  );
  return data;
}

export async function getGrileRunStatus(month?: string): Promise<{ run: GrileRun | null }> {
  const { data } = await client.get<{ run: GrileRun | null }>('/api/grile/run-status', {
    params: month ? { month } : {},
  });
  return data;
}
