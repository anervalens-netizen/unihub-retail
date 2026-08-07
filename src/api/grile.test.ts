import { beforeEach, describe, expect, it, vi } from 'vitest';

const { generatedGet, generatedPost } = vi.hoisted(() => ({
  generatedGet: vi.fn(),
  generatedPost: vi.fn(),
}));

vi.mock('./generated/client', () => ({ generatedGet, generatedPost }));

import {
  getGrileOverview,
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
});