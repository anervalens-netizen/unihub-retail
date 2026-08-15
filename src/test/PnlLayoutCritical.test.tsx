// @vitest-environment jsdom

import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const pnlController = vi.hoisted(() => ({ current: {} as Record<string, unknown> }));
const filtersApi = vi.hoisted(() => ({ get: vi.fn() }));

vi.mock('../features/pnl/usePnlController', () => ({ usePnlController: () => pnlController.current }));
vi.mock('../api/filters', () => ({ getFilterOptions: filtersApi.get }));
vi.mock('recharts', () => {
  const Element = ({ children }: { children?: ReactNode }) => <div>{children}</div>;
  return { CartesianGrid: Element, Legend: Element, Line: Element, LineChart: Element, ResponsiveContainer: Element, Tooltip: Element, XAxis: Element, YAxis: Element };
});
vi.mock('motion/react', () => ({
  AnimatePresence: ({ children }: { children?: ReactNode }) => <>{children}</>,
  motion: {
    div: ({ children, initial: _initial, animate: _animate, exit: _exit, transition: _transition, layoutId: _layoutId, ...props }: Record<string, unknown> & { children?: ReactNode }) => <div {...props}>{children}</div>,
  },
}));

import { PnlSubtab } from '../components/PnlSubtab';
import { DesktopSidebar } from '../components/DesktopSidebar';
import { DesktopTopBar } from '../components/DesktopTopBar';
import { MainLayout } from '../components/MainLayout';
import { defaultAppFilters } from '../lib/filterValues';
import { defaultPnlRange, marginPct, monthLabel, monthlyVariance, pnlStoreOptionValue } from '../features/pnl/model';

const months = [{ month: '2026-07', has_estimated: false }, { month: '2026-08', has_estimated: true }];
const stores = [
  { company_name: 'Mobiup', scope_company: 'Mobiup', site_code: 'S1', location: 'Alfa' },
  { company_name: 'Mobicell', scope_company: '', site_code: 'S2', location: 'Beta' },
];
const monthly = [
  { month: '2026-07', revenue: 1000, gross_margin: 500, operating_costs: 300, ebitda: 200, ebit: 100, is_estimated: false },
  { month: '2026-08', revenue: 1200, gross_margin: 550, operating_costs: 450, ebitda: 100, ebit: -50, is_estimated: true },
];
const data = {
  summary: { revenue: 2200, gross_margin: 1050, operating_costs: 750, ebitda: 300, ebit: -50 },
  monthly,
  reconciliation: [{ month: '2026-08', retail_sales_net: 1000, difference_to_net: 100, pnl_to_net_sales_pct: 120 }],
  categories: { v1: 1000, custom: -50 },
  stores: [
    { source_site_code: 'S1', site_code: 'S1', location: 'Alfa', company: 'Mobiup', revenue: 1200, ebitda: 100, ebit: 50, has_estimates: true },
    { source_site_code: 'S2', site_code: 'S2', location: 'Beta', company: 'Mobicell', revenue: 1000, ebitda: -20, ebit: -100, has_estimates: false },
  ],
};

function pnlModel(overrides: Record<string, unknown> = {}) {
  return {
    startMonth: '2026-07', setStartMonth: vi.fn(), endMonth: '2026-08', setEndMonth: vi.fn(),
    company: '', selectCompany: vi.fn(), regional: '', selectRegional: vi.fn(), storeScope: '', setStoreScope: vi.fn(),
    storeSearch: '', setStoreSearch: vi.fn(),
    monthsQuery: { data: months, isLoading: false, isError: false },
    storesQuery: { data: stores, isLoading: false, isError: false },
    regionsQuery: { data: ['Nord'], isLoading: false, isError: false },
    selectedStore: null,
    overviewQuery: { data, isLoading: false, isError: false },
    annualQuery: { data: [{ year: 2026, revenue: 2200, ebitda: 300, ebit: -50, store_count: 2, month_count: 2, is_estimated: true }], isLoading: false, isError: false },
    data,
    variance: { previousMonth: '2026-07', currentMonth: '2026-08', revenuePct: 20, ebitdaPct: -50, ebitPct: null },
    reconciliationWarnings: data.reconciliation,
    filteredStores: data.stores,
    singleReconciliation: data.reconciliation[0],
    ...overrides,
  };
}

describe('P&L critical surface', () => {
  beforeEach(() => { pnlController.current = pnlModel(); });

  it('covers range, scope and variance model edges', () => {
    expect(defaultPnlRange([], new Date('2026-08-01'))).toEqual({ start: '', end: '' });
    expect(defaultPnlRange(['2025-12', '2025-01'], new Date('2026-08-01'))).toEqual({ start: '2025-01', end: '2025-12' });
    expect(defaultPnlRange(['2026-08', '2026-01'], new Date('2026-08-01'))).toEqual({ start: '2026-01', end: '2026-08' });
    expect(monthLabel('2026-08')).toBeTruthy();
    expect(pnlStoreOptionValue(stores[0] as never)).toBe('["Mobiup","S1"]');
    expect(marginPct({ revenue: 0, ebit: 1 } as never)).toBe('—');
    expect(marginPct({ revenue: 100, ebit: 10 } as never)).toBe('10.0%');
    expect(monthlyVariance([])).toBeNull();
    expect(monthlyVariance([monthly[0]] as never[])).toBeNull();
    expect(monthlyVariance(monthly as never[])).toEqual(expect.objectContaining({ revenuePct: 20, ebitdaPct: -50, ebitPct: -150 }));
    expect(monthlyVariance([{ ...monthly[0], revenue: 0, ebitda: 0, ebit: 0 }, monthly[1]] as never[])?.revenuePct).toBeNull();
  });

  it('renders full data, notices, filters, charts and store search', () => {
    render(<PnlSubtab />);
    expect(screen.getByText('Profit & Loss')).toBeInTheDocument();
    expect(screen.getByText(/Intervalul conține luni estimate/)).toBeInTheDocument();
    expect(screen.getByText('Reconciliere de verificat')).toBeInTheDocument();
    expect(screen.getByText('Structură P&L')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Companie'), { target: { value: 'Mobiup' } });
    fireEvent.change(screen.getByLabelText('RM / regiune'), { target: { value: 'Nord' } });
    fireEvent.change(screen.getByLabelText('Magazin'), { target: { value: '["Mobiup","S1"]' } });
    fireEvent.change(screen.getByPlaceholderText('Caută magazin…'), { target: { value: 'alfa' } });
    expect((pnlController.current.selectCompany as ReturnType<typeof vi.fn>)).toHaveBeenCalledWith('Mobiup');
    expect((pnlController.current.setStoreSearch as ReturnType<typeof vi.fn>)).toHaveBeenCalledWith('alfa');
  });

  it('covers loading/error/annual empty variants', () => {
    pnlController.current = pnlModel({ monthsQuery: { data: null, isLoading: true, isError: false } });
    const { rerender } = render(<PnlSubtab />);
    expect(screen.getByText(/Se încarcă istoricul/)).toBeInTheDocument();
    pnlController.current = pnlModel({ monthsQuery: { data: null, isLoading: false, isError: true } });
    rerender(<PnlSubtab />);
    expect(screen.getByText(/Nu am putut încărca lunile/)).toBeInTheDocument();
    pnlController.current = pnlModel({ overviewQuery: { data: null, isLoading: true, isError: false }, data: null });
    rerender(<PnlSubtab />);
    expect(screen.getByText(/Calculez indicatorii/)).toBeInTheDocument();
    pnlController.current = pnlModel({ overviewQuery: { data: null, isLoading: false, isError: true }, data: null });
    rerender(<PnlSubtab />);
    expect(screen.getByText(/Nu am putut încărca raportul/)).toBeInTheDocument();
    pnlController.current = pnlModel({ annualQuery: { data: [], isLoading: false, isError: false }, reconciliationWarnings: [], singleReconciliation: { ...data.reconciliation[0], pnl_to_net_sales_pct: null }, variance: null });
    rerender(<PnlSubtab />);
    expect(screen.getByText(/Nu există istoric anual/)).toBeInTheDocument();
    pnlController.current = pnlModel({ annualQuery: { data: null, isLoading: false, isError: true } });
    rerender(<PnlSubtab />);
    expect(screen.getByText(/Nu am putut încărca evoluția anuală/)).toBeInTheDocument();
  });
});

describe('layout critical surfaces', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    filtersApi.get.mockResolvedValue({
      firme: ['Mobiup', 'Mobicell'], regionali: ['Nord', 'Sud'], asmi: [],
      magazine: [{ site_code: 'S2', locatie: 'Beta', firma: 'Mobicell', regional: 'Sud' }, { site_code: 'S1', locatie: 'Alfa', firma: 'Mobiup', regional: 'Nord' }],
      agenti: [{ agent: 'Ana', firma: 'Mobiup', regional: 'Nord', site_code: 'S1' }, { agent: 'Ana', firma: 'Mobiup', regional: 'Nord', site_code: 'S1' }, { agent: 'Bogdan', firma: 'Mobicell', regional: 'Sud', site_code: 'S2' }],
    });
  });

  it('renders navigation, badges, breadcrumb, filters and logout branches', () => {
    const setTab = vi.fn(); const setTheme = vi.fn(); const logout = vi.fn(); const open = vi.fn();
    const { rerender } = render(<><DesktopSidebar activeTab="hub" setActiveTab={setTab} theme="light" setTheme={setTheme} errorCount={12} canAccessManagement={false} /><DesktopTopBar activeTab="hub" mgmtSubTab="salarii" showFilterButton onOpenFilter={open} filters={{ firma: 'Mobiup', rm: 'Nord', magazin: ['S1'], agent: ['Ana'] }} userEmail="owner@example.test" onLogout={logout} /></>);
    expect(screen.queryByRole('button', { name: 'Management' })).not.toBeInTheDocument();
    expect(screen.getByText('9+')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Filtre/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Logout' }));
    fireEvent.click(screen.getByRole('button', { name: 'Focus' }));
    expect(open).toHaveBeenCalledOnce(); expect(logout).toHaveBeenCalledOnce(); expect(setTab).toHaveBeenCalledWith('focus');
    rerender(<DesktopTopBar activeTab="management" mgmtSubTab="salarii" showFilterButton={false} onOpenFilter={open} filters={defaultAppFilters()} />);
    expect(screen.getByText(/Management/)).toBeInTheDocument();
  });

  it('loads scoped options and executes mobile multi-select/reset/apply controls', async () => {
    const setFilters = vi.fn(); const setTab = vi.fn(); const setOpen = vi.fn(); const logout = vi.fn();
    render(<MainLayout activeTab="management" setActiveTab={setTab} isFilterOpen setIsFilterOpen={setOpen} filters={{ firma: 'Mobiup', rm: 'Nord', magazin: ['S1'], agent: ['Ana'] }} setFilters={setFilters} filterMonth="2026-08" theme="dark" setTheme={vi.fn()} mgmtSubTab="salarii" errorCount={2} userEmail="owner@example.test" onLogout={logout}>Conținut</MainLayout>);
    expect(await screen.findByText('Filtre active')).toBeInTheDocument();
    screen.getAllByRole('button', { name: /Filtre/ }).forEach((button) => fireEvent.click(button));
    await waitFor(() => expect(filtersApi.get).toHaveBeenCalledWith('2026-08'));
    const sheet = screen.getByText('Filtre active').closest('.mobile-filter-sheet') as HTMLElement;
    const selects = within(sheet).getAllByRole('combobox');
    fireEvent.change(selects[0]!, { target: { value: 'Mobicell' } });
    fireEvent.change(selects[1]!, { target: { value: 'Nord' } });
    fireEvent.click(within(sheet).getByRole('button', { name: /Alfa/ }));
    fireEvent.change(within(sheet).getByPlaceholderText('Cauta magazin...'), { target: { value: 'none' } });
    expect(within(sheet).getByText('Niciun rezultat.')).toBeInTheDocument();
    fireEvent.change(within(sheet).getByPlaceholderText('Cauta magazin...'), { target: { value: 'alfa' } });
    fireEvent.click(within(sheet).getAllByRole('button', { name: /Alfa \(S1\)/ })[1]!);
    fireEvent.click(within(sheet).getByRole('button', { name: /Ana/ }));
    fireEvent.click(within(sheet).getByRole('button', { name: 'Reseteaza' }));
    fireEvent.click(within(sheet).getByRole('button', { name: 'Aplica' }));
    fireEvent.click(screen.getByRole('button', { name: 'Inchide' }));
    expect(setFilters).toHaveBeenCalled();
    expect(setOpen).toHaveBeenCalledWith(false);
  });

  it('keeps filter model safe when month is absent or loading fails', async () => {
    filtersApi.get.mockRejectedValueOnce(new Error('offline'));
    const setFilters = vi.fn();
    const { rerender } = render(<MainLayout activeTab="hub" setActiveTab={vi.fn()} isFilterOpen={false} setIsFilterOpen={vi.fn()} filters={defaultAppFilters()} setFilters={setFilters} filterMonth="2026-08" theme="light" setTheme={vi.fn()} mgmtSubTab="asm">x</MainLayout>);
    await waitFor(() => expect(filtersApi.get).toHaveBeenCalled());
    rerender(<MainLayout activeTab="settings" setActiveTab={vi.fn()} isFilterOpen={false} setIsFilterOpen={vi.fn()} filters={defaultAppFilters()} setFilters={setFilters} filterMonth="" theme="light" setTheme={vi.fn()} mgmtSubTab="asm" showFilterButton={false}>x</MainLayout>);
    expect(screen.queryByRole('button', { name: 'Filtre' })).not.toBeInTheDocument();
  });
});
