import { useEffect, useMemo, useState } from 'react';
import { ChevronDown, ChevronUp, RefreshCw } from 'lucide-react';
import {
  fetchAgentEvaluation,
  type AgentEvaluationOption,
  type AgentEvaluationRow,
  type AgentEvaluationResponse,
} from '../api/agents';

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
    const labels = ['Ian', 'Feb', 'Mar', 'Apr', 'Mai', 'Iun', 'Iul', 'Aug', 'Sep', 'Oct', 'Noi', 'Dec'];
    const [year, mo] = value.split('-');
    const label = labels[Number(mo) - 1];
    return label && year ? `${label} ${year.slice(2)}` : value;
  };
  if (month.includes('..')) {
    const [start, end] = month.split('..');
    return <>{formatShort(start)} - {end.includes('-') ? formatShort(end) : end}</>;
  }
  const labels = ['Ian', 'Feb', 'Mar', 'Apr', 'Mai', 'Iun', 'Iul', 'Aug', 'Sep', 'Oct', 'Noi', 'Dec'];
  const [year, mo] = month.split('-');
  return <>{labels[Number(mo) - 1]} {year.slice(2)}</>;
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
      text: 'Lunile bifate se agregă pe agent. Fără bifă = toate lunile disponibile din ianuarie 2025. Sunt incluși doar agenții activi curent, pe alocarea curentă de firmă, magazin și manager.',
    },
    {
      label: 'Scor',
      text: 'Target agent = target locație / zile lucrate locație * zile agent. Scorul are 6 segmente a câte 0-3p; Folii Premium sunt raportate la totalul foliilor eligibile pentru modelele țintă.',
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
    <div className="rounded-xl border border-indigo-200 dark:border-indigo-900/50 bg-indigo-50/60 dark:bg-indigo-950/20 p-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h4 className="text-sm font-bold text-slate-900 dark:text-slate-100">Mecanism analiză agenți</h4>
          <p className="mt-0.5 text-[11px] text-slate-500 dark:text-slate-400">
            Maxim 18 puncte. Bonus: 18p = 300 lei, 16-17p = 200 lei, 14-15p = 100 lei fără segment roșu.
          </p>
        </div>
        <span className="shrink-0 rounded-full bg-white/80 dark:bg-slate-900/70 px-2.5 py-1 text-xs font-bold text-indigo-600 dark:text-indigo-300">
          max 18 pct
        </span>
      </div>
      <div className="mt-2 grid grid-cols-1 lg:grid-cols-2 gap-2">
        {items.map((item) => (
          <div key={item.label} className="rounded-lg bg-white/80 dark:bg-slate-900/50 border border-indigo-100 dark:border-indigo-900/40 px-3 py-2">
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
            <p className="mt-2 text-[10px] text-slate-500 dark:text-slate-400">
              Bonus: 18p = 300 lei, 16-17p = 200 lei, 14-15p = 100 lei doar dacă niciun segment nu are 0 puncte.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

function FirmBadge({ firma }: { firma: string }) {
  const value = firma.toLowerCase();
  const isMobiup = value.includes('mobiup');
  const isMobicell = value.includes('mobicell');
  return (
    <span
      title={firma}
      className={`inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-[10px] font-black text-white ${
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
}: {
  rows: AgentEvaluationRow[];
  summary: { agents: number; avgPoints: number; totalBonus: number; premiumRows: number };
}) {
  return (
    <div className="rounded-xl border border-slate-200 dark:border-slate-700 bg-white/80 dark:bg-slate-900/50 px-3 py-2">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        {[
          { label: 'Agenți', value: String(summary.agents), sub: `${rows.length} rânduri` },
          { label: 'Punctaj mediu', value: summary.avgPoints.toFixed(1), sub: 'din 18 puncte' },
          { label: 'Bonus estimat', value: `${formatMoney(summary.totalBonus)} lei`, sub: 'total filtrat' },
          { label: 'Folii premium', value: String(summary.premiumRows), sub: 'rânduri cu 2+ pct' },
        ].map((item) => (
          <div key={item.label} className="min-w-0">
            <div className="text-[10px] uppercase tracking-wider font-bold text-slate-400 truncate">{item.label}</div>
            <div className="text-base font-bold text-slate-900 dark:text-slate-100 tabular-nums truncate">{item.value}</div>
            <div className="text-[10px] text-slate-500 dark:text-slate-400 truncate">{item.sub}</div>
          </div>
        ))}
      </div>
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
        className="w-full md:w-40 rounded-xl border border-slate-200 bg-white px-3 py-2 text-left text-xs text-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 flex items-center justify-between gap-2"
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
    .filter((option) => /mobiup|mobicell/i.test(option.label))
    .sort((a, b) => {
      const aMobiup = a.label.toLowerCase().includes('mobiup') ? 0 : 1;
      const bMobiup = b.label.toLowerCase().includes('mobiup') ? 0 : 1;
      return aMobiup - bMobiup || a.label.localeCompare(b.label, 'ro');
    });

  return (
    <div className="grid grid-cols-2 gap-1.5">
      {visibleOptions.map((option) => {
        const active = selected === option.value;
        return (
          <button
            key={option.value}
            onClick={() => onChange(active ? '' : option.value)}
            className={`min-w-0 rounded-xl border px-2 py-2 text-xs font-semibold transition flex items-center justify-center gap-1.5 ${
              active
                ? 'border-indigo-500 bg-indigo-50 text-indigo-700 dark:border-indigo-400 dark:bg-indigo-950/50 dark:text-indigo-200'
                : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700'
            }`}
            title={option.label}
          >
            <FirmBadge firma={option.label} />
            <span className="truncate">{option.label}</span>
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
        className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-left text-xs text-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 flex items-center justify-between gap-2"
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
      <td className="px-2 py-2 text-right text-xs font-semibold text-slate-700 dark:text-slate-200">
        {row.bonus_amount ? `${row.bonus_amount} lei` : '-'}
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
  | 'total_points'
  | 'bonus_amount';

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
  'bonus_amount',
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

const EMPTY_RESPONSE: AgentEvaluationResponse = { months: [], firmas: [], asms: [], stores: [], rows: [] };

export function AgentEvaluationSubtab() {
  const [data, setData] = useState<AgentEvaluationResponse>(EMPTY_RESPONSE);
  const [selectedMonths, setSelectedMonths] = useState<string[]>([]);
  const [firma, setFirma] = useState('');
  const [asm, setAsm] = useState('');
  const [selectedStores, setSelectedStores] = useState<string[]>([]);
  const [sortKey, setSortKey] = useState<SortKey>('total_points');
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('desc');
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      setData(await fetchAgentEvaluation({
        months: selectedMonths.length ? selectedMonths.join(',') : undefined,
        firma: firma || undefined,
        asm: asm || undefined,
        site_code: selectedStores.length ? selectedStores.join(',') : undefined,
      }));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [selectedMonths, firma, asm, selectedStores]);

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
    return [...data.rows].sort((a, b) => {
      const av = getSortValue(a, sortKey);
      const bv = getSortValue(b, sortKey);
      let result = 0;
      if (typeof av === 'number' && typeof bv === 'number') {
        result = av - bv;
      } else {
        result = String(av).localeCompare(String(bv), 'ro');
      }
      return sortDirection === 'asc' ? result : -result;
    });
  }, [data.rows, sortKey, sortDirection]);

  const handleSort = (key: SortKey) => {
    if (key === sortKey) {
      setSortDirection((value) => value === 'asc' ? 'desc' : 'asc');
      return;
    }
    setSortKey(key);
    setSortDirection(key === 'agent' || key === 'month' ? 'asc' : 'desc');
  };

  const summary = useMemo(() => {
    const agents = new Set(rows.map((row) => row.agent)).size;
    const avgPoints = rows.length ? rows.reduce((sum, row) => sum + row.total_points, 0) / rows.length : 0;
    const totalBonus = rows.reduce((sum, row) => sum + row.bonus_amount, 0);
    const premiumRows = rows.filter((row) => row.premium_glass_points >= 2).length;
    return { agents, avgPoints, totalBonus, premiumRows };
  }, [rows]);

  return (
    <div className="p-3 md:p-4 space-y-3">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div>
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500">Analiză agenți</h3>
          <p className="text-[11px] text-slate-400 mt-0.5">Din ianuarie 2025</p>
        </div>
        <button
          onClick={load}
          className="p-1.5 rounded-xl bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-500"
        >
          <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
        </button>
      </div>

      <MechanismCard />

      <CompactSummary rows={rows} summary={summary} />

      <div className="rounded-2xl border border-slate-200 dark:border-slate-700 overflow-hidden bg-white/70 dark:bg-slate-900/40">
        <div className="border-b border-slate-200 dark:border-slate-700 p-2">
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-[160px_210px_150px_minmax(260px,1fr)] gap-2">
            <MonthDropdown
              months={data.months}
              selectedMonths={selectedMonths}
              onToggle={toggleMonth}
              onClear={() => setSelectedMonths([])}
            />
            <FirmSelector options={data.firmas} selected={firma} onChange={setFirma} />
            <select
              value={asm}
              onChange={(e) => setAsm(e.target.value)}
              className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs text-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300"
            >
              <option value="">Manageri</option>
              {data.asms.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
            <StoreDropdown
              stores={data.stores}
              selectedStores={selectedStores}
              onToggle={toggleStore}
              onClear={() => setSelectedStores([])}
            />
          </div>
        </div>
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
                <SortHeader label="Bonus" sortKey="bonus_amount" align="right" currentKey={sortKey} direction={sortDirection} onSort={handleSort} />
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <AgentRow key={`${row.month}:${row.site_code}:${row.agent}`} row={row} />
              ))}
              {!loading && rows.length === 0 && (
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
