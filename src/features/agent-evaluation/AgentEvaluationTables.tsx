import type { AgentEvaluationRow, AgentEvaluationV2Row } from '../../api/agents';
import { SortableTableHeader } from '../../components/common/TableHeader';
import { FirmBadge, formatMoney, formatNumber, formatPct, MetricCell, MonthLabel, pointColor, scoreColor } from './AgentEvaluationControls';

export function AgentRow({ row }: { row: AgentEvaluationRow }) {
  return (
    <tr className="border-b border-slate-100 dark:border-slate-800 hover:bg-slate-50 dark:hover:bg-slate-800/50">
      <td className="px-3 py-2 whitespace-nowrap text-xs font-medium text-slate-600 dark:text-slate-300">
        <MonthLabel month={row.month} />
      </td>
      <td className="px-2 py-2 min-w-[135px] max-w-[170px]">
        <div className="truncate text-xs font-semibold text-slate-800 dark:text-slate-100">{row.agent}</div>
        <div className="mt-0.5 flex items-center gap-1 min-w-0">
          <FirmBadge firma={row.firma} />
          <span className="truncate text-[10px] text-slate-400">{row.locatie}</span>
        </div>
      </td>
      <td className="px-2 py-2 text-right text-xs text-slate-600 dark:text-slate-300">
        <div className="font-semibold">{formatMoney(row.total_sales)}</div>
        <div className="text-[10px] text-slate-400">{row.working_days} zile</div>
      </td>
      <td className="px-2 py-2 text-right text-xs text-slate-600 dark:text-slate-300">
        <div>{formatMoney(row.target_value)}</div>
        <div className="text-[10px] text-slate-400">loc. {formatMoney(row.store_target)}</div>
      </td>
      <td className="px-2 py-2"><MetricCell value={row.target_pct} points={row.target_points} /></td>
      <td className="px-2 py-2 text-right text-xs">
        <div className="font-medium text-slate-700 dark:text-slate-200">{formatNumber(row.daily_average, 0)}</div>
        <div className={`text-[10px] font-semibold ${pointColor(row.daily_points)}`}>{row.daily_points}/3</div>
      </td>
      <td className="px-2 py-2"><MetricCell value={row.value_reper} points={row.value_reper_points} suffix="lei" /></td>
      <td className="px-2 py-2"><MetricCell value={row.bonuri_pct} points={row.bonuri_points} /></td>
      <td className="px-2 py-2"><MetricCell value={row.focus_pct} points={row.focus_points} /></td>
      <td className="px-2 py-2 text-right text-xs">
        <div className="font-medium text-slate-700 dark:text-slate-200">{formatPct(row.premium_glass_pct)}</div>
        <div className="text-[10px] text-slate-400">{row.premium_glass_qty}/{row.glass_qty}</div>
        <div className={`text-[10px] font-semibold ${pointColor(row.premium_glass_points)}`}>{row.premium_glass_points}/3</div>
      </td>
      <td className="px-2 py-2 text-right whitespace-nowrap">
        <span className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-bold tabular-nums ${scoreColor(row.total_points)}`}>
          {row.total_points}/18
        </span>
        <div className="text-[10px] text-slate-400 mt-0.5">{row.qualifier}</div>
      </td>
    </tr>
  );
}

export type SortKey =
  | 'month'
  | 'agent'
  | 'total_sales'
  | 'target_value'
  | 'target_pct'
  | 'daily_average'
  | 'value_reper'
  | 'bonuri_pct'
  | 'focus_pct'
  | 'premium_glass_pct'
  | 'total_points';

const NUMERIC_SORT_KEYS = new Set<SortKey>([
  'total_sales',
  'target_value',
  'target_pct',
  'daily_average',
  'value_reper',
  'bonuri_pct',
  'focus_pct',
  'premium_glass_pct',
  'total_points',
]);

export function getSortValue(row: AgentEvaluationRow, key: SortKey): string | number {
  if (key === 'agent') return `${row.agent} ${row.locatie}`.toLowerCase();
  const value = row[key];
  if (value === null || value === undefined) return Number.NEGATIVE_INFINITY;
  if (NUMERIC_SORT_KEYS.has(key)) {
    const numeric = Number(value);
    return Number.isFinite(numeric) ? numeric : Number.NEGATIVE_INFINITY;
  }
  return String(value).toLowerCase();
}

export function SortHeader({
  label,
  sortKey,
  align = 'left',
  currentKey,
  direction,
  onSort,
}: {
  label: string;
  sortKey: SortKey;
  align?: 'left' | 'right';
  currentKey: SortKey;
  direction: 'asc' | 'desc';
  onSort: (key: SortKey) => void;
}) {
  const active = currentKey === sortKey;
  return (
    <SortableTableHeader label={label} active={active} direction={direction} onClick={() => onSort(sortKey)} align={align} />
  );
}

export function score100Color(score: number | null | undefined, status?: string) {
  if (status === 'insuficient') return 'bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-300';
  if (score === null || score === undefined) return 'bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-300';
  if (score >= 75) return 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300';
  if (score >= 50) return 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300';
  return 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300';
}

export function componentWeights(row: AgentEvaluationV2Row) {
  const isSinglePartialMonth = row.is_partial && row.period_month_count === 1;
  return isSinglePartialMonth
    ? { target: 10, daily: 25, bonuri: 20, focus: 20, premium: 10, value: 15 }
    : { target: 25, daily: 20, bonuri: 15, focus: 15, premium: 10, value: 15 };
}

export function flagLabel(flag: string) {
  const labels: Record<string, string> = {
    luna_partiala: 'lună parțială',
    target_partial_din_grile: 'target parțial',
    target_alocat_din_magazin: 'target pe zile',
    reper_istoric_locatie: 'reper locație',
    reper_media_manager: 'reper manager',
    reper_none: 'fără reper',
    folii_volum_mic: 'folii volum mic',
    volum_insuficient: 'volum insuficient',
  };
  return labels[flag] ?? flag.replaceAll('_', ' ');
}

export function referenceLabel(value: string) {
  if (value === 'colegi') return 'colegi';
  if (value === 'istoric_locatie') return 'locație';
  if (value === 'media_manager') return 'manager';
  return 'fără reper';
}

export function targetSourceLabel(value: string) {
  if (value === 'agent_target') return 'target agent';
  if (value === 'partial_agent_target') return 'target mixt';
  return 'target pe zile';
}

export function AgentV2MobileCard({ row }: { row: AgentEvaluationV2Row }) {
  const indicators = [
    ['Target', row.target_pct, row.target_score],
    ['Productivitate', row.daily_vs_reference_pct, row.daily_score],
    ['Bon2Acc', row.bonuri_pct, row.bonuri_score],
    ['Focus', row.focus_pct, row.focus_score],
    ['Folii premium', row.premium_glass_pct, row.premium_glass_score],
  ] as const;
  return (
    <article className="rounded-2xl border border-slate-200 bg-white p-3 shadow-sm dark:border-slate-700 dark:bg-slate-900 lg:hidden">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate text-sm font-bold text-slate-900 dark:text-slate-100">{row.agent}</p>
          <p className="mt-0.5 truncate text-xs text-slate-500">{row.locatie} · <MonthLabel month={row.month} /></p>
          <p className="mt-1 text-xs font-semibold text-slate-600 dark:text-slate-300">{formatMoney(row.total_sales)} RON · {row.working_days} zile</p>
        </div>
        <div className="text-right">
          <span className={`inline-flex min-w-14 justify-center rounded-xl px-2 py-1.5 text-base font-black ${score100Color(row.total_score, row.eligibility_status)}`}>
            {row.total_score === null ? '—' : Number(row.total_score).toFixed(1)}
          </span>
          <p className="mt-1 text-[10px] font-semibold text-slate-500">{row.rating}</p>
        </div>
      </div>
      <div className="mt-3 grid grid-cols-2 gap-2">
        {indicators.map(([label, value, score]) => (
          <div key={label} className="rounded-xl bg-slate-50 p-2 dark:bg-slate-800/70">
            <p className="text-[10px] font-bold uppercase tracking-wide text-slate-400">{label}</p>
            <div className="mt-0.5 flex items-baseline justify-between gap-2">
              <span className="text-sm font-bold text-slate-800 dark:text-slate-100">{formatPct(value)}</span>
              <span className="text-[10px] font-semibold text-indigo-600 dark:text-indigo-300">{score === null ? '—' : Number(score).toFixed(1)}p</span>
            </div>
          </div>
        ))}
        <div className="rounded-xl bg-slate-50 p-2 dark:bg-slate-800/70">
          <p className="text-[10px] font-bold uppercase tracking-wide text-slate-400">Valoare reper</p>
          <p className="mt-0.5 text-sm font-bold text-slate-800 dark:text-slate-100">{formatNumber(row.value_reper, 0)} RON</p>
        </div>
      </div>
      {row.confidence_flags.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {row.confidence_flags.slice(0, 3).map((flag) => <span key={flag} className="rounded-full bg-slate-100 px-2 py-1 text-[10px] text-slate-500 dark:bg-slate-800">{flagLabel(flag)}</span>)}
        </div>
      )}
    </article>
  );
}

export function AgentLegacyMobileCard({ row }: { row: AgentEvaluationRow }) {
  return (
    <article className="rounded-2xl border border-slate-200 bg-white p-3 shadow-sm dark:border-slate-700 dark:bg-slate-900 lg:hidden">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0"><p className="truncate text-sm font-bold">{row.agent}</p><p className="truncate text-xs text-slate-500">{row.locatie} · <MonthLabel month={row.month} /></p></div>
        <span className={`rounded-xl px-2.5 py-1.5 text-sm font-black ${scoreColor(row.total_points)}`}>{row.total_points}/18</span>
      </div>
      <div className="mt-3 grid grid-cols-3 gap-2 text-center">
        <div><p className="text-[10px] text-slate-400">Vânzare</p><p className="text-xs font-bold">{formatMoney(row.total_sales)}</p></div>
        <div><p className="text-[10px] text-slate-400">Target</p><p className="text-xs font-bold">{formatPct(row.target_pct)}</p></div>
        <div><p className="text-[10px] text-slate-400">Focus</p><p className="text-xs font-bold">{formatPct(row.focus_pct)}</p></div>
      </div>
    </article>
  );
}
