import type { ImportJobStatus } from '../api/types';

export type ImportJobPollOutcome =
  | { kind: 'complete'; job: ImportJobStatus }
  | { kind: 'unconfirmed'; reason: 'connection' | 'not_found' | 'timeout'; job: ImportJobStatus };

interface PollImportJobOptions {
  intervalMs: number;
  maxAttempts: number;
  maxConsecutiveErrors: number;
  getStatus: (jobId: string) => Promise<ImportJobStatus>;
  onConnectionIssue?: (consecutiveErrors: number) => void;
  onConnectionRestored?: () => void;
  sleep?: (milliseconds: number) => Promise<void>;
}

const defaultSleep = (milliseconds: number) =>
  new Promise<void>((resolve) => window.setTimeout(resolve, milliseconds));

export async function pollImportJob(
  initialJob: ImportJobStatus,
  options: PollImportJobOptions,
): Promise<ImportJobPollOutcome> {
  let job = initialJob;
  let consecutiveErrors = 0;
  const sleep = options.sleep ?? defaultSleep;

  for (let attempt = 0; attempt < options.maxAttempts; attempt += 1) {
    if (job.status === 'complete') return { kind: 'complete', job };
    if (job.status === 'not_found') return { kind: 'unconfirmed', reason: 'not_found', job };

    await sleep(options.intervalMs);
    try {
      job = await options.getStatus(job.job_id);
      if (consecutiveErrors > 0) options.onConnectionRestored?.();
      consecutiveErrors = 0;
    } catch {
      consecutiveErrors += 1;
      options.onConnectionIssue?.(consecutiveErrors);
      if (consecutiveErrors >= options.maxConsecutiveErrors) {
        return { kind: 'unconfirmed', reason: 'connection', job };
      }
    }
  }

  return { kind: 'unconfirmed', reason: 'timeout', job };
}
