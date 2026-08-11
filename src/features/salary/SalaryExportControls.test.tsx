// @vitest-environment jsdom

import { act, fireEvent, render, renderHook, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { ExportOperation } from '../../api/exports';

const api = vi.hoisted(() => ({
  createSalaryExportOperation: vi.fn(),
  downloadBlob: vi.fn(),
  downloadExportOperation: vi.fn(),
  getExportOperation: vi.fn(),
  isExportOperationNotFound: vi.fn(),
  pollExportOperation: vi.fn(),
  uncertainSalaryExportOperationId: vi.fn(),
}));

vi.mock('../../api/salarii', () => ({
  createSalaryExportOperation: api.createSalaryExportOperation,
  uncertainSalaryExportOperationId: api.uncertainSalaryExportOperationId,
}));

vi.mock('../../api/exports', () => ({
  downloadExportOperation: api.downloadExportOperation,
  getExportOperation: api.getExportOperation,
  isExportOperationNotFound: api.isExportOperationNotFound,
}));

vi.mock('../../lib/exportOperationPolling', () => ({
  pollExportOperation: api.pollExportOperation,
}));

vi.mock('../../lib/download', () => ({ downloadBlob: api.downloadBlob }));

import {
  SalaryExportButton,
  SalaryExportStatus,
  useSalaryExport,
} from './SalaryExportControls';

const operation = (overrides: Partial<ExportOperation> = {}): ExportOperation => ({
  id: 17,
  status: 'queued',
  can_download: false,
  filename: null,
  row_count: null,
  ...overrides,
} as ExportOperation);

describe('SalaryExportControls', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.sessionStorage.clear();
    api.isExportOperationNotFound.mockReturnValue(false);
    api.uncertainSalaryExportOperationId.mockReturnValue(null);
    api.downloadExportOperation.mockResolvedValue(new Blob(['xlsx']));
  });

  it('renders actionable button and resumable status', () => {
    const onExport = vi.fn();
    const onResume = vi.fn();
    const { rerender } = render(
      <>
        <SalaryExportButton busy={false} disabled={false} onExport={onExport} />
        <SalaryExportStatus busy={null} message="Export in lucru" operationId={17} onResume={onResume} />
      </>,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Excel' }));
    fireEvent.click(screen.getByRole('button', { name: 'Reia status' }));
    expect(onExport).toHaveBeenCalledOnce();
    expect(onResume).toHaveBeenCalledWith(17);

    rerender(
      <>
        <SalaryExportButton busy disabled onExport={onExport} />
        <SalaryExportStatus busy="agents" message="" operationId={null} onResume={onResume} />
      </>,
    );
    expect(screen.getByRole('button', { name: 'Generare...' })).toBeDisabled();
    expect(screen.queryByText('Export in lucru')).toBeNull();
  });

  it('creates, polls, downloads, verifies and clears a salary export', async () => {
    const initial = operation();
    const completed = operation({
      status: 'completed',
      can_download: true,
      filename: 'salarii.xlsx',
      row_count: 23,
    });
    api.createSalaryExportOperation.mockResolvedValue(initial);
    api.pollExportOperation.mockResolvedValue({ kind: 'terminal', operation: completed });

    const { result } = renderHook(() => useSalaryExport());
    await act(async () => {
      await result.current.start({ export_kind: 'agents' });
    });

    expect(api.createSalaryExportOperation).toHaveBeenCalledWith({ export_kind: 'agents' });
    expect(api.pollExportOperation).toHaveBeenCalledWith(
      initial,
      api.getExportOperation,
      expect.objectContaining({ intervalMs: 1_250, maxAttempts: 1_440 }),
    );
    expect(api.downloadExportOperation).toHaveBeenCalledWith(17, expect.any(AbortSignal));
    expect(api.downloadBlob).toHaveBeenCalledWith(expect.any(Blob), 'salarii.xlsx');
    expect(result.current.operationId).toBeNull();
    expect(result.current.message).toContain('23 randuri');
    expect(window.sessionStorage.getItem('unihub:salary-export-operation')).toBeNull();
  });

  it('recovers an uncertain reservation exactly once', async () => {
    const publishError = new Error('queue timeout');
    const initial = operation({ id: 42 });
    const completed = operation({
      id: 42,
      status: 'completed',
      can_download: true,
      filename: null,
      row_count: 0,
    });
    api.createSalaryExportOperation.mockRejectedValue(publishError);
    api.uncertainSalaryExportOperationId.mockReturnValue(42);
    api.getExportOperation.mockResolvedValue(initial);
    api.pollExportOperation.mockResolvedValue({ kind: 'terminal', operation: completed });

    const { result } = renderHook(() => useSalaryExport());
    await act(async () => {
      await result.current.start({ export_kind: 'monthly_trend' });
    });

    expect(api.uncertainSalaryExportOperationId).toHaveBeenCalledWith(publishError);
    expect(api.getExportOperation).toHaveBeenCalledWith(42, expect.any(AbortSignal));
    expect(api.downloadBlob).toHaveBeenCalledWith(expect.any(Blob), 'salarii.xlsx');
    expect(result.current.message).toContain('SHA-256');
  });

  it('resumes stored work and preserves the id when status is unconfirmed', async () => {
    window.sessionStorage.setItem('unihub:salary-export-operation', '17');
    const initial = operation();
    api.getExportOperation.mockResolvedValue(initial);
    api.pollExportOperation.mockResolvedValue({ kind: 'unconfirmed', operation: initial });

    const { result } = renderHook(() => useSalaryExport());

    await waitFor(() => expect(result.current.busy).toBeNull());
    expect(api.getExportOperation).toHaveBeenCalledWith(17, expect.any(AbortSignal));
    expect(result.current.operationId).toBe(17);
    expect(result.current.message).toContain('continua in worker');
    expect(window.sessionStorage.getItem('unihub:salary-export-operation')).toBe('17');
  });

  it('drops an inaccessible stored operation and keeps transient failures resumable', async () => {
    window.sessionStorage.setItem('unihub:salary-export-operation', '17');
    api.getExportOperation.mockRejectedValueOnce(new Error('not found'));
    api.isExportOperationNotFound.mockReturnValueOnce(true);

    const first = renderHook(() => useSalaryExport());
    await waitFor(() => expect(first.result.current.message).toContain('referinta a fost eliminata'));
    expect(first.result.current.operationId).toBeNull();
    first.unmount();

    window.sessionStorage.setItem('unihub:salary-export-operation', '18');
    api.getExportOperation.mockRejectedValueOnce(new Error('temporary'));
    api.isExportOperationNotFound.mockReturnValueOnce(false);
    const second = renderHook(() => useSalaryExport());
    await waitFor(() => expect(second.result.current.message).toContain('ID-ul a fost pastrat'));
    expect(second.result.current.operationId).toBe(18);
  });

  it('reports terminal failure and ignores concurrent starts', async () => {
    const initial = operation();
    api.createSalaryExportOperation.mockResolvedValue(initial);
    api.pollExportOperation.mockResolvedValue({
      kind: 'terminal',
      operation: operation({ status: 'failed' }),
    });

    const { result } = renderHook(() => useSalaryExport());
    await act(async () => {
      await result.current.start({ export_kind: 'store_summary' });
    });
    expect(result.current.message).toContain('nu a putut fi finalizat');
    expect(result.current.operationId).toBeNull();

    window.sessionStorage.setItem('unihub:salary-export-operation', '19');
    const stored = renderHook(() => useSalaryExport());
    await act(async () => {
      await stored.result.current.start({ export_kind: 'agents' });
    });
    expect(api.createSalaryExportOperation).toHaveBeenCalledTimes(1);
    stored.unmount();
  });
});
