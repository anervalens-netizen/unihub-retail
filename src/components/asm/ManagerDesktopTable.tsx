import { Fragment, useMemo, useState } from 'react';
import { ChevronDown, ChevronUp, WalletCards } from 'lucide-react';

import type { ManagerOverview } from '../../api/hr';
import { cn } from '../../lib/utils';
import { AsmSalaryGrila } from '../AsmSalaryGrila';
import { SortableTableHeader } from '../common/TableHeader';
import {
  TONE,
  compareManagerRows,
  hasSalaryGrilaAccess,
  healthInfo,
  staffingCoverage,
  type ManagerSortDirection,
  type ManagerSortKey,
} from './managerOverviewModel';
import { ManagerStorePortfolio } from './ManagerStorePortfolio';

const NUMBER = new Intl.NumberFormat('ro-RO');

/**
 * Desktop-only sortable manager table. Owns its own sort/expansion state so
 * the mobile card can stay independently expanded. Extracted from
 * `ASMSubtab.tsx` during the C8 frontend decomposition.
 */
export function ManagerDesktopTable({ rows, month }: { rows: ManagerOverview[]; month: string }) {
  const [expandedManager, setExpandedManager] = useState<string | null>(null);
  const [sortKey, setSortKey] = useState<ManagerSortKey>('manager');
  const [sortDirection, setSortDirection] = useState<ManagerSortDirection>('asc');
  const sortedRows = useMemo(
    () => rows.slice().sort((left, right) => compareManagerRows(left, right, sortKey, sortDirection)),
    [rows, sortDirection, sortKey],
  );
  const handleSort = (key: ManagerSortKey) => {
    setSortDirection((direction) =>
      sortKey === key ? (direction === 'asc' ? 'desc' : 'asc') : key === 'manager' ? 'asc' : 'desc',
    );
    setSortKey(key);
  };

  const header = (label: string, key: ManagerSortKey, align: 'left' | 'right' | 'center' = 'left') => (
    <SortableTableHeader
      label={label}
      active={sortKey === key}
      direction={sortDirection}
      onClick={() => handleSort(key)}
      align={align}
    />
  );

  return (
    <div className="hidden overflow-hidden rounded-2xl border border-slate-200 bg-white lg:block dark:border-slate-700 dark:bg-slate-900">
      <div className="max-h-[68vh] overflow-auto">
        <table className="w-full min-w-[960px] border-collapse text-[13px]">
          <thead className="sticky top-0 z-10 bg-slate-100 dark:bg-slate-800">
            <tr>
              {header('Manager', 'manager')}
              {header('Magazine', 'active_stores', 'right')}
              {header('Agenți', 'active_agents', 'right')}
              {header('Flux net', 'agent_delta', 'right')}
              {header('Acoperire echipă', 'staffing', 'right')}
              {header('Vizite', 'visits', 'right')}
              {header('Checklist', 'checklist', 'right')}
              {header('Stare', 'health')}
            </tr>
          </thead>
          <tbody>
            {sortedRows.map((row) => {
              const expanded = expandedManager === row.manager;
              const staffed = row.active_stores - row.stores_without_agents;
              const coverage = staffingCoverage(row);
              const health = healthInfo(row);
              return (
                <Fragment key={row.manager}>
                  <tr className="border-t border-slate-100 transition-colors hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-800/40">
                    <td className="px-2.5 py-2">
                      <button type="button" onClick={() => setExpandedManager(expanded ? null : row.manager)} className="flex w-full items-center gap-2 text-left font-bold text-slate-800 hover:text-indigo-600 dark:text-slate-100 dark:hover:text-indigo-300" aria-expanded={expanded}>
                        {expanded ? <ChevronUp className="h-4 w-4 shrink-0" /> : <ChevronDown className="h-4 w-4 shrink-0" />}
                        <span>{row.manager}</span>
                        {hasSalaryGrilaAccess(row.manager) && <WalletCards className="h-3.5 w-3.5 shrink-0 text-indigo-500" aria-label="Grilă salariu disponibilă" />}
                      </button>
                    </td>
                    <td className="px-2.5 py-2 text-right font-semibold tabular-nums">{NUMBER.format(row.active_stores)}</td>
                    <td className="px-2.5 py-2 text-right font-semibold tabular-nums">{NUMBER.format(row.active_agents)}</td>
                    <td className={cn('px-2.5 py-2 text-right font-bold tabular-nums', row.agent_delta < 0 ? 'text-rose-600' : row.agent_delta > 0 ? 'text-emerald-600' : 'text-slate-500')}>
                      {row.agent_delta > 0 ? '+' : ''}{row.agent_delta}
                    </td>
                    <td className="px-2.5 py-2 text-right">
                      <div className="font-semibold tabular-nums">{coverage === null ? '—' : `${Math.round(coverage)}%`}</div>
                      <div className="text-[10px] text-slate-400">{staffed}/{row.active_stores} magazine</div>
                    </td>
                    <td className="px-2.5 py-2 text-right">
                      {row.visits_available ? <><div className="font-semibold tabular-nums">{row.visit_coverage_pct}%</div><div className="text-[10px] text-slate-400">{row.visited_stores}/{row.active_stores}</div></> : <span className="text-xs font-semibold text-slate-400">Fără raportare</span>}
                    </td>
                    <td className="px-2.5 py-2 text-right font-semibold tabular-nums">{row.checklist_score === null ? '—' : `${row.checklist_score}%`}</td>
                    <td className="px-2.5 py-2"><span className={cn('inline-flex rounded-full px-2 py-1 text-xs font-semibold', TONE[health.tone].badge)}>{health.label}</span></td>
                  </tr>
                  {expanded && (
                    <tr className="border-t border-slate-100 bg-slate-50/70 dark:border-slate-800 dark:bg-slate-950/30">
                      <td colSpan={8} className="p-3">
                        <div className="space-y-3">
                          <p className="text-xs text-slate-500">{health.detail} {row.agents_added} intrări și {row.agents_left} ieșiri față de luna precedentă.</p>
                          {hasSalaryGrilaAccess(row.manager) && <AsmSalaryGrila asm={row.manager} defaultMonth={month} />}
                          <ManagerStorePortfolio row={row} />
                        </div>
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
