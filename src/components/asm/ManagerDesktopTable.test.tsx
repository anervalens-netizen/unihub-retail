// @vitest-environment jsdom

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { ManagerOverview } from '../../api/hr';
import { ManagerDesktopTable } from './ManagerDesktopTable';

vi.mock('../AsmSalaryGrila', () => ({
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
    stores: [
      {
        site_code: 'M001',
        locatie: 'Magazin Centru',
        firma: 'Mobiup',
        active_agents: 3,
        previous_active_agents: 3,
        agent_delta: 0,
      },
    ],
    ...overrides,
  };
}

describe('ManagerDesktopTable', () => {
  afterEach(() => {
    document.body.innerHTML = '';
  });

  it('renders one row per manager with the health badge', () => {
    const rows = [makeRow({ manager: 'Ada Popescu' }), makeRow({ manager: 'Bogdan Ionescu' })];
    render(<ManagerDesktopTable rows={rows} month="2026-08" />);
    expect(screen.getByText('Ada Popescu')).toBeInTheDocument();
    expect(screen.getByText('Bogdan Ionescu')).toBeInTheDocument();
    expect(screen.getAllByText('Structură stabilă').length).toBeGreaterThan(0);
  });

  it('sorts the manager column descending on second click', async () => {
    const user = userEvent.setup();
    const rows = [makeRow({ manager: 'Ada Popescu' }), makeRow({ manager: 'Bogdan Ionescu' })];
    render(<ManagerDesktopTable rows={rows} month="2026-08" />);

    // Initial state: ascending by manager → Ada, Bogdan
    expect(getManagerOrder()).toEqual(['Ada Popescu', 'Bogdan Ionescu']);

    const managerHeader = screen.getByRole('button', { name: 'Manager' });
    await user.click(managerHeader); // same key → toggle to desc
    expect(getManagerOrder()).toEqual(['Bogdan Ionescu', 'Ada Popescu']);
  });

  it('uses desc as the default direction when switching to a non-manager column', async () => {
    const user = userEvent.setup();
    const rows = [
      makeRow({ manager: 'Ada', active_stores: 10 }),
      makeRow({ manager: 'Bogdan', active_stores: 4 }),
    ];
    render(<ManagerDesktopTable rows={rows} month="2026-08" />);
    await user.click(screen.getByRole('button', { name: 'Magazine' }));
    // Desc by active_stores: Ada (10) before Bogdan (4)
    expect(getManagerOrder()).toEqual(['Ada', 'Bogdan']);
  });

  it('expands a manager row and reveals the store portfolio', async () => {
    const user = userEvent.setup();
    render(<ManagerDesktopTable rows={[makeRow()]} month="2026-08" />);
    expect(screen.queryByText('Magazin Centru')).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /Andrei Stancu/ }));
    expect(await screen.findByText('Magazin Centru')).toBeInTheDocument();
  });

  it('shows the salary-grila icon for managers in the allowlist and mounts AsmSalaryGrila on expansion', async () => {
    const user = userEvent.setup();
    render(
      <ManagerDesktopTable
        rows={[makeRow({ manager: 'Mihai Condorateanu' })]}
        month="2026-08"
      />,
    );
    expect(screen.getByLabelText('Grilă salariu disponibilă')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /Mihai Condorateanu/ }));
    expect(await screen.findByTestId('asm-salary-grila')).toBeInTheDocument();
  });
});

function getManagerOrder(): string[] {
  const cells = document.querySelectorAll('tbody > tr > td:first-child button');
  return Array.from(cells).map((c) => c.textContent?.trim() ?? '');
}
