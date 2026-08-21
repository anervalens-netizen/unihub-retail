// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { ManagerOverview } from '../api/hr';
import { ASMSubtab } from './ASMSubtab';

const api = vi.hoisted(() => ({
  fetchManagerOverview: vi.fn(),
}));

vi.mock('../api/hr', async (importOriginal) => {
  const original = await importOriginal<typeof import('../api/hr')>();
  return {
    ...original,
    fetchManagerOverview: api.fetchManagerOverview,
  };
});

vi.mock('./AsmSalaryGrila', () => ({
  AsmSalaryGrila: () => <div data-testid="asm-salary-grila" />,
}));

function makeRow(overrides: Partial<ManagerOverview> = {}): ManagerOverview {
  return {
    manager: 'Andrei Stancu',
    month: '2026-08',
    active_stores: 4,
    active_agents: 6,
    previous_active_agents: 6,
    agents_per_store: 1.5,
    agents_added: 2,
    agents_left: 1,
    agent_delta: 1,
    stores_without_agents: 0,
    visited_stores: 3,
    total_visits: 9,
    visits_available: true,
    reporting_available: true,
    regional: null,
    approved_pct: null,
    visit_coverage_pct: 90,
    avg_visit_completion: 92,
    checklist_score: 95,
    stores: [],
    ...overrides,
  };
}

function renderSubtab(initialMonth?: string) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  render(
    <QueryClientProvider client={client}>
      <ASMSubtab currentMonth={initialMonth} />
    </QueryClientProvider>,
  );
  return client;
}

describe('ASMSubtab facade', () => {
  beforeEach(() => {
    api.fetchManagerOverview.mockReset();
  });

  afterEach(() => {
    cleanup();
  });

  it('shows the loading state while the query is in flight', () => {
    api.fetchManagerOverview.mockReturnValue(new Promise(() => {}));
    renderSubtab('2026-08');
    expect(screen.getByText(/Se încarcă overview-ul managerilor/)).toBeInTheDocument();
  });

  it('shows the error state when the query rejects', async () => {
    api.fetchManagerOverview.mockRejectedValue(new Error('boom'));
    renderSubtab('2026-08');
    expect(await screen.findByText(/Nu am putut încărca overview-ul/)).toBeInTheDocument();
  });

  it('shows the empty state when no managers are returned', async () => {
    api.fetchManagerOverview.mockResolvedValue([]);
    renderSubtab('2026-08');
    expect(await screen.findByText(/Nu există manageri activi/)).toBeInTheDocument();
  });

  it('renders summary cards and the manager list when the query resolves', async () => {
    api.fetchManagerOverview.mockResolvedValue([
      makeRow({ manager: 'Ada' }),
      makeRow({ manager: 'Bogdan', stores_without_agents: 1 }),
    ]);
    renderSubtab('2026-08');
    // Let the query promise resolve and React re-render before checking DOM.
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(screen.getAllByText('Ada').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Bogdan').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Manageri activi').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Magazine active').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Agenți activi').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Mișcare echipe').length).toBeGreaterThan(0);
  });

  it('uses the provided currentMonth prop for the query and renders it in the header', async () => {
    api.fetchManagerOverview.mockResolvedValue([]);
    renderSubtab('2026-07');
    await screen.findByText(/Nu există manageri activi/);
    expect(api.fetchManagerOverview).toHaveBeenCalledWith('2026-07', expect.anything());
  });

  it('triggers a refetch when the refresh button is pressed', async () => {
    api.fetchManagerOverview.mockResolvedValue([]);
    const user = userEvent.setup();
    renderSubtab('2026-08');
    await screen.findByText(/Nu există manageri activi/);
    const callsBefore = api.fetchManagerOverview.mock.calls.length;
    await user.click(screen.getByRole('button', { name: 'Reîncarcă overview manageri' }));
    expect(api.fetchManagerOverview.mock.calls.length).toBeGreaterThan(callsBefore);
  });
});

