// @vitest-environment jsdom

import { fireEvent, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

const pageData = vi.hoisted(() => ({ current: {} as Record<string, unknown> }));

vi.mock('./useCampaignsData', () => ({ useCampaignsData: () => pageData.current }));
vi.mock('./PromoSection', () => ({ PromoSection: () => <div>Promo fixture</div> }));
vi.mock('./IncentiveSection', () => ({ IncentiveSection: () => <div>Incentive fixture</div> }));
vi.mock('./PremiumView', () => ({ PremiumGlassFocusSection: () => <div>Premium fixture</div> }));
vi.mock('../../components/ExportTableButton', () => ({
  ExportTableButton: ({ rows, columns, filename }: { rows: Array<Record<string, unknown>>; columns: Array<{ value: (row: Record<string, unknown>, index: number) => unknown }>; filename: string }) => (
    <button type="button" onClick={() => rows.forEach((row, index) => columns.forEach((column) => column.value(row, index)))}>{`Export fixture ${filename}`}</button>
  ),
}));

vi.mock('recharts', () => {
  const Element = ({ children }: { children?: ReactNode }) => <div>{children}</div>;
  return { Area: Element, AreaChart: Element, Bar: Element, BarChart: Element, CartesianGrid: Element, Legend: Element, Line: Element, ResponsiveContainer: Element, Tooltip: Element, XAxis: Element, YAxis: Element };
});

import { IncentiveDesktopDashboard, IncentiveDesktopHeader } from '../../components/IncentiveDesktopDashboard';
import { IncentiveQualificationSummary } from '../../components/IncentiveQualificationSummary';
import { ContestSection } from './ContestSection';
import { FocusSection } from './FocusSection';
import { IncentiveAgentsTable, IncentiveStoresTable } from './IncentiveTables';
import { CampaignsPage } from './CampaignsPage';
import { defaultAppFilters } from '../../lib/filterValues';

const contest = {
  key: 'summer', title: 'Concurs vară', subtitle: 'Subtitle', scope_label: 'Toată rețeaua', month: '2026-08', start_date: '2026-08-01', end_date: '2026-08-31', store_count: 2,
  rules: [{ type: 'focus', label: 'Focus', points: 2 }], prizes: [{ rank_from: 1, rank_to: 1, label: 'Telefon' }, { rank_from: 2, rank_to: 3, label: 'Voucher' }],
  leaderboard: [
    { rank: 1, agent: 'Ana', store_name: 'S1 - Alfa', firma: 'Mobiup', focus_points: 10, promo_points: 5, price_points: 2, total_points: 17, prize: 'Telefon' },
    { rank: 4, agent: 'Bogdan', store_name: 'Beta', firma: 'Mobicell', focus_points: 5, promo_points: 1, price_points: 0, total_points: 6, prize: null },
    { rank: 5, agent: 'Carmen', store_name: 'Gamma', firma: 'Mobiup', focus_points: 3, promo_points: 1, price_points: 0, total_points: 4, prize: null },
  ],
};

const snapshot = {
  overview: { total_focus_sales: 12000, total_focus_qty: 30, focus_share_pct: 8.5, active_focus_stores: 2 },
  products: [{ item_code: 'P1', item_name: 'Produs Premium', sales_total: 10000, qty_total: 20, store_count: 2 }],
};
const history = [
  { month: '2026-07', total_focus_sales: 10000, total_focus_qty: 25, focus_share_pct: 7.5, active_focus_stores: 2 },
  { month: '2026-08', total_focus_sales: 12000, total_focus_qty: 30, focus_share_pct: 8.5, active_focus_stores: 2 },
];

const promo = {
  incentive_sold_qty: 100, incentive_qty: 80, incentive_qualified_qty: 60, incentive_value: 1200,
  incentive_product_count: 3, incentive_description: 'Mecanism activ', incentive_qualified_stores: 2, incentive_qualified_agents: 4,
  incentive_periods: [
    { label: 'Prima jumătate', start_date: '2026-08-01', end_date: '2026-08-15', product_count: 2, reward_values: [10, 20] },
    { label: 'A doua jumătate', start_date: '2026-08-16', end_date: '2026-08-31', product_count: 1, reward_values: [30] },
  ],
  incentive_category_breakdown: [
    { label: 'Huse', qualified_qty: 20, qty: 30, value: 300, potential: 500 },
    { label: 'Folii', qualified_qty: 40, qty: 70, value: 900, potential: 1200 },
  ],
  incentive_categories: [{ label: '10 RON', qty: 20 }, { label: '20 RON', qty: 10 }],
};

const agentRows = [
  { agent_name: 'Ana', firma: 'Mobiup', store_name: 'S1 - Alfa', achievement: 1.05, qty_sold: 20, val_incentive: 200, incentive_potential: 300 },
  { agent_name: 'Bogdan', firma: 'Mobicell', store_name: 'Beta', achievement: null, qty_sold: 0, val_incentive: 0, incentive_potential: null },
];
const storeRows = [
  { firma: 'Mobiup', store_name: 'S1 - Alfa', achievement: 1.05, qty: 20, incentive_value: 200, incentive_potential: 300 },
  { firma: 'Mobicell', store_name: 'Beta', achievement: null, qty: 0, incentive_value: 0, incentive_potential: null },
];

describe('campaign critical views', () => {
  it('renders contest rich/empty/leaderboard-empty variants and controls', () => {
    const onMonth = vi.fn(); const onSelect = vi.fn();
    const { rerender } = render(<ContestSection contests={[contest] as never[]} selectedContest={contest as never} month="2026-08" months={['2026-08', '2026-07']} currentMonth="2026-08" onMonthChange={onMonth} onSelect={onSelect} />);
    expect(screen.getByText('Concurs vară')).toBeInTheDocument();
    expect(screen.getByText('Locurile 2–3')).toBeInTheDocument();
    expect(screen.getAllByText('Telefon')).toHaveLength(2);
    fireEvent.click(screen.getByRole('button', { name: /Export fixture focus-concurs/ }));
    fireEvent.change(screen.getByRole('combobox'), { target: { value: '2026-07' } });
    rerender(<ContestSection contests={[{ ...contest, leaderboard: [], rules: [], prizes: [], subtitle: null, scope_label: null }] as never[]} selectedContest={{ ...contest, leaderboard: [], rules: [], prizes: [], subtitle: null, scope_label: null } as never} month="2026-08" months={['2026-08']} currentMonth="2026-08" onMonthChange={onMonth} onSelect={onSelect} />);
    expect(screen.getByText(/Nu exista inca vanzari punctate/)).toBeInTheDocument();
    rerender(<ContestSection contests={[]} selectedContest={null} month="2026-08" months={['2026-08']} currentMonth="2026-08" onMonthChange={onMonth} onSelect={onSelect} />);
    expect(screen.getByText(/Nu exista concurs activ/)).toBeInTheDocument();
  });

  it('renders focus history, selection, loading/error/empty and product-empty branches', () => {
    const retry = vi.fn(); const change = vi.fn();
    const base = { snapshot: snapshot as never, history: history as never[], historyMonth: '2026-07', month: '2026-08', months: ['2026-08', '2026-07'], currentMonth: '2026-08', loading: false, error: '', onHistoryMonthChange: change, onMonthChange: change, onRetry: retry };
    const { rerender } = render(<FocusSection {...base} />);
    expect(screen.getByText('Produs Premium')).toBeInTheDocument();
    fireEvent.change(screen.getAllByRole('combobox').at(-1)!, { target: { value: '2026-08' } });
    rerender(<FocusSection {...base} loading />);
    expect(screen.getByText(/Se incarca istoricul focus/)).toBeInTheDocument();
    rerender(<FocusSection {...base} error="Istoric indisponibil" />);
    fireEvent.click(screen.getByRole('button', { name: 'Reincearca' }));
    expect(retry).toHaveBeenCalled();
    rerender(<FocusSection {...base} history={[]} />);
    expect(screen.getByText(/Nu exista indicatori focus/)).toBeInTheDocument();
    rerender(<FocusSection {...base} snapshot={{ ...snapshot, products: [] } as never} />);
    expect(screen.getByText(/Nu exista produse focus vandute/)).toBeInTheDocument();
    expect(screen.getByText(/Nu exista inca focus products/)).toBeInTheDocument();
  });

  it('renders incentive tables, all cell tones and sort interactions', () => {
    render(<><IncentiveAgentsTable rows={agentRows as never[]} month="2026-08" /><IncentiveStoresTable rows={storeRows as never[]} month="2026-08" /></>);
    expect(screen.getAllByText('0 RON').length).toBeGreaterThan(0);
    expect(screen.getAllByText('—').length).toBeGreaterThan(0);
    fireEvent.click(screen.getAllByRole('button', { name: 'Agent' })[0]!);
    fireEvent.click(screen.getAllByRole('button', { name: 'Magazin' })[0]!);
    fireEvent.click(screen.getAllByRole('button', { name: '%Prev.' })[0]!);
    screen.getAllByRole('button', { name: /Export fixture focus-incentive/ }).forEach((button) => fireEvent.click(button));
  });

  it('renders desktop header/dashboard rich and null/empty branches', () => {
    const change = vi.fn();
    const { rerender } = render(<><IncentiveDesktopHeader promoData={promo as never} months={['2026-08', 'bad']} value="2026-08" onChange={change} currentMonth="2026-08" /><IncentiveDesktopDashboard promoData={promo as never} month="2026-08" /><IncentiveQualificationSummary promoData={promo as never} /></>);
    expect(screen.getByText('Mecanisme active')).toBeInTheDocument();
    expect(screen.getAllByText('Calificați acum').length).toBeGreaterThan(1);
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'bad' } });
    expect(change).toHaveBeenCalledWith('bad');
    rerender(<><IncentiveDesktopHeader promoData={null} months={['bad']} value="bad" onChange={change} currentMonth="2026-08" sectionLabel="Custom" title="Titlu" description="Descriere" /><IncentiveDesktopDashboard promoData={null} month="bad" /><IncentiveQualificationSummary promoData={null} /></>);
    expect(screen.getByText('Titlu —')).toBeInTheDocument();
    expect(screen.getByText(/Nu există încă detaliu pe categorii/)).toBeInTheDocument();
    expect(screen.getByText(/Nu există mecanism activ/)).toBeInTheDocument();
  });

  it('covers page loading, error, contest, premium, promo and incentive routing', () => {
    const base = {
      contests: [contest], selectedContestKey: 'summer', contestLoading: false, contestError: '', refetchContests: vi.fn(),
      loading: false, currentError: '', refetchCurrent: vi.fn(), promoData: promo, promoMonth: '2026-08', latestMonth: '2026-08',
      setPromoMonth: vi.fn(), selectedPromotionKey: '', setSelectedPromotionKey: vi.fn(), premiumGlass: null, premiumSurfaceMode: 'summary', setPremiumSurfaceMode: vi.fn(),
      snapshot, focusHistory: history, historyMonth: '2026-07', historyLoading: false, historyError: '', setHistoryMonth: vi.fn(), refetchHistory: vi.fn(), setSelectedContestKey: vi.fn(),
    };
    const props = { currentMonth: '2026-08', months: ['2026-08', '2026-07'], filters: defaultAppFilters(), onSectionChange: vi.fn() };

    pageData.current = { ...base, loading: true };
    const { rerender } = render(<CampaignsPage {...props} preferredSection="premium" />);
    expect(screen.getByText('Se incarca analiza foliilor premium...')).toBeInTheDocument();
    pageData.current = { ...base, loading: true };
    rerender(<CampaignsPage {...props} preferredSection="incentive" />);
    expect(screen.getByText('Se incarca incentive-ul...')).toBeInTheDocument();
    pageData.current = { ...base, loading: true };
    rerender(<CampaignsPage {...props} preferredSection="focus" />);
    expect(screen.getByText('Se incarca datele de focus...')).toBeInTheDocument();
    pageData.current = { ...base, contestLoading: true };
    rerender(<CampaignsPage {...props} preferredSection="concurs" />);
    expect(screen.getByText('Se incarca concursul...')).toBeInTheDocument();
    pageData.current = { ...base, contestError: 'Concurs indisponibil' };
    rerender(<CampaignsPage {...props} preferredSection="concurs" />);
    fireEvent.click(screen.getByRole('button', { name: 'Reincearca' }));
    expect(base.refetchContests).toHaveBeenCalled();
    pageData.current = base;
    rerender(<CampaignsPage {...props} preferredSection="premium" />);
    expect(screen.getByText('Premium fixture')).toBeInTheDocument();
    fireEvent.change(screen.getByRole('combobox'), { target: { value: '2026-07' } });
    expect(base.setPromoMonth).toHaveBeenCalledWith('2026-07');
    rerender(<CampaignsPage {...props} preferredSection="promo" />);
    expect(screen.getByText('Promo fixture')).toBeInTheDocument();
    rerender(<CampaignsPage {...props} preferredSection="incentive" />);
    expect(screen.getByText('Incentive fixture')).toBeInTheDocument();
  });
});
