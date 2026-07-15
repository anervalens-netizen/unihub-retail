import { client } from './client';
import { formatMonthLabel } from '../lib/dates';
import { downloadBlob } from '../lib/download';

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
  name: string | null; // null = magazine fara Team Leader (nu se afiseaza bara TL)
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

// ── Inchidere luna ─────────────────────────────────────────────────────────────

export type GrileMonthlyOp = 'finalize' | 'archive' | 'reset';

export interface GrileMonthlyResult {
  op: GrileMonthlyOp;
  month_label: string;
  status: 'success' | 'failed';
  output: string;
  exit_code: number | null;
  dry_run?: boolean | null;
}

export interface GrileMonthlyEnqueue {
  status: 'enqueued' | 'already_running' | 'already_completed';
  job_id: string | null;
  operation_id: number;
  op: GrileMonthlyOp;
  month: string;
  month_label: string;
  next_month_label?: string;
  dry_run?: boolean;
  operation?: Record<string, unknown>;
}

export interface GrileMonthlyJob {
  job_id: string;
  status: 'queued' | 'in_progress' | 'complete' | 'not_found';
  result: GrileMonthlyResult | null;
  error: string | null;
}

export async function getGrileMonthlyPermissions(): Promise<{ can_run: boolean }> {
  const { data } = await client.get<{ can_run: boolean }>('/api/grile/monthly/permissions');
  return data;
}

export async function runGrileMonthly(body: {
  op: GrileMonthlyOp;
  month: string;
  only?: string | null;
  dry_run?: boolean;
}): Promise<GrileMonthlyEnqueue> {
  const { data } = await client.post<GrileMonthlyEnqueue>('/api/grile/monthly/run', body);
  return data;
}

export async function getGrileMonthlyJob(jobId: string): Promise<GrileMonthlyJob> {
  const { data } = await client.get<GrileMonthlyJob>(`/api/grile/monthly/job/${jobId}`);
  return data;
}

export async function downloadGrileMonthly(kind: 'final' | 'archive', month: string): Promise<void> {
  const { data } = await client.get<Blob>(`/api/grile/monthly/download/${kind}/${month}`, {
    responseType: 'blob',
  });
  const monthLabel = formatMonthLabel(month, { month: 'long' });
  downloadBlob(
    data,
    kind === 'final' ? `Tabel Salarii - ${monthLabel}.xlsx` : `Arhiva Grile - ${monthLabel}.zip`,
  );
}
