// @vitest-environment jsdom

import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('../../components/common/DesktopLayout', () => ({
  PageHeader: () => null,
}));

vi.mock('../../components/common/SegmentedTabs', () => ({
  SegmentedTabs: () => null,
}));

vi.mock('./CurrentDashboard', () => ({
  CurrentDashboard: () => <div data-testid="current-dashboard">current</div>,
}));

vi.mock('./HistoryDashboard', () => ({
  HistoryDashboard: ({
    regionalGridSorts,
    onRegionalGridSortsChange,
    storeGridSorts,
    onStoreGridSortsChange,
  }: {
    regionalGridSorts: Array<{ key: string; direction: 'asc' | 'desc' }>;
    onRegionalGridSortsChange: (
      sorts: Array<{ key: string; direction: 'asc' | 'desc' }>,
    ) => void;
    storeGridSorts: Array<{ key: string; direction: 'asc' | 'desc' }>;
    onStoreGridSortsChange: (
      sorts: Array<{ key: string; direction: 'asc' | 'desc' }>,
    ) => void;
  }) => (
    <div data-testid="history-dashboard">
      <span data-testid="history-regional-grid-sort">
        {regionalGridSorts.map((sort) => `${sort.key}:${sort.direction}`).join('|')}
      </span>
      <span data-testid="history-store-grid-sort">
        {storeGridSorts.map((sort) => `${sort.key}:${sort.direction}`).join('|')}
      </span>
      <button
        type="button"
        onClick={() => onRegionalGridSortsChange([
          { key: 'regional', direction: 'asc' },
          { key: 'target', direction: 'desc' },
        ])}
      >
        set-regional-grid-sort
      </button>
      <button
        type="button"
        onClick={() => onStoreGridSortsChange([
          { key: 'locatie', direction: 'asc' },
          { key: 'target', direction: 'desc' },
        ])}
      >
        set-store-grid-sort
      </button>
    </div>
  ),
}));

vi.mock('./PerformanceDetailDrawer', () => ({
  PerformanceDetailDrawer: () => null,
}));

import { DashboardSurface } from './DashboardSurface';
import type { DashboardViewProps } from './dashboardTypes';

function model(activeSection: 'current' | 'history'): DashboardViewProps {
  return {
    activeSection,
    summary: {},
    loading: false,
    error: null,
    historyRegionalSort: { key: 'total_vanzari', direction: 'desc' },
    historyStoreSort: { key: 'total_vanzari', direction: 'desc' },
    performanceSelection: null,
    onClosePerformance: vi.fn(),
  } as unknown as DashboardViewProps;
}

describe('DashboardSurface V3 state', () => {
  it('keeps RM and Store DataGrid sort chains when History unmounts and remounts', () => {
    const { rerender } = render(<DashboardSurface {...model('history')} />);

    expect(screen.getByTestId('history-regional-grid-sort')).toHaveTextContent(
      'total_vanzari:desc',
    );
    expect(screen.getByTestId('history-store-grid-sort')).toHaveTextContent(
      'total_vanzari:desc',
    );

    fireEvent.click(screen.getByRole('button', { name: 'set-regional-grid-sort' }));
    fireEvent.click(screen.getByRole('button', { name: 'set-store-grid-sort' }));
    expect(screen.getByTestId('history-regional-grid-sort')).toHaveTextContent(
      'regional:asc|target:desc',
    );
    expect(screen.getByTestId('history-store-grid-sort')).toHaveTextContent(
      'locatie:asc|target:desc',
    );

    rerender(<DashboardSurface {...model('current')} />);
    expect(screen.getByTestId('current-dashboard')).toBeInTheDocument();

    rerender(<DashboardSurface {...model('history')} />);
    expect(screen.getByTestId('history-regional-grid-sort')).toHaveTextContent(
      'regional:asc|target:desc',
    );
    expect(screen.getByTestId('history-store-grid-sort')).toHaveTextContent(
      'locatie:asc|target:desc',
    );
  });
});
