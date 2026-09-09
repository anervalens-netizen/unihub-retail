// @vitest-environment jsdom

import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const api = vi.hoisted(() => ({
  performance: vi.fn(),
}));

vi.mock('../../api/dashboard', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../api/dashboard')>()),
  getPerformanceDetail: api.performance,
}));

import type { PerformanceSelection } from './PerformanceDetailDrawer';
import {
  buildHistoryPerformanceOpen,
} from './useDashboardController';
import {
  useDashboardPerformanceDetail,
} from './useDashboardPerformanceDetail';

describe('History performance selection', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.performance.mockResolvedValue({ title: 'Promenada' });
  });

  it('binds one exact history month and closed-store scope without mutating the row selection', () => {
    const openPerformance = vi.fn();
    const selection: PerformanceSelection = {
      level: 'store',
      key: 'S-NORD',
    };
    const openHistoryPerformance = buildHistoryPerformanceOpen(
      ['2026-04'],
      true,
      openPerformance,
    );

    expect(openHistoryPerformance).toBeTypeOf('function');
    openHistoryPerformance?.(selection);

    expect(selection).toEqual({ level: 'store', key: 'S-NORD' });
    expect(openPerformance).toHaveBeenCalledWith({
      level: 'store',
      key: 'S-NORD',
      month: '2026-04',
      includeClosedStores: true,
    });
  });

  it('does not invent one detail period for an aggregated multi-month history view', () => {
    expect(buildHistoryPerformanceOpen(
      ['2026-03', '2026-04'],
      false,
      vi.fn(),
    )).toBeUndefined();
    expect(buildHistoryPerformanceOpen([], false, vi.fn())).toBeUndefined();
  });

  it('queries the selected history month while preserving current-month defaults', async () => {
    const historyHook = renderHook(() => useDashboardPerformanceDetail({
      currentMonth: '2026-05',
      firma: 'Mobiup',
    }));

    act(() => historyHook.result.current.setPerformanceSelection({
      level: 'store',
      key: 'S-NORD',
      month: '2026-04',
      includeClosedStores: true,
    }));

    await waitFor(() => expect(api.performance).toHaveBeenLastCalledWith({
      month: '2026-04',
      level: 'store',
      key: 'S-NORD',
      firma: 'Mobiup',
      site_code: undefined,
      current_scope: true,
      include_closed_stores: true,
    }));

    historyHook.unmount();
    api.performance.mockClear();

    const currentHook = renderHook(() => useDashboardPerformanceDetail({
      currentMonth: '2026-05',
      firma: 'Mobiup',
    }));

    act(() => currentHook.result.current.setPerformanceSelection({
      level: 'store',
      key: 'S-NORD',
    }));

    await waitFor(() => expect(api.performance).toHaveBeenLastCalledWith({
      month: '2026-05',
      level: 'store',
      key: 'S-NORD',
      firma: 'Mobiup',
      site_code: undefined,
      current_scope: true,
      include_closed_stores: false,
    }));
  });
});
