// @vitest-environment jsdom

import {
  act,
  fireEvent,
  render,
  renderHook,
  screen,
  waitFor,
} from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { StoreStat } from '../../api/generated/runtime-types';

const api = vi.hoisted(() => ({
  performance: vi.fn(),
}));

vi.mock('../../api/dashboard', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../api/dashboard')>()),
  getPerformanceDetail: api.performance,
}));

import {
  HIST_STORE_COLUMNS,
  storeBreakdownColumns,
} from './dashboardColumns';
import type { PerformanceSelection } from './PerformanceDetailDrawer';
import {
  buildHistoryPerformanceOpen,
} from './useDashboardController';
import {
  useDashboardPerformanceDetail,
} from './useDashboardPerformanceDetail';

const historyStore = {
  site_code: 'S-NORD',
  firma: 'Mobiup',
  locatie: 'Promenada',
} as StoreStat;

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

  it('renders a Store detail button for one month and plain text for an aggregate', () => {
    const openPerformance = vi.fn();
    const singleMonthOpen = buildHistoryPerformanceOpen(
      ['2026-04'],
      false,
      openPerformance,
    );
    const singleMonthLocation = storeBreakdownColumns(
      HIST_STORE_COLUMNS,
      singleMonthOpen,
    ).find((column) => column.key === 'locatie');
    const view = render(<>{singleMonthLocation?.render(historyStore)}</>);

    fireEvent.click(screen.getByRole('button', { name: /Promenada/ }));
    expect(openPerformance).toHaveBeenCalledWith({
      level: 'store',
      key: 'S-NORD',
      month: '2026-04',
      includeClosedStores: false,
    });

    const aggregateLocation = storeBreakdownColumns(
      HIST_STORE_COLUMNS,
      buildHistoryPerformanceOpen(
        ['2026-03', '2026-04'],
        false,
        openPerformance,
      ),
    ).find((column) => column.key === 'locatie');
    view.rerender(<>{aggregateLocation?.render(historyStore)}</>);

    expect(screen.queryByRole('button', { name: /Promenada/ })).not.toBeInTheDocument();
    expect(screen.getByText('Promenada')).toBeInTheDocument();
  });

  it('does not invent one detail period for an empty history view', () => {
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
