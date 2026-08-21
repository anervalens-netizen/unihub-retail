import { useState, type ReactNode } from 'react';
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  ClipboardCheck,
  MapPinned,
  Store,
  UserMinus,
  UserPlus,
  Users,
  WalletCards,
} from 'lucide-react';

import type { ManagerOverview } from '../../api/hr';
import { cn } from '../../lib/utils';
import { AsmSalaryGrila } from '../AsmSalaryGrila';
import {
  TONE,
  hasSalaryGrilaAccess,
  healthInfo,
  metricTone,
  staffingCoverage,
  type Tone,
} from './managerOverviewModel';
import { ManagerStorePortfolio } from './ManagerStorePortfolio';

const NUMBER = new Intl.NumberFormat('ro-RO');

function PortfolioStat({
  icon,
  label,
  value,
  hint,
  valueClassName,
}: {
  icon: ReactNode;
  label: string;
  value: string;
  hint?: string;
  valueClassName?: string;
}) {
  return (
    <div className="rounded-xl bg-white/80 px-3 py-2.5 dark:bg-slate-900/50">
      <div className="flex items-center gap-1.5 text-[11px] font-semibold text-slate-500 dark:text-slate-400">
        {icon}
        {label}
      </div>
      <div className={cn('mt-1 text-lg font-bold tabular-nums text-slate-800 dark:text-slate-100', valueClassName)}>
        {value}
      </div>
      {hint && <div className="text-[10px] text-slate-500 dark:text-slate-400">{hint}</div>}
    </div>
  );
}

function HealthMetric({
  icon,
  label,
  value,
  display,
  tone,
}: {
  icon: ReactNode;
  label: string;
  value: number | null;
  display: string;
  tone: Tone;
}) {
  const width = value === null ? 0 : Math.max(0, Math.min(value, 100));
  return (
    <div className="min-w-0">
      <div className="mb-1 flex items-center justify-between gap-2 text-[11px]">
        <span className="inline-flex min-w-0 items-center gap-1.5 truncate font-medium text-slate-500 dark:text-slate-400">
          {icon}
          {label}
        </span>
        <strong className="flex-shrink-0 tabular-nums text-slate-700 dark:text-slate-200">{display}</strong>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700">
        <div className={cn('h-full rounded-full', TONE[tone].bar)} style={{ width: `${width}%` }} />
      </div>
    </div>
  );
}

/**
 * Mobile-only manager card. Owns its own expansion state so a single
 * desktop interaction does not collapse the mobile detail. Extracted from
 * `ASMSubtab.tsx` during the C8 frontend decomposition.
 */
export function ManagerMobileCard({ row, month }: { row: ManagerOverview; month: string }) {
  const [open, setOpen] = useState(false);
  const health = healthInfo(row);
  const staffed = row.active_stores - row.stores_without_agents;
  const coverage = staffingCoverage(row);
  const regionalLabel = row.regional && row.regional !== row.manager ? row.regional : null;
  return (
    <article className="overflow-hidden rounded-2xl border border-slate-200 bg-slate-50/70 lg:hidden dark:border-slate-700 dark:bg-slate-800/40">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="w-full px-4 py-3 text-left transition-colors hover:bg-slate-100 dark:hover:bg-slate-800"
        aria-expanded={open}
      >
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex min-w-0 items-start gap-2.5">
            <div className="mt-0.5 rounded-xl bg-indigo-100 p-2 text-indigo-600 dark:bg-indigo-900/40 dark:text-indigo-300">
              <Users className="h-4 w-4" />
            </div>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="truncate text-base font-bold text-slate-900 dark:text-slate-100">{row.manager}</h3>
                {hasSalaryGrilaAccess(row.manager) && (
                  <span className="inline-flex items-center gap-1 rounded-full bg-indigo-100 px-2 py-0.5 text-[10px] font-semibold text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-300">
                    <WalletCards className="h-3 w-3" /> Grilă salariu
                  </span>
                )}
              </div>
              <p className="mt-0.5 text-xs text-slate-500">
                {regionalLabel ? `Regional: ${regionalLabel} · ` : ''}{row.active_stores} magazine · {row.active_agents} agenți
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span className={cn('rounded-full px-2.5 py-1 text-xs font-semibold', TONE[health.tone].badge)}>
              {health.label}
            </span>
            {open ? <ChevronUp className="h-4 w-4 text-slate-400" /> : <ChevronDown className="h-4 w-4 text-slate-400" />}
          </div>
        </div>
      </button>
      <div className="border-t border-slate-200 px-4 py-3 dark:border-slate-700">
        <div className="grid grid-cols-2 gap-2">
          <PortfolioStat icon={<Store className="h-3.5 w-3.5" />} label="Magazine" value={NUMBER.format(row.active_stores)} hint={`${staffed} cu agenți raportați`} />
          <PortfolioStat icon={<Users className="h-3.5 w-3.5" />} label="Agenți activi" value={NUMBER.format(row.active_agents)} hint={`${row.agents_per_store.toLocaleString('ro-RO')} / magazin`} />
          <PortfolioStat
            icon={<UserPlus className="h-3.5 w-3.5" />}
            label="Flux net"
            value={`${row.agent_delta > 0 ? '+' : ''}${row.agent_delta}`}
            hint={`${row.agents_added} intrări · ${row.agents_left} ieșiri`}
            valueClassName={row.agent_delta < 0 ? 'text-rose-600 dark:text-rose-400' : 'text-emerald-600 dark:text-emerald-400'}
          />
          <PortfolioStat
            icon={<UserMinus className="h-3.5 w-3.5" />}
            label="Acoperire magazine"
            value={coverage === null ? '—' : `${Math.round(coverage)}%`}
            hint={`${staffed}/${row.active_stores} cu agenți`}
            valueClassName={coverage !== null && coverage < 100 ? 'text-amber-600 dark:text-amber-400' : undefined}
          />
        </div>
        {open && <div className="mt-3 grid gap-x-5 gap-y-3 rounded-xl bg-white px-3 py-3 sm:grid-cols-2 dark:bg-slate-900/60">
          <HealthMetric
            icon={<Users className="h-3.5 w-3.5" />}
            label="Acoperire cu agenți"
            value={coverage}
            display={`${staffed}/${row.active_stores}`}
            tone={metricTone(coverage, 100, 90)}
          />
          <HealthMetric
            icon={<MapPinned className="h-3.5 w-3.5" />}
            label="Acoperire vizite"
            value={row.visit_coverage_pct}
            display={row.visits_available ? `${row.visited_stores}/${row.active_stores}` : 'Fără date'}
            tone={metricTone(row.visit_coverage_pct, 90, 70)}
          />
          <HealthMetric
            icon={<Activity className="h-3.5 w-3.5" />}
            label="Completare vizite"
            value={row.avg_visit_completion}
            display={row.avg_visit_completion === null ? 'Fără date' : `${row.avg_visit_completion}%`}
            tone={metricTone(row.avg_visit_completion, 90, 75)}
          />
          <HealthMetric
            icon={<ClipboardCheck className="h-3.5 w-3.5" />}
            label="Checklist"
            value={row.checklist_score}
            display={row.checklist_score === null ? 'Fără date' : `${row.checklist_score}%`}
            tone={metricTone(row.checklist_score, 95, 85)}
          />
        </div>}
        <div className="mt-2 flex items-start gap-1.5 text-[11px] text-slate-500 dark:text-slate-400">
          {health.tone === 'emerald'
            ? <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 flex-shrink-0 text-emerald-500" />
            : <AlertTriangle className={cn('mt-0.5 h-3.5 w-3.5 flex-shrink-0', health.tone === 'rose' ? 'text-rose-500' : 'text-amber-500')} />}
          <span>{health.detail}</span>
        </div>
      </div>
      {open && (
        <div className="space-y-3 border-t border-slate-200 bg-white px-4 py-4 dark:border-slate-700 dark:bg-slate-900">
          {hasSalaryGrilaAccess(row.manager) && (
            <AsmSalaryGrila asm={row.manager} defaultMonth={month} />
          )}
          <div>
            <div className="mb-2 flex flex-wrap items-end justify-between gap-2">
              <div>
                <h4 className="text-sm font-bold text-slate-800 dark:text-slate-100">Portofoliu magazine</h4>
                <p className="text-[11px] text-slate-500">Acoperirea cu agenți comparată cu luna precedentă; fără scorare de vânzări.</p>
              </div>
              <span className="text-xs text-slate-500 dark:text-slate-400">{row.stores.length} magazine</span>
            </div>
            <ManagerStorePortfolio row={row} />
          </div>
        </div>
      )}
    </article>
  );
}
