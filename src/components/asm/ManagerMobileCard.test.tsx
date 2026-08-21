// @vitest-environment jsdom

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { ManagerOverview } from '../../api/hr';
import { ManagerMobileCard } from './ManagerMobileCard';

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

describe('ManagerMobileCard', () => {
  afterEach(() => {
    document.body.innerHTML = '';
  });

  it('renders the manager name and the active stores / agents summary', () => {
    render(<ManagerMobileCard row={makeRow()} month="2026-08" />);
    expect(screen.getByText('Andrei Stancu')).toBeInTheDocument();
    expect(screen.getByText(/4 magazine · 6 agenți/)).toBeInTheDocument();
  });

  it('shows the Structură stabilă badge for a healthy portfolio', () => {
    render(<ManagerMobileCard row={makeRow()} month="2026-08" />);
    expect(screen.getByText('Structură stabilă')).toBeInTheDocument();
  });

  it('shows the Necesită atenție badge when stores have no agents', () => {
    render(<ManagerMobileCard row={makeRow({ stores_without_agents: 2 })} month="2026-08" />);
    expect(screen.getByText('Necesită atenție')).toBeInTheDocument();
    expect(screen.getByText(/2 magazine fără agent/)).toBeInTheDocument();
  });

  it('hides the store portfolio by default and reveals it on expansion', async () => {
    const user = userEvent.setup();
    render(<ManagerMobileCard row={makeRow()} month="2026-08" />);
    expect(screen.queryByText('Portofoliu magazine')).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /Andrei Stancu/i }));
    expect(await screen.findByText('Portofoliu magazine')).toBeInTheDocument();
    expect(screen.getByText('Magazin Centru')).toBeInTheDocument();
  });

  it('renders the salary-grila badge and AsmSalaryGrila when the manager is allowed', async () => {
    const user = userEvent.setup();
    render(
      <ManagerMobileCard
        row={makeRow({ manager: 'Mihai Condorateanu' })}
        month="2026-08"
      />,
    );
    expect(screen.getByText('Grilă salariu')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /Mihai Condorateanu/i }));
    expect(await screen.findByTestId('asm-salary-grila')).toBeInTheDocument();
  });

  it('omits the salary-grila badge for managers outside the allowlist', () => {
    render(<ManagerMobileCard row={makeRow()} month="2026-08" />);
    expect(screen.queryByText('Grilă salariu')).not.toBeInTheDocument();
  });
});
