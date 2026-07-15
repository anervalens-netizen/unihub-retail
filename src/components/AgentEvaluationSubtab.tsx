import { type ReactNode, useCallback, useEffect, useMemo, useState } from 'react';
import { ChevronDown, ChevronUp, RefreshCw } from 'lucide-react';
import {
  fetchAgentEvaluation,
  fetchAgentEvaluationV2,
  type AgentEvaluationOption,
  type AgentEvaluationRow,
  type AgentEvaluationResponse,
  type AgentEvaluationV2Row,
  type AgentEvaluationV2Response,
} from '../api/agents';
import { ExportTableButton } from './ExportTableButton';
import { formatMonthLabel } from '../lib/dates';

function formatMoney(value: number | null | undefined) {
  if (value === null || value === undefined) return '-';
  return new Intl.NumberFormat('ro-RO', { maximumFractionDigits: 0 }).format(Number(value));
}

function formatPct(value: number | null | undefined) {
  if (value === null || value === undefined) return '-';
  return `${Number(value).toFixed(1)}%`;
}

function formatNumber(value: number | null | undefined, digits = 0) {
  if (value === null || value === undefined) return '-';
  return new Intl.NumberFormat('ro-RO', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(Number(value));
}

function scoreColor(points: number) {
  if (points >= 16) return 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300';
  if (points >= 10) return 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300';
  return 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300';
}

function pointColor(points: number) {
  if (points === 3) return 'text-green-600 dark:text-green-400';
  if (points >= 1) return 'text-amber-600 dark:text-amber-400';
  return 'text-red-600 dark:text-red-400';
}

function MonthLabel({ month }: { month: string }) {
  if (month === 'custom') return <>Selectate</>;
  const formatShort = (value: string) => {
    const formatted = formatMonthLabel(value, { year: 'short' });
    return formatted === value ? value : formatted;
  };
  if (month.includes('..')) {
    const [start, end] = month.split('..');
    return <>{formatShort(start)} - {end.includes('-') ? formatShort(end) : end}</>;
  }
  return <>{formatShort(month)}</>;
}

function MetricCell({ value, points, suffix = '%' }: { value: number | null; points: number; suffix?: string }) {
  return (
    <div className="text-right">
      <div className="font-medium text-slate-700 dark:text-slate-200">
        {suffix === 'lei' ? formatNumber(value, 0) : formatPct(value)}
      </div>
      <div className={`text-[10px] font-semibold ${pointColor(points)}`}>{points}/3</div>
    </div>
  );
}

function MechanismCard() {
  const [showPoints, setShowPoints] = useState(false);
  const items = [
    {
      label: 'Bază calcul',
      text: 'Lunile bifate se agregă pe agent. Fără bifă = din ian. 2025. Sunt incluși agenții activi curent, pe alocarea curentă.',
    },
    {
      label: 'Scor',
      text: 'Target agent = target locație / zile locație * zile agent. Scorul are 6 segmente de 0-3p; Folii Premium se raportează la foliile eligibile.',
    },
  ];
  const pointRules = [
    { label: 'Target', rules: ['3p >=100%', '2p 90-99%', '1p 80-89%', '0p <80%'] },
    { label: 'Medie zilnică', rules: ['3p peste media colegilor din locație', '0p sub medie sau fără comparație'] },
    { label: 'Valoare reper', rules: ['3p >=100 lei', '2p 95-99 lei', '1p 90-94 lei', '0p <90 lei'] },
    { label: '% Bonuri', rules: ['3p >=35%', '2p 30-34%', '1p 25-29%', '0p <25%'] },
    { label: 'Focus', rules: ['3p >=8%', '2p 7-7,9%', '1p 6-6,9%', '0p <6%'] },
    { label: 'Folii Premium', rules: ['3p >=50%', '2p 40-49%', '1p 30-39%', '0p <30%'] },
  ];

  return (
    <div className="rounded-xl border border-indigo-200 dark:border-indigo-900/50 bg-indigo-50/60 dark:bg-indigo-950/20 p-2.5 sm:p-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h4 className="text-sm font-bold text-slate-900 dark:text-slate-100">Mecanism analiză agenți</h4>
          <p className="mt-0.5 text-[11px] leading-4 text-slate-500 dark:text-slate-400">
            Maxim 18 puncte. Evaluare pe 6 segmente comerciale, fiecare cu 0-3 puncte.
          </p>
        </div>
        <span className="shrink-0 rounded-full bg-white/80 dark:bg-slate-900/70 px-2.5 py-1 text-xs font-bold text-indigo-600 dark:text-indigo-300">
          max 18 pct
        </span>
      </div>
      <div className="mt-2 grid grid-cols-1 lg:grid-cols-2 gap-1.5 sm:gap-2">
        {items.map((item) => (
          <div key={item.label} className="rounded-lg bg-white/80 dark:bg-slate-900/50 border border-indigo-100 dark:border-indigo-900/40 px-2.5 py-1.5 sm:px-3 sm:py-2">
            <div className="text-[11px] font-bold uppercase tracking-wider text-indigo-600 dark:text-indigo-300">{item.label}</div>
            <p className="mt-0.5 text-[11px] leading-4 text-slate-600 dark:text-slate-300">{item.text}</p>
          </div>
        ))}
      </div>
      <div className="mt-2 rounded-lg border border-indigo-100 dark:border-indigo-900/40 bg-white/80 dark:bg-slate-900/50">
        <button
          onClick={() => setShowPoints((value) => !value)}
          className="w-full flex items-center justify-between px-3 py-2 text-left"
        >
          <span className="text-[11px] font-bold uppercase tracking-wider text-indigo-600 dark:text-indigo-300">Alocare puncte</span>
          {showPoints ? <ChevronUp size={14} className="text-indigo-500" /> : <ChevronDown size={14} className="text-indigo-500" />}
        </button>
        {showPoints && (
          <div className="border-t border-indigo-100 dark:border-indigo-900/40 px-3 pb-3 pt-2">
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-2">
              {pointRules.map((rule) => (
                <div key={rule.label} className="rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50/80 dark:bg-slate-800/50 p-2">
                  <div className="text-[11px] font-semibold text-slate-800 dark:text-slate-100">{rule.label}</div>
                  <div className="mt-1 flex flex-wrap gap-x-2 gap-y-1">
                    {rule.rules.map((text) => (
                      <span key={text} className="text-[10px] text-slate-500 dark:text-slate-400">{text}</span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function FirmBadge({ firma, size = 'sm' }: { firma: string; size?: 'sm' | 'md' }) {
  const value = firma.toLowerCase();
  const isMobiup = value.includes('mobiup');
  const isMobicell = value.includes('mobicell');
  const sizeClass = size === 'md' ? 'h-7 w-7 text-sm' : 'h-4 w-4 text-[10px]';
  return (
    <span
      title={firma}
      className={`inline-flex ${sizeClass} shrink-0 items-center justify-center rounded-full font-black text-white ${
        isMobiup ? 'bg-red-600' : isMobicell ? 'bg-blue-600' : 'bg-slate-500'
      }`}
    >
      M
    </span>
  );
}

function CompactSummary({
  rows,
  summary,
  children,
}: {
  rows: AgentEvaluationRow[];
  summary: { agents: number; avgPoints: number; totalSales: number; premiumRows: number };
  children?: ReactNode;
}) {
  return (
    <div className="rounded-xl border border-slate-200 dark:border-slate-700 bg-white/80 dark:bg-slate-900/50 p-2.5">
      <div className="grid grid-cols-4 gap-2">
        {[
          { label: 'Agenți', value: String(summary.agents), sub: `${rows.length} rânduri` },
          { label: 'Punctaj', value: summary.avgPoints.toFixed(1), sub: 'din 18 pct' },
          { label: 'Vânzare', value: formatMoney(summary.totalSales), sub: 'total filtrat' },
          { label: 'Folii', value: String(summary.premiumRows), sub: 'cu 2+ pct' },
        ].map((item) => (
          <div key={item.label} className="min-w-0">
            <div className="text-[10px] uppercase tracking-wider font-bold text-slate-400 truncate">{item.label}</div>
            <div className="text-sm sm:text-base font-bold text-slate-900 dark:text-slate-100 tabular-nums truncate">{item.value}</div>
            <div className="hidden sm:block text-[10px] text-slate-500 dark:text-slate-400 truncate">{item.sub}</div>
          </div>
        ))}
      </div>
      {children && (
        <div className="mt-2 border-t border-slate-100 pt-2 dark:border-slate-800">
          {children}
        </div>
      )}
    </div>
  );
}

function MonthDropdown({
  months,
  selectedMonths,
  onToggle,
  onClear,
}: {
  months: { value: string; label: string }[];
  selectedMonths: string[];
  onToggle: (value: string) => void;
  onClear: () => void;
}) {
  const [open, setOpen] = useState(false);
  const label = selectedMonths.length ? `${selectedMonths.length} luni` : 'Toate lunile';

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((value) => !value)}
        className="h-9 w-full rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-left text-xs text-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 flex items-center justify-between gap-2"
      >
        <span className="truncate">{label}</span>
        {open ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
      </button>
      {open && (
        <div className="absolute left-0 top-full z-30 mt-1 w-56 rounded-xl border border-slate-200 bg-white p-2 shadow-lg dark:border-slate-700 dark:bg-slate-900">
          <button
            onClick={onClear}
            className="mb-1 w-full rounded-lg px-2 py-1.5 text-left text-xs font-medium text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
          >
            Toate lunile
          </button>
          <div className="max-h-52 overflow-y-auto">
            {months.map((option) => (
              <label key={option.value} className="flex items-center gap-2 rounded-lg px-2 py-1.5 text-xs text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800">
                <input
                  type="checkbox"
                  checked={selectedMonths.includes(option.value)}
                  onChange={() => onToggle(option.value)}
                  className="h-3.5 w-3.5 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                />
                <MonthLabel month={option.value} />
              </label>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function FirmSelector({
  options,
  selected,
  onChange,
}: {
  options: AgentEvaluationOption[];
  selected: string;
  onChange: (value: string) => void;
}) {
  const visibleOptions = options
    .filter((option) => /mobiup|mobicell/i.test(`${option.value} ${option.label}`))
    .sort((a, b) => {
      const aMobiup = `${a.value} ${a.label}`.toLowerCase().includes('mobiup') ? 0 : 1;
      const bMobiup = `${b.value} ${b.label}`.toLowerCase().includes('mobiup') ? 0 : 1;
      return aMobiup - bMobiup || a.label.localeCompare(b.label, 'ro');
    });

  return (
    <div className="inline-flex h-9 w-[78px] items-center justify-center gap-1 rounded-lg border border-slate-200 bg-white p-1 dark:border-slate-700 dark:bg-slate-800">
      {visibleOptions.map((option) => {
        const active = selected === option.value;
        return (
          <button
            key={option.value}
            type="button"
            onClick={() => onChange(active ? '' : option.value)}
            className={`rounded-md p-0.5 transition ${
              active
                ? 'bg-indigo-100 ring-2 ring-indigo-500 dark:bg-indigo-950/60 dark:ring-indigo-400'
                : 'hover:bg-slate-100 dark:hover:bg-slate-700'
            }`}
            title={option.label}
            aria-label={option.label}
          >
            <FirmBadge firma={option.label} size="md" />
          </button>
        );
      })}
    </div>
  );
}

function StoreDropdown({
  stores,
  selectedStores,
  onToggle,
  onClear,
}: {
  stores: AgentEvaluationOption[];
  selectedStores: string[];
  onToggle: (value: string) => void;
  onClear: () => void;
}) {
  const [open, setOpen] = useState(false);
  const label = selectedStores.length ? `${selectedStores.length} magazine` : 'Toate magazinele';

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((value) => !value)}
        className="h-9 w-full rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-left text-xs text-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 flex items-center justify-between gap-2"
      >
        <span className="truncate">{label}</span>
        {open ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
      </button>
      {open && (
        <div className="absolute left-0 top-full z-30 mt-1 w-full min-w-72 rounded-xl border border-slate-200 bg-white p-2 shadow-lg dark:border-slate-700 dark:bg-slate-900">
          <button
            onClick={onClear}
            className="mb-1 w-full rounded-lg px-2 py-1.5 text-left text-xs font-medium text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
          >
            Toate magazinele
          </button>
          <div className="max-h-64 overflow-y-auto">
            {stores.map((option) => (
              <label key={option.value} className="flex items-center gap-2 rounded-lg px-2 py-1.5 text-xs text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800">
                <input
                  type="checkbox"
                  checked={selectedStores.includes(option.value)}
                  onChange={() => onToggle(option.value)}
                  className="h-3.5 w-3.5 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                />
                <span className="truncate">{option.label}</span>
              </label>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function AgentRow({ row }: { row: AgentEvaluationRow }) {
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

type SortKey =
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

function getSortValue(row: AgentEvaluationRow, key: SortKey): string | number {
  if (key === 'agent') return `${row.agent} ${row.locatie}`.toLowerCase();
  const value = row[key];
  if (value === null || value === undefined) return Number.NEGATIVE_INFINITY;
  if (NUMERIC_SORT_KEYS.has(key)) {
    const numeric = Number(value);
    return Number.isFinite(numeric) ? numeric : Number.NEGATIVE_INFINITY;
  }
  return String(value).toLowerCase();
}

function SortHeader({
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
    <th className={`px-2 py-2 ${align === 'right' ? 'text-right' : ''}`}>
      <button
        onClick={() => onSort(sortKey)}
        className={`inline-flex items-center gap-1 ${align === 'right' ? 'justify-end' : ''} w-full hover:text-slate-700 dark:hover:text-slate-200`}
      >
        <span>{label}</span>
        {active ? (
          direction === 'asc' ? <ChevronUp size={11} /> : <ChevronDown size={11} />
        ) : (
          <span className="w-[11px]" />
        )}
      </button>
    </th>
  );
}

function V2SortHeader({
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
    <th className={`px-2 py-2 ${align === 'right' ? 'text-right' : ''}`}>
      <button
        onClick={() => onSort(sortKey)}
        className={`inline-flex items-center gap-1 ${align === 'right' ? 'justify-end' : ''} w-full hover:text-slate-700 dark:hover:text-slate-200`}
      >
        <span>{label}</span>
        {active ? (
          direction === 'asc' ? <ChevronUp size={11} /> : <ChevronDown size={11} />
        ) : (
          <span className="w-[11px]" />
        )}
      </button>
    </th>
  );
}

type V2SortKey =
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

function getV2SortValue(row: AgentEvaluationV2Row, key: V2SortKey): string | number {
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

function score100Color(score: number | null | undefined, status?: string) {
  if (status === 'insuficient') return 'bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-300';
  if (score === null || score === undefined) return 'bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-300';
  if (score >= 75) return 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300';
  if (score >= 50) return 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300';
  return 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300';
}

function componentWeights(row: AgentEvaluationV2Row) {
  const isSinglePartialMonth = row.is_partial && row.period_month_count === 1;
  return isSinglePartialMonth
    ? { target: 10, daily: 25, bonuri: 20, focus: 20, premium: 10, value: 15 }
    : { target: 25, daily: 20, bonuri: 15, focus: 15, premium: 10, value: 15 };
}

function flagLabel(flag: string) {
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

function referenceLabel(value: string) {
  if (value === 'colegi') return 'colegi';
  if (value === 'istoric_locatie') return 'locație';
  if (value === 'media_manager') return 'manager';
  return 'fără reper';
}

function targetSourceLabel(value: string) {
  if (value === 'agent_target') return 'target agent';
  if (value === 'partial_agent_target') return 'target mixt';
  return 'target pe zile';
}

function ComponentScoreCell({
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

function AgentV2Row({ row }: { row: AgentEvaluationV2Row }) {
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

function AgentV2MobileCard({ row }: { row: AgentEvaluationV2Row }) {
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

function AgentLegacyMobileCard({ row }: { row: AgentEvaluationRow }) {
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

function NewEvaluationSubsection({
  rows,
  sortKey,
  sortDirection,
  onSort,
}: {
  rows: AgentEvaluationV2Row[];
  sortKey: V2SortKey;
  sortDirection: 'asc' | 'desc';
  onSort: (key: V2SortKey) => void;
}) {
  const [showMechanism, setShowMechanism] = useState(false);
  const summary = useMemo(() => {
    const scored = rows.filter((row) => row.total_score !== null);
    const agents = new Set(rows.map((row) => row.agent)).size;
    const avgScore = scored.length ? scored.reduce((sum, row) => sum + Number(row.total_score), 0) / scored.length : 0;
    const eligible = rows.filter((row) => row.eligibility_status === 'eligibil').length;
    const partial = rows.filter((row) => row.is_partial).length;
    return { agents, avgScore, eligible, partial };
  }, [rows]);

  return (
    <div className="space-y-3">
      <div className="rounded-xl border border-indigo-200 dark:border-indigo-900/50 bg-indigo-50/60 dark:bg-indigo-950/20">
        <button
          type="button"
          onClick={() => setShowMechanism((value) => !value)}
          className="flex w-full items-center justify-between gap-3 px-3 py-2.5 text-left"
        >
          <div>
            <div className="text-[11px] font-bold uppercase tracking-wider text-indigo-600 dark:text-indigo-300">
              Cum se face evaluarea
            </div>
            <div className="mt-0.5 text-[11px] text-slate-500 dark:text-slate-400">
              Scor 0-100, subsectiune separata de evaluarea actuala, fara componenta de bonus.
            </div>
          </div>
          {showMechanism ? <ChevronUp size={14} className="text-indigo-500" /> : <ChevronDown size={14} className="text-indigo-500" />}
        </button>
        {showMechanism && (
          <div className="border-t border-indigo-100 dark:border-indigo-900/40 px-3 pb-3 pt-2">
            <div className="space-y-2 text-[11px] leading-4 text-slate-600 dark:text-slate-300">
              <div className="rounded-lg border border-indigo-100 bg-white/80 p-2.5 dark:border-indigo-900/50 dark:bg-slate-900/50">
                <div className="font-semibold text-slate-800 dark:text-slate-100">Regula generala</div>
                <p className="mt-0.5">
                  Evaluarea noua este independenta de scorul vechi. Fiecare indicator primeste puncte dupa praguri fixe:
                  sub pragul minim primeste 0, pragul minim primeste o treime din punctaj, pragul mediu primeste doua treimi,
                  iar pragul bun primeste punctajul maxim. Scorul final este normalizat la 100.
                </p>
              </div>
              <div className="rounded-lg border border-indigo-100 bg-white/80 p-2.5 dark:border-indigo-900/50 dark:bg-slate-900/50">
                <div className="font-semibold text-slate-800 dark:text-slate-100">Ponderi</div>
                <p className="mt-0.5">
                  Selectie normala sau multi-luna: Target 25p, Productivitate 20p, Bon2Acc 15p, Focus 15p,
                  Folii Premium 10p, Valoare reper 15p. Daca selectezi doar luna partiala, scorul devine provizoriu:
                  Target 10p, Productivitate 25p, Bon2Acc 20p, Focus 20p, Folii Premium 10p, Valoare reper 15p.
                </p>
              </div>

              <div className="grid grid-cols-1 gap-2 md:grid-cols-2 xl:grid-cols-3">
              <div className="rounded-lg border border-slate-200 dark:border-slate-700 bg-white/80 dark:bg-slate-900/50 p-2.5">
                <div className="text-[11px] font-semibold text-slate-800 dark:text-slate-100">1. Target: max 25p, luna curenta singura 10p</div>
                <p className="mt-0.5 text-[11px] leading-4 text-slate-600 dark:text-slate-300">
                  In fiecare luna calculam targetul agentului asa: target magazin / zile cu vanzare in locatie x zile cu vanzare agent.
                  Luna primeste nota proprie: sub 80% = 0, 80-89.9% = 1/3, 90-99.9% = 2/3, minimum 100% = maxim.
                  Pentru selectie multi-luna, punctajul target este media ponderata a notelor lunare, nu doar procentul total agregat.
                  Procentul afisat in tabel este procentul agregat, iar punctele sunt nota lunara ponderata.
                </p>
              </div>
              <div className="rounded-lg border border-slate-200 dark:border-slate-700 bg-white/80 dark:bg-slate-900/50 p-2.5">
                <div className="text-[11px] font-semibold text-slate-800 dark:text-slate-100">2. Productivitate zilnica: max 20p/25p</div>
                <p className="mt-0.5 text-[11px] leading-4 text-slate-600 dark:text-slate-300">
                  Calculam vanzare / zile lucrate si comparam cu reperul disponibil: mediana colegilor din magazin,
                  apoi istoricul locatiei pe ultimele 3 luni, apoi media managerului. Puncte: sub 85% = 0,
                  85-99.9% = 1/3, 100-114.9% = 2/3, minimum 115% = maxim.
                </p>
              </div>
              <div className="rounded-lg border border-slate-200 dark:border-slate-700 bg-white/80 dark:bg-slate-900/50 p-2.5">
                <div className="text-[11px] font-semibold text-slate-800 dark:text-slate-100">3. Bon2Acc: max 15p/20p</div>
                <p className="mt-0.5 text-[11px] leading-4 text-slate-600 dark:text-slate-300">
                  Masuram procentul de bonuri cu minimum 2 produse din total bonuri agent. Puncte: sub 25% = 0,
                  25-29.9% = 1/3, 30-34.9% = 2/3, minimum 35% = maxim.
                </p>
              </div>
              <div className="rounded-lg border border-slate-200 dark:border-slate-700 bg-white/80 dark:bg-slate-900/50 p-2.5">
                <div className="text-[11px] font-semibold text-slate-800 dark:text-slate-100">4. Focus: max 15p/20p</div>
                <p className="mt-0.5 text-[11px] leading-4 text-slate-600 dark:text-slate-300">
                  Masuram produse focus / total produse vandute de agent. Puncte: sub 6% = 0, 6-7.9% = 1/3,
                  8-9.9% = 2/3, minimum 10% = maxim.
                </p>
              </div>
              <div className="rounded-lg border border-slate-200 dark:border-slate-700 bg-white/80 dark:bg-slate-900/50 p-2.5">
                <div className="text-[11px] font-semibold text-slate-800 dark:text-slate-100">5. Folii Premium: max 10p</div>
                <p className="mt-0.5 text-[11px] leading-4 text-slate-600 dark:text-slate-300">
                  Masuram folii premium din total folii eligibile. Premium inseamna modelele marcate Sapphire, Ceramic sau Corning.
                  Daca agentul are sub 5 folii eligibile, indicatorul este scos din scor si scorul se normalizeaza fara el.
                  Puncte: sub 30% = 0, 30-39.9% = 1/3, 40-49.9% = 2/3, minimum 50% = maxim.
                </p>
              </div>
              <div className="rounded-lg border border-slate-200 dark:border-slate-700 bg-white/80 dark:bg-slate-900/50 p-2.5">
                <div className="text-[11px] font-semibold text-slate-800 dark:text-slate-100">6. Valoare reper: max 15p</div>
                <p className="mt-0.5 text-[11px] leading-4 text-slate-600 dark:text-slate-300">
                  Masuram vanzare / total produse, adica valoarea medie per produs vandut. Puncte: sub 90 lei = 0,
                  90-94.9 lei = 1/3, 95-99.9 lei = 2/3, minimum 100 lei = maxim.
                </p>
              </div>
              <div className="rounded-lg border border-slate-200 dark:border-slate-700 bg-white/80 dark:bg-slate-900/50 p-2.5">
                <div className="text-[11px] font-semibold text-slate-800 dark:text-slate-100">7. Eligibilitate si rating</div>
                <p className="mt-0.5 text-[11px] leading-4 text-slate-600 dark:text-slate-300">
                  Un agent este eligibil daca are volum minim: luna finala cere 8 zile si 30 bonuri; luna partiala singura cere
                  40% din zilele disponibile si 20 bonuri. La selectie multi-luna, lunile inchise cer 8 zile si 30 bonuri per luna,
                  iar luna partiala cere 40% din zilele disponibile si 20 bonuri.
                  Rating: 85+ Excelent, 75-84.9 Foarte Bun, 65-74.9 Bun, 50-64.9 Risc, sub 50 Critic.
                </p>
              </div>
              <div className="rounded-lg border border-slate-200 dark:border-slate-700 bg-white/80 dark:bg-slate-900/50 p-2.5">
                <div className="text-[11px] font-semibold text-slate-800 dark:text-slate-100">8. Luna partiala si trend</div>
                <p className="mt-0.5 text-[11px] leading-4 text-slate-600 dark:text-slate-300">
                  Daca selectezi doar luna partiala, scorul este provizoriu: targetul cantareste 10p, productivitatea 25p,
                  Bon2Acc 20p si Focus 20p. Daca selectezi mai multe luni si una este partiala, luna partiala intra in
                  target cu ponderea zile disponibile / zile luna, iar lunile inchise raman dominante.
                </p>
              </div>
              </div>
            </div>
          </div>
        )}
      </div>

      <div className="rounded-xl border border-slate-200 dark:border-slate-700 bg-white/80 dark:bg-slate-900/50 p-2.5">
        <div className="grid grid-cols-4 gap-2">
          {[
            { label: 'Agenți', value: String(summary.agents), sub: `${rows.length} rânduri` },
            { label: 'Scor', value: summary.avgScore.toFixed(1), sub: 'medie /100' },
            { label: 'Eligibili', value: String(summary.eligible), sub: 'volum valid' },
            { label: 'Provizorii', value: String(summary.partial), sub: 'lună parțială' },
          ].map((item) => (
            <div key={item.label} className="min-w-0">
              <div className="text-[10px] uppercase tracking-wider font-bold text-slate-400 truncate">{item.label}</div>
              <div className="text-sm sm:text-base font-bold text-slate-900 dark:text-slate-100 tabular-nums truncate">{item.value}</div>
              <div className="hidden sm:block text-[10px] text-slate-500 dark:text-slate-400 truncate">{item.sub}</div>
            </div>
          ))}
        </div>
      </div>

      <div className="space-y-2 lg:hidden">
        {rows.map((row) => <AgentV2MobileCard key={`${row.month}:${row.site_code}:${row.agent}:mobile`} row={row} />)}
        {rows.length === 0 && <p className="rounded-2xl border border-slate-200 p-6 text-center text-sm text-slate-400 dark:border-slate-700">Fără agenți pentru filtrele selectate.</p>}
      </div>
      <div className="hidden rounded-2xl border border-slate-200 bg-white/70 dark:border-slate-700 dark:bg-slate-900/40 lg:block lg:overflow-hidden">
        <div className="max-h-[68vh] overflow-auto">
          <table className="min-w-[1320px] w-full text-left">
            <thead className="sticky top-0 z-10 bg-slate-100 dark:bg-slate-800 text-[10px] uppercase tracking-wider text-slate-500">
              <tr>
                <th className="px-3 py-2">Lună</th>
                <V2SortHeader label="Agent" sortKey="agent" currentKey={sortKey} direction={sortDirection} onSort={onSort} />
                <V2SortHeader label="Vânzare" sortKey="total_sales" align="right" currentKey={sortKey} direction={sortDirection} onSort={onSort} />
                <V2SortHeader label="Scor" sortKey="total_score" align="right" currentKey={sortKey} direction={sortDirection} onSort={onSort} />
                <V2SortHeader label="Status" sortKey="eligibility_status" currentKey={sortKey} direction={sortDirection} onSort={onSort} />
                <V2SortHeader label="Target" sortKey="target_pct" align="right" currentKey={sortKey} direction={sortDirection} onSort={onSort} />
                <V2SortHeader label="Productivitate" sortKey="daily_vs_reference_pct" align="right" currentKey={sortKey} direction={sortDirection} onSort={onSort} />
                <V2SortHeader label="Bon2Acc" sortKey="bonuri_pct" align="right" currentKey={sortKey} direction={sortDirection} onSort={onSort} />
                <V2SortHeader label="Focus" sortKey="focus_pct" align="right" currentKey={sortKey} direction={sortDirection} onSort={onSort} />
                <V2SortHeader label="Folii Premium" sortKey="premium_glass_pct" align="right" currentKey={sortKey} direction={sortDirection} onSort={onSort} />
                <V2SortHeader label="Valoare reper" sortKey="value_reper" align="right" currentKey={sortKey} direction={sortDirection} onSort={onSort} />
                <V2SortHeader label="Trend" sortKey="trend_daily_pct" align="right" currentKey={sortKey} direction={sortDirection} onSort={onSort} />
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <AgentV2Row key={`${row.month}:${row.site_code}:${row.agent}:v2`} row={row} />
              ))}
              {rows.length === 0 && (
                <tr>
                  <td colSpan={12} className="px-3 py-8 text-center text-sm text-slate-400">
                    Fără agenți pentru filtrele selectate.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

const EMPTY_RESPONSE: AgentEvaluationResponse = { months: [], firmas: [], asms: [], stores: [], rows: [] };
const EMPTY_V2_RESPONSE: AgentEvaluationV2Response = { months: [], firmas: [], asms: [], stores: [], rows: [] };

export function AgentEvaluationSubtab() {
  const [data, setData] = useState<AgentEvaluationResponse>(EMPTY_RESPONSE);
  const [v2Data, setV2Data] = useState<AgentEvaluationV2Response>(EMPTY_V2_RESPONSE);
  const [mode, setMode] = useState<'current' | 'new'>('new');
  const [selectedMonths, setSelectedMonths] = useState<string[]>([]);
  const [firma, setFirma] = useState('');
  const [asm, setAsm] = useState('');
  const [selectedStores, setSelectedStores] = useState<string[]>([]);
  const [sortKey, setSortKey] = useState<SortKey>('total_points');
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('desc');
  const [v2SortKey, setV2SortKey] = useState<V2SortKey>('total_score');
  const [v2SortDirection, setV2SortDirection] = useState<'asc' | 'desc'>('desc');
  const [loading, setLoading] = useState(false);
  const [mobileFiltersOpen, setMobileFiltersOpen] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = {
        months: selectedMonths.length ? selectedMonths.join(',') : undefined,
        asm: asm || undefined,
        site_code: selectedStores.length ? selectedStores.join(',') : undefined,
      };
      const [legacyResponse, v2Response] = await Promise.all([
        fetchAgentEvaluation(params),
        fetchAgentEvaluationV2(params),
      ]);
      setData(legacyResponse);
      setV2Data(v2Response);
    } finally {
      setLoading(false);
    }
  }, [asm, selectedMonths, selectedStores]);

  useEffect(() => { void load(); }, [load]);

  const toggleMonth = (value: string) => {
    setSelectedMonths((current) => {
      if (current.includes(value)) return current.filter((monthValue) => monthValue !== value);
      return [...current, value].sort();
    });
  };

  const toggleStore = (value: string) => {
    setSelectedStores((current) => {
      if (current.includes(value)) return current.filter((storeValue) => storeValue !== value);
      return [...current, value].sort();
    });
  };

  const rows = useMemo(() => {
    const filtered = firma
      ? data.rows.filter((row) => row.firma.toLowerCase() === firma.toLowerCase())
      : data.rows;

    return [...filtered].sort((a, b) => {
      const av = getSortValue(a, sortKey);
      const bv = getSortValue(b, sortKey);
      const result = typeof av === 'number' && typeof bv === 'number'
        ? av - bv
        : String(av).localeCompare(String(bv), 'ro');
      return sortDirection === 'asc' ? result : -result;
    });
  }, [data.rows, firma, sortKey, sortDirection]);

  const v2Rows = useMemo(() => {
    const filtered = firma
      ? v2Data.rows.filter((row) => row.firma.toLowerCase() === firma.toLowerCase())
      : v2Data.rows;

    return [...filtered].sort((a, b) => {
      const av = getV2SortValue(a, v2SortKey);
      const bv = getV2SortValue(b, v2SortKey);
      const result = typeof av === 'number' && typeof bv === 'number'
        ? av - bv
        : String(av).localeCompare(String(bv), 'ro');
      return v2SortDirection === 'asc' ? result : -result;
    });
  }, [v2Data.rows, firma, v2SortKey, v2SortDirection]);

  const handleSort = (key: SortKey) => {
    if (key === sortKey) {
      setSortDirection((value) => value === 'asc' ? 'desc' : 'asc');
      return;
    }
    setSortKey(key);
    setSortDirection(key === 'agent' || key === 'month' ? 'asc' : 'desc');
  };

  const handleV2Sort = (key: V2SortKey) => {
    if (key === v2SortKey) {
      setV2SortDirection((value) => value === 'asc' ? 'desc' : 'asc');
      return;
    }
    setV2SortKey(key);
    setV2SortDirection(key === 'agent' || key === 'eligibility_status' ? 'asc' : 'desc');
  };

  const summary = useMemo(() => {
    const agents = new Set(rows.map((row) => row.agent)).size;
    const avgPoints = rows.length ? rows.reduce((sum, row) => sum + row.total_points, 0) / rows.length : 0;
    const totalSales = rows.reduce((sum, row) => sum + row.total_sales, 0);
    const premiumRows = rows.filter((row) => row.premium_glass_points >= 2).length;
    return { agents, avgPoints, totalSales, premiumRows };
  }, [rows]);

  const filterControls = (
    <div className="grid grid-cols-[minmax(0,1fr)_auto] gap-1.5 sm:grid-cols-[160px_86px_150px_minmax(260px,1fr)]">
      <MonthDropdown
        months={data.months}
        selectedMonths={selectedMonths}
        onToggle={toggleMonth}
        onClear={() => setSelectedMonths([])}
      />
      <FirmSelector options={data.firmas} selected={firma} onChange={setFirma} />
      <select
        value={asm}
        onChange={(e) => {
          setAsm(e.target.value);
          setSelectedStores([]);
        }}
        className="col-span-2 h-9 w-full rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 sm:col-span-1"
      >
        <option value="">Manageri</option>
        {data.asms.map((option) => (
          <option key={option.value} value={option.value}>{option.label}</option>
        ))}
      </select>
      <div className="col-span-2 sm:col-span-1">
        <StoreDropdown
          stores={data.stores}
          selectedStores={selectedStores}
          onToggle={toggleStore}
          onClear={() => setSelectedStores([])}
        />
      </div>
    </div>
  );

  return (
    <div className="p-3 md:p-4 space-y-3">
      <div className="sticky top-2 z-20 flex flex-wrap items-center justify-between gap-2 rounded-2xl border border-slate-200 bg-white/95 p-3 shadow-sm backdrop-blur-xl dark:border-slate-700 dark:bg-slate-900/95">
        <div>
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500">Analiză agenți</h3>
          <p className="text-[11px] text-slate-400 mt-0.5">Din ianuarie 2025</p>
        </div>
        <div className="hidden h-9 rounded-lg border border-slate-200 bg-white p-1 dark:border-slate-700 dark:bg-slate-800 lg:inline-flex">
          {[
            { key: 'new', label: 'Scor 0–100' },
            { key: 'current', label: 'Comparație veche' },
          ].map((item) => (
            <button
              key={item.key}
              type="button"
              onClick={() => setMode(item.key as 'current' | 'new')}
              className={`rounded-md px-3 py-1 text-xs font-semibold transition ${
                mode === item.key
                  ? 'bg-indigo-600 text-white shadow-sm'
                  : 'text-slate-500 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-700'
              }`}
            >
              {item.label}
            </button>
          ))}
        </div>
        <button type="button" onClick={() => setMobileFiltersOpen(true)} className="min-h-11 rounded-xl border border-indigo-200 bg-indigo-50 px-3 text-xs font-bold text-indigo-700 dark:border-indigo-800 dark:bg-indigo-950/40 dark:text-indigo-300 lg:hidden">Filtre</button>
        <details className="relative lg:hidden">
          <summary className="flex min-h-11 cursor-pointer list-none items-center rounded-xl border border-slate-200 bg-white px-3 text-xs font-bold text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">Mod</summary>
          <div className="absolute right-0 z-40 mt-1 w-48 rounded-xl border border-slate-200 bg-white p-1 shadow-xl dark:border-slate-700 dark:bg-slate-900">
            <button type="button" onClick={() => setMode('new')} className="min-h-11 w-full rounded-lg px-3 text-left text-xs font-semibold hover:bg-slate-100 dark:hover:bg-slate-800">Scor 0–100</button>
            <button type="button" onClick={() => setMode('current')} className="min-h-11 w-full rounded-lg px-3 text-left text-xs font-semibold hover:bg-slate-100 dark:hover:bg-slate-800">Comparație veche</button>
          </div>
        </details>
        <button
          onClick={load}
          aria-label="Reîncarcă analiza"
          className="flex h-11 w-11 items-center justify-center rounded-xl bg-slate-100 text-slate-500 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700"
        >
          <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
        </button>
        {mode === 'current' ? (
          <ExportTableButton
            filename="management_agenti_evaluare_actuala"
            sheetName="Evaluare Actuala"
            rows={rows}
            columns={[
              { header: 'Luna', value: (row) => row.month },
              { header: 'Firma', value: (row) => row.firma },
              { header: 'Agent', value: (row) => row.agent },
              { header: 'Magazin', value: (row) => row.locatie },
              { header: 'Vanzare', value: (row) => formatMoney(row.total_sales) },
              { header: 'Target', value: (row) => formatMoney(row.target_value) },
              { header: '% Target', value: (row) => formatPct(row.target_pct) },
              { header: 'Medie zilnica', value: (row) => formatNumber(row.daily_average, 0) },
              { header: 'Valoare reper', value: (row) => formatNumber(row.value_reper, 0) },
              { header: 'Bon2Acc', value: (row) => formatPct(row.bonuri_pct) },
              { header: 'Focus', value: (row) => formatPct(row.focus_pct) },
              { header: 'Folii Premium', value: (row) => formatPct(row.premium_glass_pct) },
              { header: 'Scor', value: (row) => `${row.total_points}/18` },
              { header: 'Calificativ', value: (row) => row.qualifier },
            ]}
          />
        ) : (
          <ExportTableButton
            filename="management_agenti_evaluare_noua"
            sheetName="Evaluare Noua"
            rows={v2Rows}
            columns={[
              { header: 'Luna', value: (row) => row.month },
              { header: 'Firma', value: (row) => row.firma },
              { header: 'Agent', value: (row) => row.agent },
              { header: 'Magazin', value: (row) => row.locatie },
              { header: 'Vanzare', value: (row) => formatMoney(row.total_sales) },
              { header: 'Scor', value: (row) => row.total_score === null ? '' : Number(row.total_score).toFixed(1) },
              { header: 'Rating', value: (row) => row.rating },
              { header: 'Status', value: (row) => row.eligibility_status },
              { header: 'Flaguri', value: (row) => row.confidence_flags.map(flagLabel).join(', ') },
              { header: '% Target', value: (row) => formatPct(row.target_pct) },
              { header: 'Productivitate vs reper', value: (row) => formatPct(row.daily_vs_reference_pct) },
              { header: 'Bon2Acc', value: (row) => formatPct(row.bonuri_pct) },
              { header: 'Focus', value: (row) => formatPct(row.focus_pct) },
              { header: 'Folii Premium', value: (row) => formatPct(row.premium_glass_pct) },
              { header: 'Valoare reper', value: (row) => formatNumber(row.value_reper, 0) },
              { header: 'Trend 3 luni', value: (row) => formatPct(row.trend_daily_pct) },
            ]}
          />
        )}
      </div>

      {mobileFiltersOpen && (
        <div className="fixed inset-0 z-50 flex items-end bg-slate-950/40 lg:hidden" onClick={() => setMobileFiltersOpen(false)}>
          <div className="mobile-filter-sheet w-full rounded-t-3xl bg-white p-4 shadow-2xl dark:bg-slate-900" onClick={(event) => event.stopPropagation()}>
            <div className="mb-3 flex items-center justify-between"><h3 className="text-base font-bold">Filtre analiză</h3><button type="button" onClick={() => setMobileFiltersOpen(false)} className="h-11 rounded-xl bg-slate-100 px-3 text-xs font-bold dark:bg-slate-800">Închide</button></div>
            {filterControls}
            <button type="button" onClick={() => setMobileFiltersOpen(false)} className="mt-4 min-h-11 w-full rounded-xl bg-indigo-600 px-4 text-sm font-bold text-white">Aplică filtrele</button>
          </div>
        </div>
      )}

      {mode === 'current' ? (
        <>
          <MechanismCard />
          <CompactSummary rows={rows} summary={summary}>
            <div className="hidden lg:block">{filterControls}</div>
          </CompactSummary>

          <div className="space-y-2 lg:hidden">
            {rows.map((row) => <AgentLegacyMobileCard key={`${row.month}:${row.site_code}:${row.agent}:legacy-mobile`} row={row} />)}
          </div>

          <div className="hidden rounded-2xl border border-slate-200 bg-white/70 dark:border-slate-700 dark:bg-slate-900/40 lg:block lg:overflow-hidden">
            <div className="max-h-[68vh] overflow-auto">
              <table className="min-w-[1060px] xl:min-w-0 w-full text-left">
                <thead className="sticky top-0 z-10 bg-slate-100 dark:bg-slate-800 text-[10px] uppercase tracking-wider text-slate-500">
                  <tr>
                    <SortHeader label="Lună" sortKey="month" currentKey={sortKey} direction={sortDirection} onSort={handleSort} />
                    <SortHeader label="Agent" sortKey="agent" currentKey={sortKey} direction={sortDirection} onSort={handleSort} />
                    <SortHeader label="Vânzare" sortKey="total_sales" align="right" currentKey={sortKey} direction={sortDirection} onSort={handleSort} />
                    <SortHeader label="Target" sortKey="target_value" align="right" currentKey={sortKey} direction={sortDirection} onSort={handleSort} />
                    <SortHeader label="% Target" sortKey="target_pct" align="right" currentKey={sortKey} direction={sortDirection} onSort={handleSort} />
                    <SortHeader label="Medie zilnică" sortKey="daily_average" align="right" currentKey={sortKey} direction={sortDirection} onSort={handleSort} />
                    <SortHeader label="Valoare reper" sortKey="value_reper" align="right" currentKey={sortKey} direction={sortDirection} onSort={handleSort} />
                    <SortHeader label="% Bonuri" sortKey="bonuri_pct" align="right" currentKey={sortKey} direction={sortDirection} onSort={handleSort} />
                    <SortHeader label="Focus" sortKey="focus_pct" align="right" currentKey={sortKey} direction={sortDirection} onSort={handleSort} />
                    <SortHeader label="Folii Premium" sortKey="premium_glass_pct" align="right" currentKey={sortKey} direction={sortDirection} onSort={handleSort} />
                    <SortHeader label="Scor" sortKey="total_points" align="right" currentKey={sortKey} direction={sortDirection} onSort={handleSort} />
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <AgentRow key={`${row.month}:${row.site_code}:${row.agent}`} row={row} />
                  ))}
                  {!loading && rows.length === 0 && (
                    <tr>
                      <td colSpan={11} className="px-3 py-8 text-center text-sm text-slate-400">
                        Fără agenți pentru filtrele selectate.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </>
      ) : (
        <>
          <div className="hidden rounded-xl border border-slate-200 bg-white/80 p-2.5 dark:border-slate-700 dark:bg-slate-900/50 lg:block">
            {filterControls}
          </div>
          <NewEvaluationSubsection
            rows={v2Rows}
            sortKey={v2SortKey}
            sortDirection={v2SortDirection}
            onSort={handleV2Sort}
          />
        </>
      )}
    </div>
  );
}
