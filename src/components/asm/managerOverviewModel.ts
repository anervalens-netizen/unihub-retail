import type { ManagerOverview } from '../../api/hr';

/**
 * Pure derivation helpers for the ASM manager-overview page.
 *
 * These functions are deliberately stateless and side-effect free so the
 * responsive views can share the same health, tone, coverage and sort
 * semantics without re-implementing the business rules. They were extracted
 * from `ASMSubtab.tsx` during the C8 frontend decomposition.
 */

export type Tone = 'emerald' | 'amber' | 'rose' | 'slate';

export type HealthInfo = {
  label: string;
  detail: string;
  tone: Tone;
};

export const TONE: Record<Tone, { badge: string; bar: string }> = {
  emerald: {
    badge: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300',
    bar: 'bg-emerald-500',
  },
  amber: {
    badge: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
    bar: 'bg-amber-500',
  },
  rose: {
    badge: 'bg-rose-100 text-rose-700 dark:bg-rose-900/40 dark:text-rose-300',
    bar: 'bg-rose-500',
  },
  slate: {
    badge: 'bg-slate-200 text-slate-600 dark:bg-slate-700 dark:text-slate-300',
    bar: 'bg-slate-400',
  },
};

export function metricTone(value: number | null, green: number, amber: number): Tone {
  if (value === null) return 'slate';
  if (value >= green) return 'emerald';
  if (value >= amber) return 'amber';
  return 'rose';
}

export function healthInfo(row: ManagerOverview): HealthInfo {
  if (!row.reporting_available) {
    return { label: 'Neactualizat', detail: 'Nu există încă raportare pentru luna selectată.', tone: 'slate' };
  }
  if (row.stores_without_agents > 0) {
    return {
      label: 'Necesită atenție',
      detail: `${row.stores_without_agents} magazine fără agent activ în raportare.`,
      tone: 'rose',
    };
  }
  const signals: string[] = [];
  if (row.agents_left > row.agents_added) {
    signals.push(`flux net ${row.agent_delta} agenți`);
  }
  if (row.visits_available && row.visit_coverage_pct !== null && row.visit_coverage_pct < 70) {
    signals.push(`acoperire vizite ${row.visit_coverage_pct}%`);
  }
  if (row.visits_available && row.avg_visit_completion !== null && row.avg_visit_completion < 75) {
    signals.push(`completare vizite ${row.avg_visit_completion}%`);
  }
  if (row.visits_available && row.checklist_score !== null && row.checklist_score < 85) {
    signals.push(`checklist ${row.checklist_score}%`);
  }
  if (signals.length > 0) {
    return {
      label: 'De urmărit',
      detail: `${signals.join(' · ')}.`,
      tone: 'amber',
    };
  }
  return {
    label: 'Structură stabilă',
    detail: row.visits_available
      ? 'Portofoliul este acoperit, fără deficit net de agenți.'
      : 'Structura este acoperită; raportarea Vizite nu este disponibilă pentru această lună.',
    tone: 'emerald',
  };
}

export function staffedStores(row: ManagerOverview): number {
  return row.active_stores - row.stores_without_agents;
}

export function staffingCoverage(row: ManagerOverview): number | null {
  if (row.active_stores <= 0) return null;
  return (staffedStores(row) / row.active_stores) * 100;
}

export type ManagerSortKey =
  | 'manager'
  | 'active_stores'
  | 'active_agents'
  | 'agent_delta'
  | 'staffing'
  | 'visits'
  | 'checklist'
  | 'health';

const HEALTH_SORT_ORDER: Record<Tone, number> = {
  rose: 0,
  amber: 1,
  slate: 2,
  emerald: 3,
};

export function managerSortValue(row: ManagerOverview, key: ManagerSortKey): string | number {
  if (key === 'manager') return row.manager.toLocaleLowerCase('ro-RO');
  if (key === 'staffing') {
    const coverage = staffingCoverage(row);
    return coverage === null ? -1 : coverage;
  }
  if (key === 'visits') return row.visit_coverage_pct ?? -1;
  if (key === 'checklist') return row.checklist_score ?? -1;
  if (key === 'health') return HEALTH_SORT_ORDER[healthInfo(row).tone];
  return row[key];
}

export type ManagerSortDirection = 'asc' | 'desc';

export function compareManagerRows(
  left: ManagerOverview,
  right: ManagerOverview,
  sortKey: ManagerSortKey,
  direction: ManagerSortDirection,
): number {
  const leftValue = managerSortValue(left, sortKey);
  const rightValue = managerSortValue(right, sortKey);
  const result = typeof leftValue === 'string'
    ? leftValue.localeCompare(String(rightValue), 'ro-RO')
    : Number(leftValue) - Number(rightValue);
  return direction === 'asc' ? result : -result;
}

export function sortManagerRows(
  rows: ManagerOverview[],
  sortKey: ManagerSortKey,
  direction: ManagerSortDirection,
): ManagerOverview[] {
  return [...rows].sort((left, right) => compareManagerRows(left, right, sortKey, direction));
}

export type ManagerOverviewSummary = {
  managers: number;
  stores: number;
  agents: number;
  added: number;
  left: number;
  attention: number;
  net: number;
};

export function summarizeManagerOverview(rows: ManagerOverview[] | undefined): ManagerOverviewSummary {
  const safeRows = rows ?? [];
  const added = safeRows.reduce((sum, row) => sum + row.agents_added, 0);
  const left = safeRows.reduce((sum, row) => sum + row.agents_left, 0);
  const attention = safeRows.filter(
    (row) => healthInfo(row).tone === 'rose' || healthInfo(row).tone === 'amber',
  ).length;
  return {
    managers: safeRows.length,
    stores: safeRows.reduce((sum, row) => sum + row.active_stores, 0),
    agents: safeRows.reduce((sum, row) => sum + row.active_agents, 0),
    added,
    left,
    attention,
    net: added - left,
  };
}

export const SALARY_GRILA_MANAGERS = new Set(['Mihai Condorateanu']);

export function hasSalaryGrilaAccess(managerName: string): boolean {
  return SALARY_GRILA_MANAGERS.has(managerName);
}
