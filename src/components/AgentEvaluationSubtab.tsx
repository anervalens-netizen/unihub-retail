import { useEffect, useMemo, useState } from 'react';
import { ChevronDown, ChevronUp, RefreshCw, Search } from 'lucide-react';
import {
  fetchAgentEvaluation,
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
  if (month.includes('..')) return <>Ian-Mai 26</>;
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

function SummaryCard({ label, value, sublabel }: { label: string; value: string; sublabel?: string }) {
  return (
    <div className="rounded-xl border border-slate-200 dark:border-slate-700 bg-white/70 dark:bg-slate-900/40 p-3">
      <div className="text-[11px] uppercase tracking-wider font-bold text-slate-400">{label}</div>
      <div className="mt-1 text-xl font-bold text-slate-900 dark:text-slate-100">{value}</div>
      {sublabel && <div className="text-[11px] text-slate-500 dark:text-slate-400">{sublabel}</div>}
    </div>
  );
}

function MechanismCard() {
  const items = [
    {
      label: 'Perioadă',
      text: 'Toate lunile agregă ianuarie-mai 2026 pe agent; o lună selectată arată doar luna respectivă.',
    },
    {
      label: 'Alocare',
      text: 'Sunt incluși doar agenții activi în luna curentă disponibilă, afișați pe firma, magazinul și managerul curent.',
    },
    {
      label: 'Target agent',
      text: 'Target locație se împarte la totalul zilelor lucrate în locație, apoi se înmulțește cu zilele lucrate de agent.',
    },
    {
      label: 'Punctaj',
      text: 'Fiecare segment are 0-3 puncte: Target, Medie zilnică, Valoare reper, % Bonuri, Focus și Folii Premium.',
    },
    {
      label: 'Folii Premium',
      text: 'Premium înseamnă SAPPHIRE, CERAMIC sau CORNING din Folii Sticla, raportate la totalul foliilor pentru aceleași modele țintă ca în Focus.',
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
    <div className="rounded-2xl border border-indigo-200 dark:border-indigo-900/50 bg-indigo-50/60 dark:bg-indigo-950/20 p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h4 className="text-sm font-bold text-slate-900 dark:text-slate-100">Mecanism analiză agenți</h4>
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
            Scorul final este suma celor 6 segmente, maxim 18 puncte. Bonusul se acordă pe pragurile din analiza sursă.
          </p>
        </div>
        <span className="shrink-0 rounded-full bg-white/80 dark:bg-slate-900/70 px-2.5 py-1 text-xs font-bold text-indigo-600 dark:text-indigo-300">
          max 18 pct
        </span>
      </div>
      <div className="mt-3 grid grid-cols-1 md:grid-cols-2 xl:grid-cols-5 gap-2">
        {items.map((item) => (
          <div key={item.label} className="rounded-xl bg-white/80 dark:bg-slate-900/50 border border-indigo-100 dark:border-indigo-900/40 p-3">
            <div className="text-[11px] font-bold uppercase tracking-wider text-indigo-600 dark:text-indigo-300">{item.label}</div>
            <p className="mt-1 text-[11px] leading-4 text-slate-600 dark:text-slate-300">{item.text}</p>
          </div>
        ))}
      </div>
      <div className="mt-3 rounded-xl border border-indigo-100 dark:border-indigo-900/40 bg-white/80 dark:bg-slate-900/50 p-3">
        <div className="text-[11px] font-bold uppercase tracking-wider text-indigo-600 dark:text-indigo-300">Alocare puncte</div>
        <div className="mt-2 grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-2">
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
    </div>
  );
}

function AgentRow({ row }: { row: AgentEvaluationRow }) {
  return (
    <tr className="border-b border-slate-100 dark:border-slate-800 hover:bg-slate-50 dark:hover:bg-slate-800/50">
      <td className="px-3 py-2 whitespace-nowrap text-xs font-medium text-slate-600 dark:text-slate-300">
        <MonthLabel month={row.month} />
      </td>
      <td className="px-3 py-2 min-w-[190px]">
        <div className="text-sm font-semibold text-slate-800 dark:text-slate-100">{row.agent}</div>
        <div className="text-[11px] text-slate-400">{row.locatie} · {row.asm}</div>
      </td>
      <td className="px-3 py-2 text-right text-xs text-slate-600 dark:text-slate-300">
        <div className="font-semibold">{formatMoney(row.total_sales)}</div>
        <div className="text-[10px] text-slate-400">{row.working_days} zile</div>
      </td>
      <td className="px-3 py-2 text-right text-xs text-slate-600 dark:text-slate-300">
        <div>{formatMoney(row.target_value)}</div>
        <div className="text-[10px] text-slate-400">loc. {formatMoney(row.store_target)}</div>
      </td>
      <td className="px-3 py-2"><MetricCell value={row.target_pct} points={row.target_points} /></td>
      <td className="px-3 py-2 text-right text-xs">
        <div className="font-medium text-slate-700 dark:text-slate-200">{formatNumber(row.daily_average, 0)}</div>
        <div className={`text-[10px] font-semibold ${pointColor(row.daily_points)}`}>{row.daily_points}/3</div>
      </td>
      <td className="px-3 py-2"><MetricCell value={row.value_reper} points={row.value_reper_points} suffix="lei" /></td>
      <td className="px-3 py-2"><MetricCell value={row.bonuri_pct} points={row.bonuri_points} /></td>
      <td className="px-3 py-2"><MetricCell value={row.focus_pct} points={row.focus_points} /></td>
      <td className="px-3 py-2 text-right text-xs">
        <div className="font-medium text-slate-700 dark:text-slate-200">{formatPct(row.premium_glass_pct)}</div>
        <div className="text-[10px] text-slate-400">{row.premium_glass_qty}/{row.glass_qty}</div>
        <div className={`text-[10px] font-semibold ${pointColor(row.premium_glass_points)}`}>{row.premium_glass_points}/3</div>
      </td>
      <td className="px-3 py-2 text-right whitespace-nowrap">
        <span className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-bold tabular-nums ${scoreColor(row.total_points)}`}>
          {row.total_points}/18
        </span>
        <div className="text-[10px] text-slate-400 mt-0.5">{row.qualifier}</div>
      </td>
      <td className="px-3 py-2 text-right text-xs font-semibold text-slate-700 dark:text-slate-200">
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
    <th className={`px-3 py-2 ${align === 'right' ? 'text-right' : ''}`}>
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
  const [month, setMonth] = useState('');
  const [firma, setFirma] = useState('');
  const [asm, setAsm] = useState('');
  const [siteCode, setSiteCode] = useState('');
  const [search, setSearch] = useState('');
  const [sortKey, setSortKey] = useState<SortKey>('total_points');
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('desc');
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      setData(await fetchAgentEvaluation({
        month: month || undefined,
        firma: firma || undefined,
        asm: asm || undefined,
        site_code: siteCode || undefined,
      }));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [month, firma, asm, siteCode]);

  const rows = useMemo(() => {
    const term = search.trim().toLowerCase();
    const filtered = term ? data.rows.filter((row) =>
      row.agent.toLowerCase().includes(term) ||
      row.locatie.toLowerCase().includes(term) ||
      row.site_code.toLowerCase().includes(term)
    ) : data.rows;

    return [...filtered].sort((a, b) => {
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
  }, [data.rows, search, sortKey, sortDirection]);

  const handleSort = (key: SortKey) => {
    if (key === sortKey) {
      setSortDirection((value) => value === 'asc' ? 'desc' : 'asc');
      return;
    }
    setSortKey(key);
    setSortDirection(key === 'agent' || key === 'month' ? 'asc' : 'desc');
  };

  const summary = useMemo(() => {
    const agents = new Set(rows.map((row) => `${row.month}:${row.site_code}:${row.agent}`)).size;
    const avgPoints = rows.length ? rows.reduce((sum, row) => sum + row.total_points, 0) / rows.length : 0;
    const totalBonus = rows.reduce((sum, row) => sum + row.bonus_amount, 0);
    const premiumRows = rows.filter((row) => row.premium_glass_points >= 2).length;
    return { agents, avgPoints, totalBonus, premiumRows };
  }, [rows]);

  return (
    <div className="p-4 space-y-4">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div>
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500">Analiză agenți</h3>
          <p className="text-[11px] text-slate-400 mt-0.5">Ianuarie - mai 2026</p>
        </div>
        <button
          onClick={load}
          className="p-1.5 rounded-xl bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-500"
        >
          <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
        </button>
      </div>

      <MechanismCard />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-2">
        <SummaryCard label="Rânduri" value={String(rows.length)} sublabel={`${summary.agents} agent-lună`} />
        <SummaryCard label="Punctaj mediu" value={summary.avgPoints.toFixed(1)} sublabel="din 18 puncte" />
        <SummaryCard label="Bonus estimat" value={`${formatMoney(summary.totalBonus)} lei`} />
        <SummaryCard label="Folii premium" value={String(summary.premiumRows)} sublabel="rânduri cu 2+ pct" />
      </div>

      <div className="flex flex-wrap gap-2">
        <select
          value={month}
          onChange={(e) => setMonth(e.target.value)}
          className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs text-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300"
        >
          <option value="">Toate lunile</option>
          {data.months.map((option) => (
            <option key={option.value} value={option.value}>{option.label}</option>
          ))}
        </select>
        <select
          value={firma}
          onChange={(e) => setFirma(e.target.value)}
          className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs text-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300"
        >
          <option value="">Toate firmele</option>
          {data.firmas.map((option) => (
            <option key={option.value} value={option.value}>{option.label}</option>
          ))}
        </select>
        <select
          value={asm}
          onChange={(e) => setAsm(e.target.value)}
          className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs text-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300"
        >
          <option value="">Manageri</option>
          {data.asms.map((option) => (
            <option key={option.value} value={option.value}>{option.label}</option>
          ))}
        </select>
        <select
          value={siteCode}
          onChange={(e) => setSiteCode(e.target.value)}
          className="min-w-[220px] rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs text-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300"
        >
          <option value="">Toate magazinele</option>
          {data.stores.map((option) => (
            <option key={option.value} value={option.value}>{option.label}</option>
          ))}
        </select>
        <div className="relative flex-1 min-w-[220px]">
          <Search size={13} className="absolute left-3 top-2.5 text-slate-400" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Caută agent sau magazin"
            className="w-full rounded-xl border border-slate-200 bg-white pl-8 pr-3 py-2 text-xs text-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300"
          />
        </div>
      </div>

      <div className="rounded-2xl border border-slate-200 dark:border-slate-700 overflow-hidden bg-white/70 dark:bg-slate-900/40">
        <div className="max-h-[65vh] overflow-auto">
          <table className="min-w-[1180px] w-full text-left">
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
