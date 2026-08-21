// @vitest-environment jsdom

import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import type { ManagerOverview } from '../../api/hr';
import { ManagerStorePortfolio } from './ManagerStorePortfolio';

function makeRow(stores: NonNullable<ManagerOverview['stores']>): ManagerOverview {
  return {
    manager: 'Test Manager',
    month: '2026-08',
    active_stores: stores.length,
    active_agents: 6,
    previous_active_agents: 6,
    agents_per_store: 2,
    agents_added: 0,
    agents_left: 0,
    agent_delta: 0,
    stores_without_agents: 0,
    visited_stores: 0,
    total_visits: 0,
    visits_available: true,
    reporting_available: true,
    regional: null,
    approved_pct: null,
    visit_coverage_pct: 90,
    avg_visit_completion: 92,
    checklist_score: 95,
    stores,
  };
}

const baseStores = [
  {
    site_code: 'M001',
    locatie: 'Magazin Centru',
    firma: 'Mobiup' as const,
    active_agents: 4,
    previous_active_agents: 5,
    agent_delta: -1,
  },
  {
    site_code: 'M002',
    locatie: 'Magazin Nord',
    firma: 'MobiCell' as const,
    active_agents: 2,
    previous_active_agents: 1,
    agent_delta: 1,
  },
];

describe('ManagerStorePortfolio', () => {
  it('renders one row per store with the location and site code', () => {
    render(<ManagerStorePortfolio row={makeRow(baseStores)} />);
    expect(screen.getByText('Magazin Centru')).toBeInTheDocument();
    expect(screen.getByText('Magazin Nord')).toBeInTheDocument();
    expect(screen.getByText('M001')).toBeInTheDocument();
    expect(screen.getByText('M002')).toBeInTheDocument();
  });

  it('uses FirmaBadge for the firma cell', () => {
    render(<ManagerStorePortfolio row={makeRow(baseStores)} />);
    expect(document.querySelectorAll('[title="Mobiup"]').length).toBeGreaterThan(0);
    expect(document.querySelectorAll('[title="MobiCell"]').length).toBeGreaterThan(0);
  });

  it('prefixes a positive agent_delta with + and a negative one without', () => {
    render(<ManagerStorePortfolio row={makeRow(baseStores)} />);
    expect(screen.getByText('-1')).toBeInTheDocument();
    expect(screen.getByText('+1')).toBeInTheDocument();
  });

  it('uses the neutral slate tone for stores with zero delta', () => {
    const stable = [{ ...baseStores[0]!, agent_delta: 0 }];
    render(<ManagerStorePortfolio row={makeRow(stable)} />);
    expect(screen.getByText('0')).toBeInTheDocument();
  });
});
