import type { ExportOperation } from '../api/exports';

export type ExportPollOutcome =
  | { kind: 'terminal'; operation: ExportOperation }
  | { kind: 'unconfirmed'; operation: ExportOperation }
  | { kind: 'aborted'; operation: ExportOperation };

export type ExportPollOptions = {
  intervalMs: number;
  maxAttempts: number;
  maxConsecutiveErrors: number;
  signal?: AbortSignal;
  onUpdate?: (operation: ExportOperation) => void;
  wait?: (milliseconds: number, signal?: AbortSignal) => Promise<void>;
};

const terminal = (status: ExportOperation['status']) =>
  status === 'completed' ||
  status === 'failed' ||
  status === 'cancelled' ||
  status === 'expired';

export async function pollExportOperation(
  initial: ExportOperation,
  fetchStatus: (operationId: number, signal?: AbortSignal) => Promise<ExportOperation>,
  options: ExportPollOptions,
): Promise<ExportPollOutcome> {
  if (terminal(initial.status)) return { kind: 'terminal', operation: initial };
  const wait =
    options.wait ??
    ((milliseconds, signal) =>
      new Promise<void>((resolve) => {
        if (signal?.aborted) {
          resolve();
          return;
        }
        const timeout = setTimeout(resolve, milliseconds);
        signal?.addEventListener(
          'abort',
          () => {
            clearTimeout(timeout);
            resolve();
          },
          { once: true },
        );
      }));
  let current = initial;
  let consecutiveErrors = 0;
  for (let attempt = 0; attempt < options.maxAttempts; attempt += 1) {
    if (options.signal?.aborted) return { kind: 'aborted', operation: current };
    await wait(options.intervalMs, options.signal);
    if (options.signal?.aborted) return { kind: 'aborted', operation: current };
    try {
      current = await fetchStatus(initial.id, options.signal);
      consecutiveErrors = 0;
    } catch {
      if (options.signal?.aborted) return { kind: 'aborted', operation: current };
      consecutiveErrors += 1;
      if (consecutiveErrors >= options.maxConsecutiveErrors) {
        return { kind: 'unconfirmed', operation: current };
      }
      continue;
    }
    options.onUpdate?.(current);
    if (terminal(current.status)) return { kind: 'terminal', operation: current };
  }
  return { kind: 'unconfirmed', operation: current };
}
