// @vitest-environment jsdom

import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

const monthly = vi.hoisted(() => ({ model: { state: 'ready' } }));
vi.mock('./grile/useGrileMonthlyPanel', () => ({ useGrileMonthlyPanel: vi.fn(() => monthly.model) }));
vi.mock('./grile/GrileMonthlyPanelView', () => ({
  GrileMonthlyPanelView: ({ month, model }: { month: string; model: { state: string } }) => <div>{month}:{model.state}</div>,
}));

import { GrileMonthlyPanel } from './GrileMonthlyPanel';
import { GRILE_STATUS_FILTERS, matchesGrileStatusFilter } from './grile/grileOverviewFilters';

const store = {
  fill_status: 'NECOMPLETAT', target_status: 'DIFERENTA', sales_status: 'IN_URMA',
  provider_status: { state: 'error' },
};

describe('Grile monthly facade and status filters', () => {
  it('forwards the month and model through the facade', () => {
    render(<GrileMonthlyPanel month="2026-08" />);
    expect(screen.getByText('2026-08:ready')).toBeInTheDocument();
  });

  it('matches every declared status without conflating provider and business states', () => {
    expect(GRILE_STATUS_FILTERS).toHaveLength(9);
    expect(matchesGrileStatusFilter(store as never, 'all')).toBe(true);
    expect(matchesGrileStatusFilter({ ...store, target_status: 'OK', sales_status: 'OK' } as never, 'OK')).toBe(true);
    expect(matchesGrileStatusFilter(store as never, 'OK')).toBe(false);
    expect(matchesGrileStatusFilter(store as never, 'NECOMPLETAT')).toBe(true);
    expect(matchesGrileStatusFilter(store as never, 'IN_URMA')).toBe(true);
    expect(matchesGrileStatusFilter(store as never, 'DIF_TARGET')).toBe(true);
    expect(matchesGrileStatusFilter({ ...store, sales_status: 'DIFERENTA' } as never, 'DIF_SALES')).toBe(true);
    expect(matchesGrileStatusFilter(store as never, 'ERROR')).toBe(true);
    expect(matchesGrileStatusFilter({ ...store, provider_status: { state: 'stale' } } as never, 'STALE')).toBe(true);
    expect(matchesGrileStatusFilter({ ...store, provider_status: { state: 'unknown' } } as never, 'UNKNOWN')).toBe(true);
    expect(matchesGrileStatusFilter(store as never, 'bad' as never)).toBe(true);
  });
});
