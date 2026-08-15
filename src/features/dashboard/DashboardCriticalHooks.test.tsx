// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const api = vi.hoisted(() => ({ current: vi.fn(), history: vi.fn(), details: vi.fn(), year: vi.fn(), performance: vi.fn() }));
vi.mock('../../api/dashboard', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../api/dashboard')>()),
  getDashboardAll: api.current,
  getDashboardHistory: api.history,
  getDashboardHistoryDetailsBatch: api.details,
  getDashboardHistoryYear: api.year,
  getPerformanceDetail: api.performance,
}));

import { defaultAppFilters } from '../../lib/filterValues';
import { aggregateDashboardDetails, formatMonthSelectionLabel, getDefaultHistoryMonth, sortMonthsAsc } from './presenters';
import { shouldPrefetchDashboardHistory, useDashboardData } from './useDashboardData';
import { useDashboardHistorySelection } from './useDashboardHistorySelection';
import { useDashboardPerformanceDetail } from './useDashboardPerformanceDetail';

function wrapper() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

const summary = {
  month: '2026-07', total_sales: 1000, total_target: 1200, target_progress_pct: 83.3, forecast_sales: 1100, forecast_target_progress_pct: 91.7,
  total_quantity: 10, total_receipts: 5, proc_bon2acc: 40, prc_focus_acc_qty: 20, total_stores: 1, total_agents: 1,
  working_days: 20, daily_average: 50, medie_produs: 100, is_month_final: true, last_sale_date: '2026-07-31', imported_day_of_month: 31, days_in_month: 31, cartele_qty: 1,
};
const regional = { regional: 'Nord', total_vanzari: 1000, qty_total: 10, nr_bonuri: 5, nr_agenti: 1, zile_active: 20, target: 1200, proc_realizare_target: 83, forecast_target_pct: 90, promo_qty: 1, promo_discount_value: 2, incentive_qty: 3, medie_zilnica: 50, medie_produs: 100, proc_bon2acc: 40, prc_focus_acc_qty: 20, return_receipt_count: 1 };
const asm = { ...regional, asm: 'ASM' };
const store = { ...regional, import_month: '2026-07', site_code: 'S1', locatie: 'Alfa', firma: 'Mobiup', asm: 'ASM', total_vanzari: 1000, qty_total: 10, nr_bonuri: 5, nr_agenti: 1, zile_active: 20 };
const agent = { import_month: '2026-07', agent: 'Ana', site_code: 'S1', locatie: 'Alfa', firma: 'Mobiup', regional: 'Nord', asm: 'ASM', acc_qty_realizat: 10, nr_bonuri: 5, nr_bon2acc: 2, proc_bon2acc: 40, total_vanzari: 1000, zile_lucrate: 20, medie_zilnica: 50, medie_produs: 100, acc_focus_qty: 2, prc_focus_acc_qty: 20, target: 1200, proc_realizare_target: 83, promo_qty: 1, promo_discount_value: 2, incentive_qty: 3, return_receipt_count: 1 };
const point = { month: '2026-07', total_sales: 1000, total_target: 1200, target_progress_pct: 83, total_quantity: 10, total_receipts: 5, proc_bon2acc: 40, prc_focus_acc_qty: 20, total_stores: 1, total_agents: 1, working_days: 20, daily_average: 50, medie_produs: 100 };
const comparisonPoint = { label: 'Curent', month: '2026-07', day_range: '1-31', total_sales: 1000, total_quantity: 10, total_receipts: 5, cartele_qty: 1, working_days: 20, daily_average: 50, avg_receipt_value: 200, medie_produs: 100, proc_bon2acc: 40, prc_focus_acc_qty: 20 };

function response(overrides: Record<string, unknown> = {}) {
  return {
    summary,
    receipt_bucket_mix: [{ bucket: '1', receipt_count: 5, share_pct: 100 }], focus_subcategory_mix: [{ category: 'Focus', sales_total: 200, quantity_total: 2, share_pct: 20 }],
    daily: [{ sale_date: '2026-07-01', total_sales: 100, total_quantity: 1, receipt_count: 1 }], daily_last_year: [], category_mix: [{ category: 'Acc', sales_total: 1000, quantity_total: 10, share_pct: 100 }], brand_mix: [{ brand: 'Brand', sales_total: 1000, quantity_total: 10, share_pct: 100 }],
    period_comparison: { current: comparisonPoint, previous: { ...comparisonPoint, label: 'Anterior' }, year_over_year: { ...comparisonPoint, label: 'An anterior' } },
    regionals: [regional], asms: [asm], stores: [store], agents: [agent],
    ...overrides,
  };
}

const hookProps = { currentMonth: '2026-08', filters: defaultAppFilters(), historyMonth: '2026-07', selectedHistoryMonths: ['2026-06', '2026-07'], includeClosedStores: false, activeSection: 'history' as const, historyYearFilter: 2026, aggregateDetails: aggregateDashboardDetails };

describe('dashboard data, selection and performance hooks', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.current.mockResolvedValue(response()); api.history.mockResolvedValue({ history: [point] }); api.details.mockResolvedValue([response(), response({ summary: { ...summary, month: '2026-06', total_sales: 0, total_target: 0, total_quantity: 0, total_receipts: 0, working_days: 0, forecast_sales: null, last_sale_date: null, days_in_month: null }, period_comparison: null, regionals: [{ ...regional, total_vanzari: 0, qty_total: 0, nr_bonuri: 0, zile_active: 0, target: 0 }], asms: [{ ...asm, total_vanzari: 0, qty_total: 0, nr_bonuri: 0, zile_active: 0, target: 0 }], stores: [{ ...store, total_vanzari: 0, qty_total: null, nr_bonuri: 0, zile_active: 0, target: 0 }], agents: [{ ...agent, total_vanzari: 0, acc_qty_realizat: 0, nr_bonuri: 0, nr_bon2acc: 0, zile_lucrate: 0, target: null }] })]);
    api.year.mockResolvedValue({ points: [{ year: 2026, total_sales: 1000 }] }); api.performance.mockResolvedValue({ title: 'Nord', summary: {}, monthly: [], stores: [], agents: [] });
  });

  it('honors connection constraints for speculative history prefetch', () => {
    const original = navigator;
    vi.stubGlobal('navigator', undefined); expect(shouldPrefetchDashboardHistory()).toBe(false);
    vi.stubGlobal('navigator', { connection: { saveData: true } }); expect(shouldPrefetchDashboardHistory()).toBe(false);
    vi.stubGlobal('navigator', { connection: { effectiveType: '2g' } }); expect(shouldPrefetchDashboardHistory()).toBe(false);
    vi.stubGlobal('navigator', { connection: { effectiveType: 'slow-2g' } }); expect(shouldPrefetchDashboardHistory()).toBe(false);
    vi.stubGlobal('navigator', { connection: { effectiveType: '4g' } }); expect(shouldPrefetchDashboardHistory()).toBe(true);
    vi.stubGlobal('navigator', original);
  });

  it('loads all history sources, aggregates selected months and exposes refetches', async () => {
    const { result } = renderHook(() => useDashboardData(hookProps), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.historyLoading).toBe(false));
    expect(result.current.historySummary?.month).toBe('2026-06 - 2026-07');
    expect(result.current.yearHistory).toHaveLength(1);
    act(() => { result.current.refetchCurrentData(); result.current.refetchHistoryData(); });
    await waitFor(() => expect(api.details).toHaveBeenCalledTimes(2));
  });

  it('reports current, history and detail failures only when no usable data exists', async () => {
    api.current.mockRejectedValueOnce(new Error('curent indisponibil'));
    const current = renderHook(() => useDashboardData({ ...hookProps, activeSection: 'current', selectedHistoryMonths: [], historyYearFilter: null }), { wrapper: wrapper() });
    await waitFor(() => expect(current.result.current.error).toBe('curent indisponibil'));
    current.unmount();

    api.history.mockRejectedValue(new Error('istoric indisponibil'));
    const history = renderHook(() => useDashboardData(hookProps), { wrapper: wrapper() });
    await waitFor(() => expect(history.result.current.historyError).toBe('istoric indisponibil'));
    history.unmount();

    api.history.mockResolvedValue({ history: [point] }); api.details.mockRejectedValueOnce(new Error('detalii indisponibile'));
    const details = renderHook(() => useDashboardData(hookProps), { wrapper: wrapper() });
    await waitFor(() => expect(details.result.current.historyError).toBe('detalii indisponibile'));
    details.unmount();

    api.history.mockResolvedValue({ history: [] }); api.details.mockResolvedValueOnce([response()]);
    const empty = renderHook(() => useDashboardData({ ...hookProps, selectedHistoryMonths: ['2026-07'] }), { wrapper: wrapper() });
    await waitFor(() => expect(empty.result.current.historyError).toBe('Nu exista date istorice pentru filtrarea curenta.'));
  });

  it('keeps history selection valid, bounded and synchronized', () => {
    const months = Array.from({ length: 13 }, (_, index) => `2026-${String(13 - index).padStart(2, '0')}`);
    const hook = renderHook((props) => useDashboardHistorySelection(props), { initialProps: { currentMonth: '2026-12', months, initialSection: 'history' as 'current' | 'history' } });
    expect(hook.result.current.selectedHistoryMonths).toEqual(['2026-11']);
    act(() => hook.result.current.handleToggleHistoryMonth('2026-11'));
    expect(hook.result.current.draftSelectedHistoryMonths).toEqual(['2026-11']);
    act(() => hook.result.current.handleToggleHistoryMonth('2026-10'));
    act(() => hook.result.current.handleApplyHistoryMonths());
    expect(hook.result.current.selectedHistoryMonths).toEqual(['2026-10', '2026-11']);
    const details = document.createElement('details'); details.open = true;
    hook.result.current.historyMonthDropdownRef.current = details;
    act(() => hook.result.current.handleHistoryDropdownToggle());
    expect(hook.result.current.historyMonthDropdownOpen).toBe(true);
    act(() => hook.result.current.handleApplyHistoryPreset(20));
    expect(hook.result.current.selectedHistoryMonths).toHaveLength(12);
    act(() => hook.result.current.handleToggleHistoryMonth(months[12]!));
    expect(hook.result.current.draftSelectedHistoryMonths).toHaveLength(12);
    hook.rerender({ currentMonth: '2026-12', months: ['2026-10', '2026-09'], initialSection: 'history' as const });
    expect(hook.result.current.selectedHistoryMonths).toContain('2026-10');
    hook.rerender({ currentMonth: '2027-01', months: ['2026-12'], initialSection: 'current' as const });
    expect(hook.result.current.activeSection).toBe('current');
    expect(hook.result.current.selectedHistoryMonths).toEqual(['2026-12']);
    expect(sortMonthsAsc(['2026-02', '2026-01'])).toEqual(['2026-01', '2026-02']);
    expect(formatMonthSelectionLabel(['2026-01', '2026-02'])).toContain('2 luni');
    expect(getDefaultHistoryMonth('bad', [])).toBe('bad');
    expect(getDefaultHistoryMonth('2026-01', [])).toBe('2025-12');
  });

  it('loads, clears and reports performance detail with normalized errors', async () => {
    const hook = renderHook(() => useDashboardPerformanceDetail({ currentMonth: '2026-08', firma: 'Mobiup' }));
    act(() => hook.result.current.setPerformanceSelection({ level: 'regional', key: 'Nord' }));
    await waitFor(() => expect(hook.result.current.performanceDetail?.title).toBe('Nord'));
    act(() => hook.result.current.setPerformanceSelection(null));
    expect(hook.result.current.performanceDetail).toBeNull();
    api.performance.mockRejectedValueOnce(new Error('API error: 503 - temporar'));
    act(() => hook.result.current.setPerformanceSelection({ level: 'store', key: 'Alfa', site_code: 'S1' }));
    await waitFor(() => expect(hook.result.current.performanceError).toBe('temporar'));
    api.performance.mockRejectedValueOnce('bad');
    act(() => hook.result.current.setPerformanceSelection({ level: 'agent', key: 'Ana' }));
    await waitFor(() => expect(hook.result.current.performanceError).toBe('Detaliul nu a putut fi incarcat.'));
  });
});

describe('dashboard aggregation presenter', () => {
  it('aggregates sparse multi-month details without inventing denominators', () => {
    const result = aggregateDashboardDetails([response(), response({ summary: { ...summary, total_sales: 0, total_target: 0, total_quantity: 0, total_receipts: 0, working_days: 0, forecast_sales: null, last_sale_date: null, days_in_month: null }, period_comparison: null })] as never, ['2026-06', '2026-07']);
    expect(result.summary.month).toBe('2026-06 - 2026-07');
    expect(result.dailySales[0]?.total_sales).toBe(200);
    expect(result.categoryMix[0]?.share_pct).toBe(100);
    expect(() => aggregateDashboardDetails([], [])).toThrow(/at least one response/);
  });
});
