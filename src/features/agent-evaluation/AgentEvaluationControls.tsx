import { type ReactNode, useState } from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';
import type { AgentEvaluationOption, AgentEvaluationRow } from '../../api/agents';
import { formatMonthLabel } from '../../lib/dates';

export function formatMoney(value: number | null | undefined) {
  if (value === null || value === undefined) return '-';
  return new Intl.NumberFormat('ro-RO', { maximumFractionDigits: 0 }).format(Number(value));
}

export function formatPct(value: number | null | undefined) {
  if (value === null || value === undefined) return '-';
  return `${Number(value).toFixed(1)}%`;
}

export function formatNumber(value: number | null | undefined, digits = 0) {
  if (value === null || value === undefined) return '-';
  return new Intl.NumberFormat('ro-RO', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(Number(value));
}

export function scoreColor(points: number) {
  if (points >= 16) return 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300';
  if (points >= 10) return 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300';
  return 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300';
}

export function pointColor(points: number) {
  if (points === 3) return 'text-green-600 dark:text-green-400';
  if (points >= 1) return 'text-amber-600 dark:text-amber-400';
  return 'text-red-600 dark:text-red-400';
}

export function MonthLabel({ month }: { month: string }) {
  if (month === 'custom') return <>Selectate</>;
  const formatShort = (value: string) => {
    const formatted = formatMonthLabel(value, { year: 'short' });
    return formatted === value ? value : formatted;
  };
  if (month.includes('..')) {
    const [start, end] = month.split('..');
    if (!start || !end) return <>{formatShort(month)}</>;
    return <>{formatShort(start)} - {end.includes('-') ? formatShort(end) : end}</>;
  }
  return <>{formatShort(month)}</>;
}

export function MetricCell({ value, points, suffix = '%' }: { value: number | null; points: number; suffix?: string }) {
  return (
    <div className="text-right">
      <div className="font-medium text-slate-700 dark:text-slate-200">
        {suffix === 'lei' ? formatNumber(value, 0) : formatPct(value)}
      </div>
      <div className={`text-[10px] font-semibold ${pointColor(points)}`}>{points}/3</div>
    </div>
  );
}

export function MechanismCard() {
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

export function FirmBadge({ firma, size = 'sm' }: { firma: string; size?: 'sm' | 'md' }) {
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

export function CompactSummary({
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

export function MonthDropdown({
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
  const label = selectedMonths.length === 1
    ? formatMonthLabel(selectedMonths[0] ?? '', { month: 'long', year: 'full' })
    : selectedMonths.length
      ? `${selectedMonths.length} luni`
      : 'Toate lunile';

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

export function FirmSelector({
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

export function StoreDropdown({
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

