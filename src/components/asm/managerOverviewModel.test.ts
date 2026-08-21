import { describe, expect, it } from 'vitest';

import type { ManagerOverview } from '../../api/hr';
import {
  TONE,
  compareManagerRows,
  hasSalaryGrilaAccess,
  healthInfo,
  managerSortValue,
  metricTone,
  sortManagerRows,
  staffedStores,
  staffingCoverage,
  summarizeManagerOverview,
  type ManagerSortKey,
} from './managerOverviewModel';

/**
 * Pure characterization tests for the manager-overview model extracted from
 * `ASMSubtab.tsx` during the C8 frontend decomposition.
 *
 * These tests intentionally exercise the real thresholds and ordering
 * semantics so any accidental drift is caught during the refactor.
 */

function makeRow(overrides: Partial<ManagerOverview> = {}): ManagerOverview {
  return {
    manager: 'Test Manager',
    month: '2026-08',
    active_stores: 10,
    active_agents: 20,
    previous_active_agents: 20,
    agents_per_store: 2,
    agents_added: 1,
    agents_left: 1,
    agent_delta: 0,
    stores_without_agents: 0,
    visited_stores: 9,
    total_visits: 27,
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

describe('healthInfo', () => {
  it('returns slate/Neactualizat when reporting is unavailable', () => {
    const row = makeRow({ reporting_available: false });
    const result = healthInfo(row);
    expect(result.tone).toBe('slate');
    expect(result.label).toBe('Neactualizat');
    expect(result.detail).toContain('Nu există');
  });

  it('returns rose/Necesită atenție when stores have no agents', () => {
    const row = makeRow({ stores_without_agents: 3 });
    const result = healthInfo(row);
    expect(result.tone).toBe('rose');
    expect(result.label).toBe('Necesită atenție');
    expect(result.detail).toContain('3 magazine');
  });

  it('returns amber/De urmărit when visit coverage drops below 70%', () => {
    const row = makeRow({ visit_coverage_pct: 65 });
    const result = healthInfo(row);
    expect(result.tone).toBe('amber');
    expect(result.label).toBe('De urmărit');
    expect(result.detail).toContain('acoperire vizite 65%');
  });

  it('returns amber/De urmărit when visit completion drops below 75%', () => {
    const row = makeRow({ visit_coverage_pct: 95, avg_visit_completion: 70 });
    const result = healthInfo(row);
    expect(result.tone).toBe('amber');
    expect(result.detail).toContain('completare vizite 70%');
  });

  it('returns amber/De urmărit when checklist score drops below 85%', () => {
    const row = makeRow({ checklist_score: 80 });
    const result = healthInfo(row);
    expect(result.tone).toBe('amber');
    expect(result.detail).toContain('checklist 80%');
  });

  it('returns amber/De urmărit when more agents left than were added', () => {
    const row = makeRow({ agents_added: 1, agents_left: 4, agent_delta: -3 });
    const result = healthInfo(row);
    expect(result.tone).toBe('amber');
    expect(result.detail).toContain('flux net -3 agenți');
  });

  it('ignores degraded visit/checklist signals when visits are unavailable', () => {
    const row = makeRow({
      visits_available: false,
      visit_coverage_pct: null,
      avg_visit_completion: null,
      checklist_score: null,
    });
    expect(healthInfo(row).tone).toBe('emerald');
  });

  it('returns emerald/Structură stabilă for a healthy portfolio', () => {
    const row = makeRow();
    const result = healthInfo(row);
    expect(result.tone).toBe('emerald');
    expect(result.label).toBe('Structură stabilă');
    expect(result.detail).toContain('Portofoliul este acoperit');
  });

  it('keeps emerald label but switches detail when visits are unavailable', () => {
    const row = makeRow({
      visits_available: false,
      visit_coverage_pct: null,
      avg_visit_completion: null,
      checklist_score: null,
    });
    const result = healthInfo(row);
    expect(result.tone).toBe('emerald');
    expect(result.label).toBe('Structură stabilă');
    expect(result.detail).toContain('Vizite nu este disponibilă');
  });
});

describe('metricTone', () => {
  it('uses slate for null values', () => {
    expect(metricTone(null, 90, 70)).toBe('slate');
  });

  it('uses emerald when at or above the green threshold', () => {
    expect(metricTone(90, 90, 70)).toBe('emerald');
    expect(metricTone(100, 90, 70)).toBe('emerald');
  });

  it('uses amber when between green and amber thresholds', () => {
    expect(metricTone(70, 90, 70)).toBe('amber');
    expect(metricTone(85, 90, 70)).toBe('amber');
  });

  it('uses rose below the amber threshold', () => {
    expect(metricTone(69, 90, 70)).toBe('rose');
  });
});

describe('staffingCoverage', () => {
  it('returns null when there are no active stores', () => {
    expect(staffingCoverage(makeRow({ active_stores: 0 }))).toBeNull();
  });

  it('returns 100 when every store is staffed', () => {
    expect(staffingCoverage(makeRow({ active_stores: 10, stores_without_agents: 0 }))).toBe(100);
  });

  it('falls back to 0 when every store is uncovered', () => {
    expect(staffingCoverage(makeRow({ active_stores: 4, stores_without_agents: 4 }))).toBe(0);
  });

  it('exposes the staffed-store count', () => {
    expect(staffedStores(makeRow({ active_stores: 10, stores_without_agents: 3 }))).toBe(7);
  });

  it('reflects partial coverage', () => {
    expect(staffingCoverage(makeRow({ active_stores: 10, stores_without_agents: 2 }))).toBe(80);
  });
});

describe('managerSortValue + sort/compare helpers', () => {
  const ada = makeRow({ manager: 'Ada Popescu', active_stores: 5 });
  const bogdan = makeRow({ manager: 'Bogdan Ionescu', active_stores: 12 });

  it('sorts by manager using the ro-RO lowercase key (asc)', () => {
    const sorted = sortManagerRows([bogdan, ada], 'manager', 'asc');
    expect(sorted.map((row) => row.manager)).toEqual(['Ada Popescu', 'Bogdan Ionescu']);
  });

  it('reverses order for desc direction', () => {
    const sorted = sortManagerRows([bogdan, ada], 'manager', 'desc');
    expect(sorted.map((row) => row.manager)).toEqual(['Bogdan Ionescu', 'Ada Popescu']);
  });

  it('sorts by numeric fields (active_stores desc)', () => {
    const sorted = sortManagerRows([ada, bogdan], 'active_stores', 'desc');
    expect(sorted[0]?.manager).toBe('Bogdan Ionescu');
  });

  it('falls back to -1 for null visits/checklist so unknown rows sort last in desc', () => {
    const visits = makeRow({ visit_coverage_pct: 90 });
    const unknown = makeRow({ visit_coverage_pct: null });
    const sorted = sortManagerRows([unknown, visits], 'visits', 'desc');
    expect(sorted[0]?.manager).toBe('Test Manager');
    expect(sorted[1]?.manager).toBe('Test Manager');
    expect(managerSortValue(unknown, 'visits')).toBe(-1);
  });

  it('orders by health (rose < amber < slate < emerald)', () => {
    const rose = makeRow({ reporting_available: true, stores_without_agents: 2 });
    const amber = makeRow({ visit_coverage_pct: 50 });
    const emerald = makeRow();
    const slate = makeRow({ reporting_available: false });
    const sorted = sortManagerRows([emerald, slate, amber, rose], 'health', 'asc');
    expect(sorted.map((row) => healthInfo(row).tone)).toEqual(['rose', 'amber', 'slate', 'emerald']);
  });

  it('compareManagerRows returns 0 when keys match', () => {
    const a = makeRow();
    const b = makeRow();
    expect(compareManagerRows(a, b, 'active_agents', 'asc')).toBe(0);
  });

  it('exposes the full set of sortable keys', () => {
    const keys: ManagerSortKey[] = [
      'manager',
      'active_stores',
      'active_agents',
      'agent_delta',
      'staffing',
      'visits',
      'checklist',
      'health',
    ];
    for (const key of keys) {
      expect(typeof managerSortValue(makeRow(), key)).toMatch(/string|number/);
    }
  });
});

describe('summarizeManagerOverview', () => {
  it('aggregates counts, deltas and the attention count from the rows', () => {
    const rows: ManagerOverview[] = [
      makeRow({
        manager: 'A',
        active_stores: 3,
        active_agents: 6,
        agents_added: 2,
        agents_left: 1,
      }),
      makeRow({
        manager: 'B',
        active_stores: 4,
        active_agents: 7,
        agents_added: 1,
        agents_left: 3,
        visit_coverage_pct: 60, // amber signal
      }),
      makeRow({
        manager: 'C',
        active_stores: 5,
        active_agents: 8,
        stores_without_agents: 1, // rose signal
      }),
    ];
    const summary = summarizeManagerOverview(rows);
    expect(summary.managers).toBe(3);
    expect(summary.stores).toBe(12);
    expect(summary.agents).toBe(21);
    expect(summary.added).toBe(4);
    expect(summary.left).toBe(5);
    expect(summary.net).toBe(-1);
    expect(summary.attention).toBe(2);
  });

  it('treats undefined input as an empty list', () => {
    expect(summarizeManagerOverview(undefined)).toEqual({
      managers: 0,
      stores: 0,
      agents: 0,
      added: 0,
      left: 0,
      attention: 0,
      net: 0,
    });
  });

  it('excludes emerald rows from the attention count', () => {
    const rows: ManagerOverview[] = [makeRow(), makeRow()];
    expect(summarizeManagerOverview(rows).attention).toBe(0);
  });
});

describe('TONE palette and salary grila access', () => {
  it('exposes a palette entry for every tone', () => {
    expect(Object.keys(TONE).sort()).toEqual(['amber', 'emerald', 'rose', 'slate']);
    for (const key of Object.keys(TONE) as Array<keyof typeof TONE>) {
      expect(TONE[key].badge).toMatch(/^bg-/);
      expect(TONE[key].bar).toMatch(/^bg-/);
    }
  });

  it('grants salary grila access only to the configured manager name', () => {
    expect(hasSalaryGrilaAccess('Mihai Condorateanu')).toBe(true);
    expect(hasSalaryGrilaAccess('Someone Else')).toBe(false);
  });
});
