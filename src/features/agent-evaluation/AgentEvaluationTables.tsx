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

export function V2SortHeader({
  label,
  sortKey,
  align = 'left',
  currentKey,
  direction,
  onSort,
}: {
  label: string;
  sortKey: V2SortKey;
  align?: 'left' | 'right';
  currentKey: V2SortKey;
  direction: 'asc' | 'desc';
  onSort: (key: V2SortKey) => void;
}) {
  const active = currentKey === sortKey;
  return (
    <SortableTableHeader label={label} active={active} direction={direction} onClick={() => onSort(sortKey)} align={align} />
  );
}

export type V2SortKey =
  | 'agent'
  | 'total_sales'
  | 'total_score'
  | 'target_pct'
  | 'daily_vs_reference_pct'
  | 'bonuri_pct'
  | 'focus_pct'
  | 'premium_glass_pct'
  | 'value_reper'
  | 'trend_daily_pct'
  | 'eligibility_status';

const V2_NUMERIC_SORT_KEYS = new Set<V2SortKey>([
  'total_sales',
  'total_score',
  'target_pct',
  'daily_vs_reference_pct',
  'bonuri_pct',
  'focus_pct',
  'premium_glass_pct',
  'value_reper',
  'trend_daily_pct',
]);

export function getV2SortValue(row: AgentEvaluationV2Row, key: V2SortKey): string | number {
  if (key === 'agent') return `${row.agent} ${row.locatie}`.toLowerCase();
  if (key === 'target_pct') return row.target_pct ?? Number.NEGATIVE_INFINITY;
  const value = row[key];
  if (value === null || value === undefined) return Number.NEGATIVE_INFINITY;
  if (V2_NUMERIC_SORT_KEYS.has(key)) {
    const numeric = Number(value);
    return Number.isFinite(numeric) ? numeric : Number.NEGATIVE_INFINITY;
  }
  return String(value).toLowerCase();
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

export function ComponentScoreCell({
  value,
  score,
  weight,
  suffix = '%',
  sub,
}: {
  value: number | null;
  score: number | null;
  weight: number;
  suffix?: '%' | 'lei';
  sub?: string;
}) {
  return (
    <td className="px-2 py-2 text-right text-xs">
      <div className="font-medium text-slate-700 dark:text-slate-200">
        {suffix === 'lei' ? formatNumber(value, 0) : formatPct(value)}
      </div>
      {sub && <div className="text-[10px] text-slate-400">{sub}</div>}
      <div className={`text-[10px] font-semibold ${score === null ? 'text-slate-400' : score >= weight * 0.66 ? 'text-green-600 dark:text-green-400' : score > 0 ? 'text-amber-600 dark:text-amber-400' : 'text-red-600 dark:text-red-400'}`}>
        {score === null ? '-' : `${Number(score).toFixed(1)}/${weight}`}
      </div>
    </td>
  );
}

export function AgentV2Row({ row }: { row: AgentEvaluationV2Row }) {
  const weights = componentWeights(row);
  const targetValue = row.target_pct;
  const trendClass = row.trend_direction === 'up'
    ? 'text-green-600 dark:text-green-400'
    : row.trend_direction === 'down'
      ? 'text-red-600 dark:text-red-400'
      : 'text-slate-500 dark:text-slate-400';

  return (
    <tr className="border-b border-slate-100 dark:border-slate-800 hover:bg-slate-50 dark:hover:bg-slate-800/50">
      <td className="px-3 py-2 whitespace-nowrap text-xs font-medium text-slate-600 dark:text-slate-300">
        <MonthLabel month={row.month} />
      </td>
      <td className="px-2 py-2 min-w-[150px] max-w-[190px]">
        <div className="truncate text-xs font-semibold text-slate-800 dark:text-slate-100">{row.agent}</div>
        <div className="mt-0.5 flex items-center gap-1 min-w-0">
          <FirmBadge firma={row.firma} />
          <span className="truncate text-[10px] text-slate-400">{row.locatie}</span>
        </div>
      </td>
      <td className="px-2 py-2 text-right text-xs text-slate-600 dark:text-slate-300">
        <div className="font-semibold">{formatMoney(row.total_sales)}</div>
        <div className="text-[10px] text-slate-400">{row.working_days} zile · {row.receipt_count} bonuri</div>
      </td>
      <td className="px-2 py-2 text-right whitespace-nowrap">
        <span className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-bold tabular-nums ${score100Color(row.total_score, row.eligibility_status)}`}>
          {row.total_score === null ? '-' : `${Number(row.total_score).toFixed(1)}`}
        </span>
        <div className="text-[10px] text-slate-400 mt-0.5">{row.rating}</div>
      </td>
      <td className="px-2 py-2 text-left min-w-[145px]">
        <div className={`inline-flex rounded-full px-2 py-0.5 text-[10px] font-semibold ${row.eligibility_status === 'eligibil' ? 'bg-green-50 text-green-700 dark:bg-green-950/40 dark:text-green-300' : 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300'}`}>
          {row.eligibility_status}
        </div>
        <div className="mt-1 flex max-w-[155px] flex-wrap justify-start gap-1">
          {row.confidence_flags.slice(0, 3).map((flag) => (
            <span key={flag} className="rounded-full bg-slate-100 px-1.5 py-0.5 text-[9px] text-slate-500 dark:bg-slate-800 dark:text-slate-400">
              {flagLabel(flag)}
            </span>
          ))}
        </div>
      </td>
      <ComponentScoreCell
        value={targetValue}
        score={row.target_score}
        weight={weights.target}
        sub={`${targetSourceLabel(row.target_source)} · punctaj lunar`}
      />
      <ComponentScoreCell
        value={row.daily_vs_reference_pct}
        score={row.daily_score}
        weight={weights.daily}
        sub={`${formatNumber(row.daily_average, 0)} lei/zi vs ${referenceLabel(row.daily_reference_type)}`}
      />
      <ComponentScoreCell value={row.bonuri_pct} score={row.bonuri_score} weight={weights.bonuri} />
      <ComponentScoreCell value={row.focus_pct} score={row.focus_score} weight={weights.focus} />
      <ComponentScoreCell
        value={row.premium_glass_pct}
        score={row.premium_glass_score}
        weight={weights.premium}
        sub={`${row.premium_glass_qty}/${row.glass_qty}`}
      />
      <ComponentScoreCell value={row.value_reper} score={row.value_reper_score} weight={weights.value} suffix="lei" />
      <td className="px-2 py-2 text-right text-xs">
        <div className={`font-semibold ${trendClass}`}>{row.trend_daily_pct === null ? '-' : `${Number(row.trend_daily_pct).toFixed(1)}%`}</div>
        <div className="text-[10px] text-slate-400">vs 3 luni</div>
      </td>
    </tr>
  );
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

