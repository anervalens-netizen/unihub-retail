import { describe, expect, it, vi } from 'vitest';

import type { ImportJobStatus } from '../api/generated/runtime-types';
import { pollImportJob } from './importJobPolling';

const queued: ImportJobStatus = {
  job_id: 'sales-import:test',
  job_kind: 'sales',
  status: 'queued',
  result: null,
  promo_result: null,
  erp_result: null,
  error: null,
};

const complete: ImportJobStatus = {
  ...queued,
  status: 'complete',
  result: {
    import_month: '2026-07',
    rows_in_file: 10,
    rows_imported: 8,
    rows_filtered: 2,
    store_count: 1,
    agent_count: 1,
    snapshot_id: 200,
    filename: 'sales.xlsx',
    is_month_final: false,
    coverage_report: {
      incoming_store_count: null,
      company_count: null,
      active_store_count_before: null,
      prior_snapshot_store_count: null,
      active_store_coverage_pct: null,
      prior_snapshot_coverage_pct: null,
      missing_active_store_count: null,
      missing_prior_store_count: null,
      new_store_count: null,
      metadata_change_count: null,
      store_activity_writes: null,
    },
    generation_state: 'promoted',
    generation_token: null,
    manifest_sha256: null,
    manifest: null,
  },
};

const immediateSleep = async () => undefined;

describe('pollImportJob', () => {
  it('tolerates a transient polling failure and returns the completed job', async () => {
    const getStatus = vi.fn()
      .mockRejectedValueOnce(new TypeError('network interrupted'))
      .mockResolvedValueOnce(complete);

    const outcome = await pollImportJob(queued, {
      intervalMs: 0,
      maxAttempts: 5,
      maxConsecutiveErrors: 3,
      getStatus,
      sleep: immediateSleep,
    });

    expect(outcome).toEqual({ kind: 'complete', job: complete });
    expect(getStatus).toHaveBeenCalledTimes(2);
  });

  it('reports an unconfirmed status instead of a failed import after repeated connection errors', async () => {
    const getStatus = vi.fn().mockRejectedValue(new TypeError('offline'));

    const outcome = await pollImportJob(queued, {
      intervalMs: 0,
      maxAttempts: 10,
      maxConsecutiveErrors: 3,
      getStatus,
      sleep: immediateSleep,
    });

    expect(outcome).toEqual({ kind: 'unconfirmed', reason: 'connection', job: queued });
    expect(getStatus).toHaveBeenCalledTimes(3);
  });

  it('preserves an explicit worker failure as a completed job with an error', async () => {
    const failed = { ...complete, result: null, error: 'Fișier invalid' };

    const outcome = await pollImportJob(failed, {
      intervalMs: 0,
      maxAttempts: 1,
      maxConsecutiveErrors: 1,
      getStatus: vi.fn(),
      sleep: immediateSleep,
    });

    expect(outcome).toEqual({ kind: 'complete', job: failed });
  });
});
