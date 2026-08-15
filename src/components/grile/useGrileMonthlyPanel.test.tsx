// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from '../../api/client';
import type {
  GrileMonthlyEnqueue,
  GrileMonthlyJob,
  GrileMonthlyManifest,
  GrileMonthlyResult,
} from '../../api/grile';

const api = vi.hoisted(() => ({
  approveGrileMonthlyManifest: vi.fn(),
  downloadGrileMonthly: vi.fn(),
  getGrileMonthlyJob: vi.fn(),
  getGrileMonthlyManifest: vi.fn(),
  getGrileMonthlyPermissions: vi.fn(),
  runGrileMonthly: vi.fn(),
}));

vi.mock('../../api/grile', () => ({
  approveGrileMonthlyManifest: api.approveGrileMonthlyManifest,
  downloadGrileMonthly: api.downloadGrileMonthly,
  getGrileMonthlyJob: api.getGrileMonthlyJob,
  getGrileMonthlyManifest: api.getGrileMonthlyManifest,
  getGrileMonthlyPermissions: api.getGrileMonthlyPermissions,
  runGrileMonthly: api.runGrileMonthly,
}));

import {
  grileMonthLabel,
  nextGrileMonthLabel,
  useGrileMonthlyPanel,
} from './useGrileMonthlyPanel';

const MONTH = '2026-07';

function createWrapper() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
}

const manifest = (overrides: Partial<GrileMonthlyManifest> = {}): GrileMonthlyManifest => ({
  id: 5,
  month: MONTH,
  status: 'verified',
  expected: { stores: 12, agents: 34 },
  processed: { stores: 12, agents: 34 },
  ...overrides,
} as unknown as GrileMonthlyManifest);

const enqueue = (overrides: Partial<GrileMonthlyEnqueue> = {}): GrileMonthlyEnqueue => ({
  status: 'enqueued',
  job_id: 'job-1',
  operation_id: 9,
  op: 'finalize',
  month: MONTH,
  month_label: 'Iulie 2026',
  next_month_label: null,
  dry_run: true,
  operation: null,
  ...overrides,
});

const jobStatus = (overrides: Partial<GrileMonthlyJob> = {}): GrileMonthlyJob => ({
  job_id: 'job-1',
  status: 'in_progress',
  result: null,
  error: null,
  ...overrides,
});

const jobResult: GrileMonthlyResult = {
  op: 'finalize',
  month_label: 'Iulie 2026',
  status: 'success',
  output: 'finalizat',
  exit_code: 0,
  dry_run: true,
  manifest: null,
};

describe('useGrileMonthlyPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal('confirm', vi.fn(() => true));
    api.getGrileMonthlyPermissions.mockResolvedValue({ can_run: true });
    api.getGrileMonthlyManifest.mockResolvedValue(manifest());
    api.runGrileMonthly.mockResolvedValue(enqueue());
    api.approveGrileMonthlyManifest.mockResolvedValue(manifest({ status: 'approved' }));
    api.downloadGrileMonthly.mockResolvedValue(undefined);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('exposes month labels and loads permissions plus manifest for the month', async () => {
    expect(grileMonthLabel(MONTH)).toBe('Iulie 2026');
    expect(nextGrileMonthLabel(MONTH)).toBe('August 2026');
    expect(nextGrileMonthLabel('2026-12')).toBe('Ianuarie 2027');

    const { result } = renderHook(() => useGrileMonthlyPanel(MONTH), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.manifest).not.toBeNull());

    expect(api.getGrileMonthlyPermissions).toHaveBeenCalledWith(expect.any(AbortSignal));
    expect(api.getGrileMonthlyManifest).toHaveBeenCalledWith(MONTH, expect.any(AbortSignal));
    expect(result.current.permissions.data).toEqual({ can_run: true });
    expect(result.current.manifest?.status).toBe('verified');
    expect(result.current.approvedManifestId).toBeNull();
    expect(result.current.running).toBe(false);
    expect(result.current.error).toBeNull();
    expect(result.current.job).toBeNull();
    expect(result.current.result).toBeNull();

    expect(result.current.open).toBe(false);
    act(() => result.current.setOpen(true));
    expect(result.current.open).toBe(true);
  });

  it('does not request the manifest when the user cannot run monthly ops', async () => {
    api.getGrileMonthlyPermissions.mockResolvedValue({ can_run: false });
    const { result } = renderHook(() => useGrileMonthlyPanel(MONTH), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.permissions.data).toEqual({ can_run: false }));

    expect(api.getGrileMonthlyManifest).not.toHaveBeenCalled();
    expect(result.current.manifest).toBeNull();
  });

  it('starts a dry-run finalize job, follows it to completion and refreshes the manifest', async () => {
    api.runGrileMonthly.mockResolvedValue(enqueue({ op: 'finalize', dry_run: true }));
    api.getGrileMonthlyJob
      .mockResolvedValueOnce(jobStatus({ status: 'in_progress' }))
      .mockResolvedValueOnce(jobStatus({ status: 'complete', result: jobResult }));

    const { result } = renderHook(() => useGrileMonthlyPanel(MONTH), { wrapper: createWrapper() });
    await waitFor(() => expect(result.current.manifest).not.toBeNull());

    await act(async () => {
      await result.current.trigger('finalize', true);
    });

    expect(api.runGrileMonthly).toHaveBeenCalledWith({
      op: 'finalize',
      month: MONTH,
      dry_run: true,
      approved_manifest_id: undefined,
    });
    expect(result.current.job).toEqual({ jobId: 'job-1', op: 'finalize', dryRun: true });
    expect(result.current.running).toBe(true);

    // A second start attempt while the job is active must be ignored.
    await act(async () => {
      await result.current.trigger('finalize', true);
    });
    expect(api.runGrileMonthly).toHaveBeenCalledTimes(1);

    await act(async () => {
      await result.current.jobQuery.refetch();
    });
    await waitFor(() => expect(result.current.running).toBe(false));

    expect(api.getGrileMonthlyJob).toHaveBeenCalledWith('job-1', expect.any(AbortSignal));
    expect(result.current.result).toEqual(jobResult);
    // Job completion triggers a manifest refetch on top of the initial load.
    await waitFor(() => expect(api.getGrileMonthlyManifest).toHaveBeenCalledTimes(2));
  });

  it('live reset demands confirmation and sends the approved manifest id', async () => {
    api.getGrileMonthlyManifest.mockResolvedValue(manifest({ id: 7, status: 'approved' }));
    api.runGrileMonthly.mockResolvedValue(enqueue({ op: 'reset', dry_run: false }));
    api.getGrileMonthlyJob.mockResolvedValue(jobStatus({ status: 'not_found' }));

    const { result } = renderHook(() => useGrileMonthlyPanel(MONTH), { wrapper: createWrapper() });
    await waitFor(() => expect(result.current.approvedManifestId).toBe(7));

    await act(async () => {
      await result.current.trigger('reset', false);
    });

    expect(window.confirm).toHaveBeenCalledTimes(1);
    expect((window.confirm as ReturnType<typeof vi.fn>).mock.calls[0]![0])
      .toContain('Reset LIVE pentru Iulie 2026');
    expect((window.confirm as ReturnType<typeof vi.fn>).mock.calls[0]![0]).toContain('IREVOCABILA');
    expect(api.runGrileMonthly).toHaveBeenCalledWith({
      op: 'reset',
      month: MONTH,
      dry_run: false,
      approved_manifest_id: 7,
    });

    (window.confirm as ReturnType<typeof vi.fn>).mockReturnValue(false);
    await act(async () => {
      await result.current.trigger('reset', false);
    });
    expect(api.runGrileMonthly).toHaveBeenCalledTimes(1);
    expect(result.current.error).toBeNull();
  });

  it('maps enqueue outcomes and API errors to bounded messages', async () => {
    const { result } = renderHook(() => useGrileMonthlyPanel(MONTH), { wrapper: createWrapper() });
    await waitFor(() => expect(result.current.manifest).not.toBeNull());

    api.runGrileMonthly.mockResolvedValueOnce(enqueue({ status: 'already_completed', job_id: null }));
    await act(async () => {
      await result.current.trigger('finalize', true);
    });
    expect(result.current.error).toContain('deja marcat finalizat');
    expect(result.current.job).toBeNull();

    api.runGrileMonthly.mockResolvedValueOnce(enqueue({ status: 'already_running', job_id: null }));
    await act(async () => {
      await result.current.trigger('finalize', true);
    });
    expect(result.current.error).toBe('Exista deja o operatie lunara Grile in curs pentru luna selectata.');

    api.runGrileMonthly.mockResolvedValueOnce(enqueue({ job_id: null }));
    await act(async () => {
      await result.current.trigger('finalize', true);
    });
    expect(result.current.error).toBe('Nu am primit id-ul jobului pentru operatia lunara.');

    api.runGrileMonthly.mockRejectedValueOnce(new ApiError(403, 'permisiuni insuficiente', null));
    await act(async () => {
      await result.current.trigger('finalize', true);
    });
    expect(result.current.error).toBe('permisiuni insuficiente');

    api.runGrileMonthly.mockRejectedValueOnce(new Error('network'));
    await act(async () => {
      await result.current.trigger('finalize', true);
    });
    expect(result.current.error).toBe('Nu am putut porni operatia. Verifica permisiunile / serviciul grile.');
    expect(result.current.running).toBe(false);
  });

  it('surfaces worker failure reported by a completed job', async () => {
    api.getGrileMonthlyJob.mockResolvedValue(jobStatus({ status: 'complete', error: 'disk full' }));

    const { result } = renderHook(() => useGrileMonthlyPanel(MONTH), { wrapper: createWrapper() });
    await waitFor(() => expect(result.current.manifest).not.toBeNull());

    await act(async () => {
      await result.current.trigger('finalize', true);
    });

    await waitFor(() => expect(result.current.error).toBe('Operatia a esuat in worker: disk full'));
    expect(result.current.running).toBe(false);
    expect(result.current.result).toBeNull();
  });

  it('approves a verified manifest and refreshes it, with confirmation guards', async () => {
    api.getGrileMonthlyManifest
      .mockResolvedValueOnce(manifest())
      .mockResolvedValueOnce(manifest({ status: 'approved' }));

    const { result } = renderHook(() => useGrileMonthlyPanel(MONTH), { wrapper: createWrapper() });
    await waitFor(() => expect(result.current.manifest?.status).toBe('verified'));

    await act(async () => {
      await result.current.approveManifest();
    });

    expect(window.confirm).toHaveBeenCalledTimes(1);
    expect((window.confirm as ReturnType<typeof vi.fn>).mock.calls[0]![0])
      .toContain('Aprobi manifestul verificat pentru Iulie 2026: 12 magazine si 34 agenti');
    expect(api.approveGrileMonthlyManifest).toHaveBeenCalledWith(5);
    await waitFor(() => expect(result.current.manifest?.status).toBe('approved'));
    expect(result.current.approvedManifestId).toBe(5);
    expect(result.current.approving).toBe(false);

    // Approved manifests are no longer approvable.
    await act(async () => {
      await result.current.approveManifest();
    });
    expect(api.approveGrileMonthlyManifest).toHaveBeenCalledTimes(1);
  });

  it('skips approval without confirmation and reports approval failures', async () => {
    (window.confirm as ReturnType<typeof vi.fn>).mockReturnValue(false);
    const first = renderHook(() => useGrileMonthlyPanel(MONTH), { wrapper: createWrapper() });
    await waitFor(() => expect(first.result.current.manifest?.status).toBe('verified'));

    await act(async () => {
      await first.result.current.approveManifest();
    });
    expect(api.approveGrileMonthlyManifest).not.toHaveBeenCalled();
    first.unmount();

    (window.confirm as ReturnType<typeof vi.fn>).mockReturnValue(true);
    api.approveGrileMonthlyManifest.mockRejectedValueOnce(new ApiError(409, 'manifest blocat', null));
    const second = renderHook(() => useGrileMonthlyPanel(MONTH), { wrapper: createWrapper() });
    await waitFor(() => expect(second.result.current.manifest?.status).toBe('verified'));

    await act(async () => {
      await second.result.current.approveManifest();
    });
    expect(second.result.current.error).toBe('manifest blocat');
    expect(second.result.current.approving).toBe(false);
    second.unmount();
  });

  it('downloads final file and archive with dedicated error messages', async () => {
    let resolveDownload: (() => void) | null = null;
    api.downloadGrileMonthly.mockReturnValueOnce(new Promise<void>((resolve) => {
      resolveDownload = resolve;
    }));

    const { result } = renderHook(() => useGrileMonthlyPanel(MONTH), { wrapper: createWrapper() });
    await waitFor(() => expect(result.current.manifest).not.toBeNull());

    act(() => {
      void result.current.download('final');
    });
    await waitFor(() => expect(result.current.downloading).toBe('final'));
    expect(api.downloadGrileMonthly).toHaveBeenCalledWith('final', MONTH);

    await act(async () => {
      resolveDownload?.();
      await Promise.resolve();
    });
    await waitFor(() => expect(result.current.downloading).toBeNull());
    expect(result.current.error).toBeNull();

    api.downloadGrileMonthly.mockRejectedValueOnce(new Error('missing'));
    await act(async () => {
      await result.current.download('final');
    });
    expect(result.current.error).toBe('Fisierul de salarii nu exista inca. Ruleaza intai „Finalizeaza salarii".');

    api.downloadGrileMonthly.mockRejectedValueOnce(new Error('missing'));
    await act(async () => {
      await result.current.download('archive');
    });
    expect(api.downloadGrileMonthly).toHaveBeenCalledWith('archive', MONTH);
    expect(result.current.error).toBe('Arhiva nu exista inca. Ruleaza intai „Exporta arhiva".');
    expect(result.current.downloading).toBeNull();
  });

  it('refuses to start operations for an empty month', async () => {
    const { result } = renderHook(() => useGrileMonthlyPanel(''), { wrapper: createWrapper() });

    await act(async () => {
      await result.current.trigger('finalize', true);
    });

    expect(api.runGrileMonthly).not.toHaveBeenCalled();
    expect(api.getGrileMonthlyManifest).not.toHaveBeenCalled();
    expect(result.current.error).toBeNull();
  });
});
