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
  }: {
    regionalGridSorts: Array<{ key: string; direction: 'asc' | 'desc' }>;
    onRegionalGridSortsChange: (
      sorts: Array<{ key: string; direction: 'asc' | 'desc' }>,
    ) => void;
  }) => (
    <div data-testid="history-dashboard">
      <span data-testid="history-grid-sort">
        {regionalGridSorts.map((sort) => `${sort.key}:${sort.direction}`).join('|')}
      </span>
      <button
        type="button"
        onClick={() => onRegionalGridSortsChange([
          { key: 'regional', direction: 'asc' },
          { key: 'target', direction: 'desc' },
        ])}
      >
        set-grid-sort
      </button>
    </div>
  ),
}));

vi.mock('./PerformanceDetailDrawer', () => ({
  PerformanceDetailDrawer: () => null,
}));

import { DashboardSurface } from './DashboardSurface';

function model(activeSection: 'current' | 'history') {
  return {
    activeSection,
    summary: {},
    loading: false,
    error: null,
    historyRegionalSort: { key: 'total_vanzari', direction: 'desc' },
    performanceSelection: null,
    onClosePerformance: vi.fn(),
  };
}

describe('DashboardSurface V3 state', () => {
  it('keeps the full RM DataGrid sort chain when History unmounts and remounts', () => {
    const { rerender } = render(<DashboardSurface {...model('history') as never} />);

    expect(screen.getByTestId('history-grid-sort')).toHaveTextContent(
      'total_vanzari:desc',
    );

    fireEvent.click(screen.getByRole('button', { name: 'set-grid-sort' }));
    expect(screen.getByTestId('history-grid-sort')).toHaveTextContent(
      'regional:asc|target:desc',
    );

    rerender(<DashboardSurface {...model('current') as never} />);
    expect(screen.getByTestId('current-dashboard')).toBeInTheDocument();

    rerender(<DashboardSurface {...model('history') as never} />);
    expect(screen.getByTestId('history-grid-sort')).toHaveTextContent(
      'regional:asc|target:desc',
    );
  });
});
