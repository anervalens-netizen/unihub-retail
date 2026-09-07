// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from 'vitest';

const { generatedGet, generatedPost, clientGet, downloadBlob } = vi.hoisted(() => ({
  generatedGet: vi.fn(),
  generatedPost: vi.fn(),
  clientGet: vi.fn(),
  downloadBlob: vi.fn(),
}));

vi.mock('./generated/client', () => ({ generatedGet, generatedPost }));
vi.mock('./client', () => ({ client: { get: clientGet } }));
vi.mock('../lib/download', () => ({ downloadBlob }));

import {
  approveGrileMonthlyManifest,
  downloadGrileMonthly,
  getGrileOverview,
  getGrileMonthlyJob,
  getGrileMonthlyManifest,
  getGrileMonthlyPermissions,
  getGrileRunStatus,
  runGrileCheck,
  runGrileMonthly,
  refreshGrileStore,
} from './grile';

const completedOperation = {
  id: 41,
  run_month: '2026-08',
  site_code: 'S001',
  status: 'completed' as const,
  projection_applied: true,
  error_code: null,
  error_message: null,
  created_at: '2026-08-07T08:00:00Z',
  started_at: '2026-08-07T08:00:01Z',
  heartbeat_at: '2026-08-07T08:00:02Z',
  finished_at: '2026-08-07T08:00:03Z',
};

describe('Grile generated API boundary', () => {
  beforeEach(() => {
    generatedGet.mockReset();
    generatedPost.mockReset();
    clientGet.mockReset();
    downloadBlob.mockReset();
  });

  it('uses the generated overview operation', async () => {
    generatedGet.mockResolvedValue({
      month: '2026-08',
      total_sheets: 0,
      run: null,
      summary: {
        business_ok: 0,
        business_problems: 0,
        business_unknown: 0,
        provider_fresh: 0,
        provider_errors: 0,
        provider_stale: 0,
        provider_unknown: 0,
        legacy_completion_windows: 0,
      },
      managers: [],
    });

    await getGrileOverview('2026-08');

    expect(generatedGet).toHaveBeenCalledWith(
      'grile_overview_api_grile_overview_get',
      { params: { month: '2026-08' }, signal: undefined },
    );
  });

  it('does not report refresh success until the persisted operation is terminal', async () => {
    generatedPost.mockResolvedValue({
      status: 'enqueued',
      month: '2026-08',
      operation_id: 41,
      job_id: 'grile-refresh:41',
    });
    generatedGet.mockResolvedValue({ operation: completedOperation });

    await expect(
      refreshGrileStore('2026-08', 'S001', undefined, { maxAttempts: 1 }),
    ).resolves.toEqual(completedOperation);

    expect(generatedPost).toHaveBeenCalledWith(
      'grile_store_refresh_api_grile_stores__site_code__refresh_post',
      undefined,
      {
        pathParams: { site_code: 'S001' },
        params: { month: '2026-08' },
        signal: undefined,
      },
    );
    expect(generatedGet).toHaveBeenCalledWith(
      'grile_store_refresh_operation_api_grile_store_refreshes__operation_id__get',
      { pathParams: { operation_id: 41 }, signal: undefined },
    );
  });

  it('polls a running refresh until the persisted operation completes', async () => {
    generatedPost.mockResolvedValue({ operation_id: 41 });
    generatedGet
      .mockResolvedValueOnce({ operation: { ...completedOperation, status: 'running' } })
      .mockResolvedValueOnce({ operation: completedOperation });

    await expect(
      refreshGrileStore('2026-08', 'S001', undefined, { intervalMs: 0, maxAttempts: 2 }),
    ).resolves.toEqual(completedOperation);
    expect(generatedGet).toHaveBeenCalledTimes(2);
  });

  it('stops polling when cancelled and when the bounded attempt budget expires', async () => {
    const controller = new AbortController();
    controller.abort();
    generatedPost.mockResolvedValue({ operation_id: 41 });
    generatedGet.mockResolvedValue({ operation: { ...completedOperation, status: 'running' } });

    await expect(
      refreshGrileStore('2026-08', 'S001', controller.signal, { intervalMs: 0, maxAttempts: 3 }),
    ).rejects.toMatchObject({ name: 'AbortError' });
    expect(generatedGet).toHaveBeenCalledTimes(1);

    generatedGet.mockClear();
    generatedPost.mockResolvedValue({ operation_id: 41 });
    generatedGet.mockResolvedValue({ operation: { ...completedOperation, status: 'running' } });
    await expect(
      refreshGrileStore('2026-08', 'S001', undefined, { intervalMs: 0, maxAttempts: 2 }),
    ).rejects.toMatchObject({ name: 'GrileRefreshStatusUnknown', operationId: 41 });
    expect(generatedGet).toHaveBeenCalledTimes(2);
  });

  it('surfaces the finite terminal provider failure', async () => {
    generatedPost.mockResolvedValue({
      status: 'enqueued',
      month: '2026-08',
      operation_id: 41,
      job_id: 'grile-refresh:41',
    });
    generatedGet.mockResolvedValue({
      operation: {
        ...completedOperation,
        status: 'failed',
        projection_applied: false,
        error_code: 'provider_timeout',
        error_message: 'Google read exceeded the configured deadline',
      },
    });

    await expect(
      refreshGrileStore('2026-08', 'S001', undefined, { maxAttempts: 1 }),
    ).rejects.toMatchObject({
      name: 'provider_timeout',
      message: 'Google read exceeded the configured deadline',
    });
  });

  it('maps an unavailable persisted status to an explicit no-blind-retry error', async () => {
    generatedPost.mockResolvedValue({
      status: 'enqueued',
      month: '2026-08',
      operation_id: 41,
      job_id: 'grile-refresh:41',
    });
    generatedGet.mockRejectedValue(new Error('backend unavailable'));

    await expect(
      refreshGrileStore('2026-08', 'S001', undefined, { maxAttempts: 1 }),
    ).rejects.toMatchObject({
      name: 'GrileRefreshStatusUnknown',
      operationId: 41,
      message: expect.stringContaining('Nu relansa verificarea'),
    });
  });

  it('does not turn an explicit unknown operation into success or automatic retry', async () => {
    generatedPost.mockResolvedValue({
      status: 'enqueued',
      month: '2026-08',
      operation_id: 41,
      job_id: 'grile-refresh:41',
    });
    generatedGet.mockResolvedValue({
      operation: {
        ...completedOperation,
        status: 'unknown',
        projection_applied: null,
        error_code: 'operation_state_unknown',
        error_message: 'Starea persistată nu este recunoscută.',
      },
    });

    await expect(
      refreshGrileStore('2026-08', 'S001', undefined, { maxAttempts: 3 }),
    ).rejects.toMatchObject({
      name: 'GrileRefreshStatusUnknown',
      operationId: 41,
    });
    expect(generatedGet).toHaveBeenCalledTimes(1);
  });

  it('keeps the retained V1 run and monthly transport boundaries generated', async () => {
    generatedGet
      .mockResolvedValueOnce({ run: null })
      .mockResolvedValueOnce({ can_run: true })
      .mockResolvedValueOnce({ job_id: 'job-1', status: 'complete', result: null, error: null });
    generatedPost
      .mockResolvedValueOnce({ status: 'enqueued', operation_id: 7 })
      .mockResolvedValueOnce({ status: 'enqueued', operation_id: 8 });

    await runGrileCheck('2026-09');
    await expect(getGrileRunStatus('2026-09', undefined)).resolves.toEqual({ run: null });
    await expect(getGrileMonthlyPermissions()).resolves.toEqual({ can_run: true });
    await runGrileMonthly({ op: 'reset', month: '2026-09', dry_run: true });
    await expect(getGrileMonthlyJob('job-1')).resolves.toMatchObject({ status: 'complete' });

    expect(generatedPost).toHaveBeenNthCalledWith(
      1,
      'grile_run_api_grile_run_post',
      undefined,
      { params: { month: '2026-09' } },
    );
    expect(generatedPost).toHaveBeenNthCalledWith(
      2,
      'grile_monthly_run_api_grile_monthly_run_post',
      { op: 'reset', month: '2026-09', dry_run: true },
    );

    generatedPost.mockRejectedValueOnce(new Error('queue unavailable'));
    await expect(runGrileMonthly({ op: 'finalize', month: '2026-09', dry_run: false }))
      .rejects.toThrow('queue unavailable');
    generatedGet.mockResolvedValueOnce({
      job_id: 'job-2', status: 'not_found', result: null, error: 'job missing',
    });
    await expect(getGrileMonthlyJob('job-2')).resolves.toMatchObject({
      status: 'not_found', error: 'job missing',
    });
  });

  it('preserves missing and approved monthly manifest states', async () => {
    generatedGet.mockResolvedValueOnce({ manifest: null });
    await expect(getGrileMonthlyManifest('2026-09')).resolves.toBeNull();

    const manifest = { id: 15, month: '2026-09', status: 'approved' };
    generatedGet.mockResolvedValueOnce({ manifest });
    await expect(getGrileMonthlyManifest('2026-09')).resolves.toEqual(manifest);
    generatedPost.mockResolvedValueOnce({ manifest });
    await expect(approveGrileMonthlyManifest(15)).resolves.toEqual(manifest);
    generatedPost.mockResolvedValueOnce({ manifest: null });
    await expect(approveGrileMonthlyManifest(15)).rejects.toThrow('Manifestul aprobat lipsește');
  });

  it('downloads final and archive artifacts with their stable month-specific names', async () => {
    const salaryFile = new Blob(['xlsx']);
    const archiveFile = new Blob(['zip']);
    clientGet.mockResolvedValueOnce({ data: salaryFile }).mockResolvedValueOnce({ data: archiveFile });

    await downloadGrileMonthly('final', '2026-09');
    await downloadGrileMonthly('archive', '2026-09');

    expect(clientGet).toHaveBeenNthCalledWith(1, '/api/grile/monthly/download/final/2026-09', {
      responseType: 'blob',
    });
    expect(clientGet).toHaveBeenNthCalledWith(2, '/api/grile/monthly/download/archive/2026-09', {
      responseType: 'blob',
    });
    expect(downloadBlob).toHaveBeenNthCalledWith(1, salaryFile, 'Tabel Salarii - Septembrie 2026.xlsx');
    expect(downloadBlob).toHaveBeenNthCalledWith(2, archiveFile, 'Arhiva Grile - Septembrie 2026.zip');
  });
});
