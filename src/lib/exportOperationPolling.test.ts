import { describe, expect, it, vi } from 'vitest';

import type { ExportOperation } from '../api/exports';
import { pollExportOperation } from './exportOperationPolling';

const queued: ExportOperation = {
  id: 7,
  kind: 'daily_metrics',
  status: 'queued',
  job_id: 'export-complex:7',
  filename: null,
  artifact_size: null,
  artifact_sha256: null,
  peak_rss_bytes: null,
  build_seconds: null,
  cell_count: null,
  error_code: null,
  created_at: '2026-08-06T12:00:00Z',
  started_at: null,
  finished_at: null,
  expires_at: null,
  can_download: false,
};

describe('pollExportOperation', () => {
  it('polls a durable id until completed without resubmitting', async () => {
    const completed: ExportOperation = {
      ...queued,
      status: 'completed',
      filename: 'report.xlsx',
      artifact_size: 42,
      artifact_sha256: 'a'.repeat(64),
      peak_rss_bytes: 1024,
      build_seconds: 1.5,
      cell_count: 120,
      finished_at: '2026-08-06T12:01:00Z',
      expires_at: '2026-08-06T13:01:00Z',
      can_download: true,
    };
    const fetchStatus = vi.fn().mockResolvedValue(completed);

    const result = await pollExportOperation(queued, fetchStatus, {
      intervalMs: 0,
      maxAttempts: 3,
      maxConsecutiveErrors: 2,
      wait: async () => undefined,
    });

    expect(result).toEqual({ kind: 'terminal', operation: completed });
    expect(fetchStatus).toHaveBeenCalledExactlyOnceWith(7, undefined);
  });

  it('returns unconfirmed after bounded status errors', async () => {
    const fetchStatus = vi.fn().mockRejectedValue(new Error('offline'));
    const result = await pollExportOperation(queued, fetchStatus, {
      intervalMs: 0,
      maxAttempts: 10,
      maxConsecutiveErrors: 2,
      wait: async () => undefined,
    });

    expect(result).toEqual({ kind: 'unconfirmed', operation: queued });
    expect(fetchStatus).toHaveBeenCalledTimes(2);
  });

  it('does not poll an already terminal operation', async () => {
    const failed = { ...queued, status: 'failed' as const, error_code: 'worker_failed' };
    const fetchStatus = vi.fn();
    expect(
      await pollExportOperation(failed, fetchStatus, {
        intervalMs: 0,
        maxAttempts: 1,
        maxConsecutiveErrors: 1,
      }),
    ).toEqual({ kind: 'terminal', operation: failed });
    expect(fetchStatus).not.toHaveBeenCalled();
  });

  it('publishes each status transition and stops promptly on abort', async () => {
    const running = { ...queued, status: 'running' as const };
    const controller = new AbortController();
    const onUpdate = vi.fn();
    const fetchStatus = vi.fn().mockResolvedValue(running);
    const result = await pollExportOperation(queued, fetchStatus, {
      intervalMs: 1,
      maxAttempts: 5,
      maxConsecutiveErrors: 2,
      signal: controller.signal,
      onUpdate: (operation) => {
        onUpdate(operation);
        controller.abort();
      },
      wait: async () => undefined,
    });

    expect(onUpdate).toHaveBeenCalledExactlyOnceWith(running);
    expect(result).toEqual({ kind: 'aborted', operation: running });
    expect(fetchStatus).toHaveBeenCalledOnce();
  });
});
