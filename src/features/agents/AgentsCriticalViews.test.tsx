// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { createRef, type ComponentProps, type ComponentType, type ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const api = vi.hoisted(() => ({ profile: vi.fn(), history: vi.fn() }));
const controller = vi.hoisted(() => ({ current: {} as Record<string, unknown> }));

vi.mock('../../api/agents', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../api/agents')>()),
  fetchAgentProfile: api.profile,
  fetchAgentHistory: api.history,
}));
vi.mock('./useAgentsPageController', () => ({ useAgentsPageController: () => controller.current }));
vi.mock('recharts', () => {
  const Element = ({ children }: { children?: ReactNode }) => <div>{children}</div>;
  const Axis = ({ tickFormatter }: { tickFormatter?: (value: string) => string }) => <div>{tickFormatter?.('2026-08')}</div>;
  const Tooltip = ({ content: Content }: { content?: ComponentType<Record<string, unknown>> }) => <div>{Content && <><Content active={false} payload={[]} label="2026-08" /><Content active payload={[{ payload: { is_baseline: true }, color: '#fff', name: 'Iesiti', dataKey: 'churned_negative', value: -2 }, { payload: {}, color: '#000', name: 'Noi', dataKey: 'new', value: null }]} label="2026-08" /></>}</div>;
  return { Bar: Element, CartesianGrid: Element, ComposedChart: Element, Legend: Element, Line: Element, ResponsiveContainer: Element, Tooltip, XAxis: Axis, YAxis: Axis };
});

import { Agents } from './AgentsPage';
import { AgentDetails, AgentDrawer } from './AgentDetails';
import { AgentsCoverageView } from './AgentsCoverageView';
import { AgentsListView } from './AgentsListView';
import { AgentsOverviewView } from './AgentsOverviewView';
import { AgentsTeamMovementView } from './AgentsTeamMovementView';
import { deserializeAgentListTab, deserializeAgentsMainTab, deserializeSelectedAgent, hasNoSelectedAgent } from './model';
import { defaultAppFilters } from '../../lib/filterValues';

function queryWrapper(children: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

const agents = [
  { agent: 'Ana', firma: 'Mobiup', store_name: 'Alfa', current_status: 'active', is_new: true, is_reactivated: false, total_sales: 10000, total_quantity: 10 },
  { agent: 'Bogdan', firma: 'Mobicell', store_name: 'Beta', current_status: 'inactive_recent', is_new: false, is_reactivated: true, total_sales: 5000, total_quantity: 5 },
  { agent: 'Carmen', firma: null, store_name: null, current_status: 'churned', is_new: false, is_reactivated: false, total_sales: 0, total_quantity: 0 },
];

const coverageItems = [
  { site_code: 'S1', locatie: 'Alfa', firma: 'Mobiup', regional: 'Nord', asm: 'RM A', status: 'covered', agent_count: 2, previous_agent_count: 1, has_changes: true, added_agents_count: 1, removed_agents_count: 0, change_reason: 'intrare' },
  { site_code: 'S2', locatie: '', firma: 'Mobicell', regional: 'Sud', asm: 'RM B', status: 'closed', agent_count: 0, previous_agent_count: 2, has_changes: true, added_agents_count: 0, removed_agents_count: 2, change_reason: null },
];

const coverage = { active_stores_count: 1, modified_stores_count: 2, closed_stores_count: 1, items: coverageItems };
const overview = { active_count: 10, new_count: 2, reactivated_count: 1, left_this_month_count: 3, retention_rate: 82.5, total_unique_agents: 20, avg_seniority_months: 8, stability_rate: 70, churned_total_count: 5 };
const chartData = [
  { month: '2025-01', active: 8, new: 0, reactivated: 0, churned: 0, churned_negative: 0, net_growth: 0, is_baseline: true },
  { month: '2026-08', active: 10, new: 2, reactivated: 1, churned: 1, churned_negative: -1, net_growth: 2, is_baseline: false },
];

function viewProps(overrides: Record<string, unknown> = {}) {
  return {
    overviewSection: 'team', selectOverviewSection: vi.fn(), currentMonth: '2026-08', filterLabel: 'Firma: Mobiup', loadingOverview: true,
    overview, chartData, maxMovement: 7, churnAnalysis: { currentChurnRate: 10, avgChurnRate: 8.5, totalExited: 4, currentExited: 1, currentNetGrowth: -2 },
    topFluxStores: coverageItems.map((item) => ({ ...item, change_count: item.added_agents_count + item.removed_agents_count })), teamSectionRef: createRef<HTMLDivElement>(),
    coverage, loadingCoverage: true, expandedSection: 'active', setExpandedSection: vi.fn((updater) => typeof updater === 'function' && updater('active')), coverageSectionRef: createRef<HTMLDivElement>(),
    list: agents, filteredList: agents, loadingList: true, activeTab: 'active', setActiveTab: vi.fn(), search: 'an', setSearch: vi.fn(),
    cardFirma: 'Mobiup', setCardFirma: vi.fn(), cardMagazin: 'Alfa', setCardMagazin: vi.fn(),
    filterOptions: { firme: ['Mobiup', 'Mobicell'], regionali: [], asmi: [], magazine: [{ site_code: 'S1', locatie: 'Alfa', firma: 'Mobiup', regional: 'Nord' }, { site_code: 'S2', locatie: 'Beta', firma: 'Mobicell', regional: 'Sud' }], agenti: [] },
    setSelectedAgent: vi.fn(), listSectionRef: createRef<HTMLDivElement>(),
    ...overrides,
  };
}

function pageController(overrides: Record<string, unknown> = {}) {
  return {
    ...viewProps(), mainTab: 'overview', setMainTab: vi.fn(), selectedAgent: null, setSelectedAgent: vi.fn(),
    ...overrides,
  };
}

describe('agents critical views', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.profile.mockResolvedValue({ agent: 'Ana', current_status: 'active', first_seen_month: '2025-01', active_months_count: 12, career_total_sales: 120000, best_month: '2026-07', best_month_sales: 20000, distinct_store_count: 2, distinct_firma_count: 1, reactivation_count: 1, longest_active_streak: 10 });
    api.history.mockResolvedValue({ history: [{ month: '2026-07', total_sales: 20000, total_quantity: 10, receipt_count: 4, active_store_count: 1 }] });
    controller.current = pageController();
  });

  it('covers persisted state model fallbacks', () => {
    expect(deserializeAgentListTab('active', 'all')).toBe('active');
    expect(deserializeAgentListTab('bad', 'all')).toBe('all');
    expect(deserializeAgentsMainTab('analysis', 'overview')).toBe('analysis');
    expect(deserializeAgentsMainTab('bad', 'overview')).toBe('overview');
    expect(deserializeSelectedAgent('Ana')).toBe('Ana');
    expect(deserializeSelectedAgent('')).toBeNull();
    expect(hasNoSelectedAgent(null)).toBe(true);
    expect(hasNoSelectedAgent('Ana')).toBe(false);
  });

  it('composes overview and executes section/list/filter/selection controls', () => {
    const props = viewProps();
    render(<AgentsOverviewView {...props as unknown as ComponentProps<typeof AgentsOverviewView>} />);
    expect(screen.getByText('Snapshot — 2026-08')).toBeInTheDocument();
    expect(screen.getByText('Magazine active (1)')).toBeInTheDocument();
    expect(screen.getByText('Lista Agenti')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', { name: 'Acoperire magazine' }));
    fireEvent.click(screen.getByRole('button', { name: /Cu Modificări/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Miscari' }));
    fireEvent.change(screen.getByPlaceholderText('Cauta dupa nume agent...'), { target: { value: 'bog' } });
    const selects = screen.getAllByRole('combobox');
    fireEvent.change(selects[0]!, { target: { value: 'Mobicell' } });
    fireEvent.change(selects[1]!, { target: { value: 'Beta' } });
    fireEvent.click(screen.getByRole('button', { name: /Ana/ }));
    expect(props.selectOverviewSection).toHaveBeenCalledWith('coverage');
    expect(props.setSelectedAgent).toHaveBeenCalledWith('Ana');
  });

  it('covers all coverage row tones and missing data counters', () => {
    const setter = vi.fn();
    const { rerender } = render(<AgentsCoverageView {...viewProps({ expandedSection: 'modified', loadingCoverage: false, setExpandedSection: setter }) as unknown as ComponentProps<typeof AgentsCoverageView>} />);
    expect(screen.getByText(/Magazine cu modificări/)).toBeInTheDocument();
    rerender(<AgentsCoverageView {...viewProps({ expandedSection: 'inactive', loadingCoverage: false, setExpandedSection: setter }) as unknown as ComponentProps<typeof AgentsCoverageView>} />);
    expect(screen.getByText(/Magazine inactive/)).toBeInTheDocument();
    rerender(<AgentsCoverageView {...viewProps({ coverage: undefined, expandedSection: null, loadingCoverage: false, setExpandedSection: setter }) as unknown as ComponentProps<typeof AgentsCoverageView>} />);
    expect(screen.getAllByText('-')).toHaveLength(3);
  });

  it('covers list empty/max/all status render branches', () => {
    const props = viewProps({ list: Array.from({ length: 200 }, (_, index) => ({ ...agents[index % agents.length]!, agent: `Agent ${index}` })), filteredList: agents, loadingList: false, activeTab: 'all', search: '', cardFirma: 'Toate', cardMagazin: 'Toate' });
    const { rerender } = render(<AgentsListView {...props as unknown as ComponentProps<typeof AgentsListView>} />);
    expect(screen.getByText(/3 din 200/)).toBeInTheDocument();
    expect(screen.getByText('INACTIV RECENT')).toBeInTheDocument();
    expect(screen.getByText('IESIT')).toBeInTheDocument();
    rerender(<AgentsListView {...viewProps({ list: [], filteredList: [], loadingList: false, filterOptions: null, search: '', cardFirma: 'Toate', cardMagazin: 'Toate' }) as unknown as ComponentProps<typeof AgentsListView>} />);
    expect(screen.getByText('Niciun agent in aceasta categorie')).toBeInTheDocument();
  });

  it('covers rich and empty team movement branches', () => {
    const { rerender } = render(<AgentsTeamMovementView {...viewProps() as unknown as ComponentProps<typeof AgentsTeamMovementView>} />);
    expect(screen.getByText('Analiza Churn')).toBeInTheDocument();
    rerender(<AgentsTeamMovementView {...viewProps({ overview: undefined, chartData: [], topFluxStores: [], loadingOverview: false, churnAnalysis: { currentChurnRate: null, avgChurnRate: null, totalExited: 0, currentExited: 0, currentNetGrowth: 2 } }) as unknown as ComponentProps<typeof AgentsTeamMovementView>} />);
    expect(screen.getByText('Nu exista modificari in selectia curenta.')).toBeInTheDocument();
    expect(screen.getByText('Nu exista date de miscare.')).toBeInTheDocument();
  });

  it('renders profile status/history/loading/error and drawer close branches', async () => {
    const { rerender } = render(queryWrapper(<AgentDetails agent="Ana" currentMonth="2026-08" />));
    expect(await screen.findByText('Istoric Vanzari')).toBeInTheDocument();
    expect(screen.getByText('Activ')).toBeInTheDocument();

    api.profile.mockResolvedValueOnce({ ...(await api.profile.mock.results[0]?.value), agent: 'Bogdan', current_status: 'inactive_recent', best_month: null });
    api.history.mockResolvedValueOnce({ history: [] });
    rerender(queryWrapper(<AgentDetails key="bogdan" agent="Bogdan" currentMonth="2026-08" />));
    expect(await screen.findByText('Inactiv recent')).toBeInTheDocument();
    expect(screen.getByText('Nu exista istoric.')).toBeInTheDocument();

    api.profile.mockResolvedValueOnce({ agent: 'Carmen', current_status: 'churned', first_seen_month: '2025-01', active_months_count: 2, career_total_sales: 1, best_month: null, best_month_sales: 0, distinct_store_count: 1, distinct_firma_count: 1, reactivation_count: 0, longest_active_streak: 2 });
    api.history.mockResolvedValueOnce({ history: [] });
    rerender(queryWrapper(<AgentDetails key="carmen" agent="Carmen" currentMonth="2026-08" />));
    expect(await screen.findByText('Iesit')).toBeInTheDocument();

    api.profile.mockResolvedValueOnce(null);
    rerender(queryWrapper(<AgentDetails key="none" agent="None" currentMonth="2026-08" />));
    expect(await screen.findByText('Eroare la incarcare profil')).toBeInTheDocument();
    const onClose = vi.fn();
    rerender(queryWrapper(<AgentDrawer agent="Ana" currentMonth="2026-08" isOpen onClose={onClose} />));
    fireEvent.click(screen.getByRole('button'));
    expect(onClose).toHaveBeenCalled();
    rerender(queryWrapper(<AgentDrawer agent="Ana" currentMonth="2026-08" isOpen={false} onClose={onClose} />));
  });

  it('covers the page overview and selected-agent composition', async () => {
    const { rerender } = render(queryWrapper(<Agents currentMonth="2026-08" months={['2026-08']} filters={defaultAppFilters()} />));
    expect(screen.getByRole('tablist', { name: 'Secțiuni Agenți' })).toBeInTheDocument();
    controller.current = pageController({ selectedAgent: 'Ana' });
    rerender(queryWrapper(<Agents currentMonth="2026-08" months={['2026-08']} filters={defaultAppFilters()} />));
    expect(await screen.findByText('Profil agent')).toBeInTheDocument();
  });
});
