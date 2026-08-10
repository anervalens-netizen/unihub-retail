import { client } from './client';
import { generatedGet, generatedPost } from './generated/client';
import type {
  RetailGrileFirmResponse,
  RetailGrileManagerResponse,
  RetailGrileMonthlyManifestResponse,
  RetailGrileOverviewResponse,
  RetailGrileOverviewSummary,
  RetailGrilePilotV2OverviewResponse,
  RetailGrileProviderStatus,
  RetailGrileRunEnqueueResponse,
  RetailGrileRunResponse,
  RetailGrileStoreRefreshEnqueueResponse,
  RetailGrileStoreRefreshOperationResponse,
  RetailGrileStoreResponse,
  RetailGrileTeamLeaderResponse,
  RetailMonthlyRunRequest,
} from './generated/contracts';
import type { RequiredRuntime } from './generated/runtime-types';
import { formatMonthLabel } from '../lib/dates';
import { downloadBlob } from '../lib/download';

export type GrileRun = RequiredRuntime<RetailGrileRunResponse>;
export type GrileProviderStatus = RequiredRuntime<RetailGrileProviderStatus>;
export type GrileProviderState = GrileProviderStatus['state'];
export type GrileStore = RequiredRuntime<RetailGrileStoreResponse>;
export type GrileFirm = RequiredRuntime<RetailGrileFirmResponse>;
export type GrileTeamLeader = RequiredRuntime<RetailGrileTeamLeaderResponse>;
export type GrileManager = RequiredRuntime<RetailGrileManagerResponse>;
export type GrileOverviewSummary = RequiredRuntime<RetailGrileOverviewSummary>;
export type GrileOverview = RequiredRuntime<RetailGrileOverviewResponse>;
export type GrilePilotV2Overview = RequiredRuntime<RetailGrilePilotV2OverviewResponse>;
export type GrileStoreRefreshEnqueue = RequiredRuntime<RetailGrileStoreRefreshEnqueueResponse>;
export type GrileStoreRefreshOperation = RequiredRuntime<RetailGrileStoreRefreshOperationResponse>;

type GrileRunEnqueue = RequiredRuntime<RetailGrileRunEnqueueResponse>;

export async function getGrileOverview(
  month?: string,
  signal?: AbortSignal,
): Promise<GrileOverview> {
  return generatedGet('grile_overview_api_grile_overview_get', {
    params: month ? { month } : undefined,
    signal,
  });
}

export async function getGrilePilotV2(
  month = '2026-08',
  signal?: AbortSignal,
): Promise<GrilePilotV2Overview> {
  return generatedGet('grile_pilot_v2_api_grile_pilot_v2_get', {
    params: { month },
    signal,
  });
}

export async function runGrileCheck(month?: string): Promise<GrileRunEnqueue> {
  return generatedPost(
    'grile_run_api_grile_run_post',
    undefined,
    { params: month ? { month } : undefined },
  );
}

export async function getGrileRunStatus(
  month?: string,
  signal?: AbortSignal,
): Promise<{ run: GrileRun | null }> {
  return generatedGet('grile_run_status_api_grile_run_status_get', {
    params: month ? { month } : undefined,
    signal,
  });
}

export async function enqueueGrileStoreRefresh(
  month: string,
  siteCode: string,
  signal?: AbortSignal,
): Promise<GrileStoreRefreshEnqueue> {
  return generatedPost(
    'grile_store_refresh_api_grile_stores__site_code__refresh_post',
    undefined,
    {
      pathParams: { site_code: siteCode },
      params: { month },
      signal,
    },
  );
}

export async function getGrileStoreRefreshOperation(
  operationId: number,
  signal?: AbortSignal,
): Promise<GrileStoreRefreshOperation> {
  const data = await generatedGet(
    'grile_store_refresh_operation_api_grile_store_refreshes__operation_id__get',
    { pathParams: { operation_id: operationId }, signal },
  );
  return data.operation;
}

function abortableDelay(delayMs: number, signal?: AbortSignal): Promise<void> {
  if (signal?.aborted) return Promise.reject(new DOMException('Aborted', 'AbortError'));
  return new Promise((resolve, reject) => {
    const onAbort = () => {
      window.clearTimeout(timeout);
      reject(new DOMException('Aborted', 'AbortError'));
    };
    const timeout = window.setTimeout(() => {
      signal?.removeEventListener('abort', onAbort);
      resolve();
    }, delayMs);
    signal?.addEventListener('abort', onAbort, { once: true });
  });
}


export class GrileRefreshStatusUnknownError extends Error {
  readonly operationId: number;

  constructor(operationId: number, cause?: unknown) {
    super(
      `Starea verificării ${operationId} nu poate fi confirmată. `
      + 'Nu relansa verificarea până când operația nu este verificată în backend.',
      { cause },
    );
    this.name = 'GrileRefreshStatusUnknown';
    this.operationId = operationId;
  }
}

interface GrileRefreshPollingOptions {
  intervalMs?: number;
  maxAttempts?: number;
}

export async function refreshGrileStore(
  month: string,
  siteCode: string,
  signal?: AbortSignal,
  options: GrileRefreshPollingOptions = {},
): Promise<GrileStoreRefreshOperation> {
  const reservation = await enqueueGrileStoreRefresh(month, siteCode, signal);
  const intervalMs = options.intervalMs ?? 1_500;
  const maxAttempts = options.maxAttempts ?? 180;
  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    let operation: GrileStoreRefreshOperation;
    try {
      operation = await getGrileStoreRefreshOperation(reservation.operation_id, signal);
    } catch (error) {
      if (signal?.aborted) throw error;
      throw new GrileRefreshStatusUnknownError(reservation.operation_id, error);
    }
    if (operation.status === 'completed') return operation;
    if (operation.status === 'failed' || operation.status === 'cancelled') {
      const error = new Error(operation.error_message || 'Verificarea grilei a eșuat.');
      error.name = operation.error_code || 'GrileRefreshFailed';
      throw error;
    }
    if (operation.status === 'unknown') {
      throw new GrileRefreshStatusUnknownError(reservation.operation_id);
    }
    if (attempt < maxAttempts - 1) await abortableDelay(intervalMs, signal);
  }
  throw new GrileRefreshStatusUnknownError(reservation.operation_id);
}

// ── Inchidere luna ─────────────────────────────────────────────────────────────

export type GrileMonthlyOp = RetailMonthlyRunRequest['op'];

export interface GrileMonthlyResult {
  op: GrileMonthlyOp;
  month_label: string;
  status: 'success' | 'failed';
  output: string;
  exit_code: number | null;
  dry_run?: boolean | null;
  manifest?: GrileMonthlyManifest | null;
}

type GeneratedManifest = RequiredRuntime<RetailGrileMonthlyManifestResponse>;
export type GrileMonthlyManifest = Omit<GeneratedManifest, 'expected' | 'processed'> & {
  expected: { stores?: number; agents?: number };
  processed: { stores?: number; agents?: number };
};

export interface GrileMonthlyEnqueue {
  status: 'enqueued' | 'already_running' | 'already_completed';
  job_id: string | null;
  operation_id: number;
  op: GrileMonthlyOp;
  month: string;
  month_label: string;
  next_month_label: string | null;
  dry_run: boolean | null;
  operation: Record<string, unknown> | null;
}

export interface GrileMonthlyJob {
  job_id: string;
  status: 'queued' | 'in_progress' | 'complete' | 'not_found';
  result: GrileMonthlyResult | null;
  error: string | null;
}

export async function getGrileMonthlyPermissions(
  signal?: AbortSignal,
): Promise<{ can_run: boolean }> {
  return generatedGet('grile_monthly_permissions_api_grile_monthly_permissions_get', { signal });
}

export async function runGrileMonthly(
  body: RetailMonthlyRunRequest,
): Promise<GrileMonthlyEnqueue> {
  return generatedPost('grile_monthly_run_api_grile_monthly_run_post', body) as Promise<GrileMonthlyEnqueue>;
}

export async function getGrileMonthlyManifest(
  month: string,
  signal?: AbortSignal,
): Promise<GrileMonthlyManifest | null> {
  const data = await generatedGet(
    'grile_monthly_manifest_api_grile_monthly_manifests__month__get',
    { pathParams: { month }, signal },
  );
  return data.manifest as GrileMonthlyManifest | null;
}

export async function approveGrileMonthlyManifest(
  manifestId: number,
): Promise<GrileMonthlyManifest> {
  const data = await generatedPost(
    'grile_monthly_manifest_approve_api_grile_monthly_manifests__manifest_id__approve_post',
    undefined,
    { pathParams: { manifest_id: manifestId } },
  );
  if (!data.manifest) throw new Error('Manifestul aprobat lipsește din răspuns.');
  return data.manifest as GrileMonthlyManifest;
}

export async function getGrileMonthlyJob(
  jobId: string,
  signal?: AbortSignal,
): Promise<GrileMonthlyJob> {
  const data = await generatedGet(
    'grile_monthly_job_api_grile_monthly_job__job_id__get',
    { pathParams: { job_id: jobId }, signal },
  );
  return data as GrileMonthlyJob;
}

export async function downloadGrileMonthly(
  kind: 'final' | 'archive',
  month: string,
): Promise<void> {
  const { data } = await client.get<Blob>(
    `/api/grile/monthly/download/${kind}/${month}`,
    { responseType: 'blob' },
  );
  const monthLabel = formatMonthLabel(month, { month: 'long' });
  downloadBlob(
    data,
    kind === 'final' ? `Tabel Salarii - ${monthLabel}.xlsx` : `Arhiva Grile - ${monthLabel}.zip`,
  );
}
