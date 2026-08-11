import { useCallback, useEffect, useMemo, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import {
  fetchAgentEvaluation,
  fetchAgentEvaluationV2,
  type AgentEvaluationResponse,
  type AgentEvaluationV2Response,
} from '../../api/agents';
import { ExportTableButton } from '../../components/ExportTableButton';
import { shiftMonth } from '../../lib/dates';
import { CompactSummary, FirmSelector, MechanismCard, MonthDropdown, StoreDropdown } from './AgentEvaluationControls';
import { AgentLegacyMobileCard, AgentRow, flagLabel, getSortValue, getV2SortValue, SortHeader, type SortKey, type V2SortKey } from './AgentEvaluationTables';
import { NewEvaluationSubsection } from './AgentEvaluationV2Table';

const EMPTY_RESPONSE: AgentEvaluationResponse = { months: [], firmas: [], asms: [], stores: [], rows: [] };
const EMPTY_V2_RESPONSE: AgentEvaluationV2Response = { months: [], firmas: [], asms: [], stores: [], rows: [] };

function latestClosedMonth(currentMonth: string, months: readonly string[]): string {
  const availableClosedMonths = months
    .filter((month) => /^\d{4}-\d{2}$/.test(month) && month < currentMonth)
    .sort();
  const latestAvailable = availableClosedMonths[availableClosedMonths.length - 1];
  if (latestAvailable) return latestAvailable;

  const previousMonth = shiftMonth(currentMonth, -1);
  return previousMonth !== currentMonth ? previousMonth : '';
}

export function AgentEvaluationSubtab({
  currentMonth,
  months,
}: {
  currentMonth: string;
  months: string[];
}) {
  const [data, setData] = useState<AgentEvaluationResponse>(EMPTY_RESPONSE);
  const [v2Data, setV2Data] = useState<AgentEvaluationV2Response>(EMPTY_V2_RESPONSE);
  const [mode, setMode] = useState<'current' | 'new'>('current');
  const [selectedMonths, setSelectedMonths] = useState<string[]>(() => {
    const defaultMonth = latestClosedMonth(currentMonth, months);
    return defaultMonth ? [defaultMonth] : [];
  });
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
        site_code: selectedStores.length ? selectedStores : undefined,
      };
      if (mode === 'new') {
        setV2Data(await fetchAgentEvaluationV2(params));
      } else {
        setData(await fetchAgentEvaluation(params));
      }
    } finally {
      setLoading(false);
    }
  }, [asm, mode, selectedMonths, selectedStores]);

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

  const optionData = mode === 'new' ? v2Data : data;

  const filterControls = (
    <div className="grid grid-cols-[minmax(0,1fr)_auto] gap-1.5 sm:grid-cols-[160px_86px_150px_minmax(260px,1fr)]">
      <MonthDropdown
        months={optionData.months}
        selectedMonths={selectedMonths}
        onToggle={toggleMonth}
        onClear={() => setSelectedMonths([])}
      />
      <FirmSelector options={optionData.firmas} selected={firma} onChange={setFirma} />
      <select
        value={asm}
        onChange={(e) => {
          setAsm(e.target.value);
          setSelectedStores([]);
        }}
        className="col-span-2 h-9 w-full rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 sm:col-span-1"
      >
        <option value="">Manageri</option>
        {optionData.asms.map((option) => (
          <option key={option.value} value={option.value}>{option.label}</option>
        ))}
      </select>
      <div className="col-span-2 sm:col-span-1">
        <StoreDropdown
          stores={optionData.stores}
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
            { key: 'current', label: 'Analiză' },
            { key: 'new', label: 'Punctaj 0–100' },
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
            <button type="button" onClick={() => setMode('current')} className="min-h-11 w-full rounded-lg px-3 text-left text-xs font-semibold hover:bg-slate-100 dark:hover:bg-slate-800">Analiză</button>
            <button type="button" onClick={() => setMode('new')} className="min-h-11 w-full rounded-lg px-3 text-left text-xs font-semibold hover:bg-slate-100 dark:hover:bg-slate-800">Punctaj 0–100</button>
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
            sheetName="Analiza"
            rows={rows}
            columns={[
              { header: 'Luna', value: (row) => row.month, format: 'month' },
              { header: 'Firma', value: (row) => row.firma },
              { header: 'Agent', value: (row) => row.agent },
              { header: 'Magazin', value: (row) => row.locatie },
              { header: 'Vanzare', value: (row) => row.total_sales, format: 'currency' },
              { header: 'Target', value: (row) => row.target_value, format: 'currency' },
              { header: '% Target', value: (row) => row.target_pct, format: 'percentPoints' },
              { header: 'Medie zilnica', value: (row) => row.daily_average, format: 'number' },
              { header: 'Valoare reper', value: (row) => row.value_reper, format: 'number' },
              { header: 'Bon2Acc', value: (row) => row.bonuri_pct, format: 'percentPoints' },
              { header: 'Focus', value: (row) => row.focus_pct, format: 'percentPoints' },
              { header: 'Folii Premium', value: (row) => row.premium_glass_pct, format: 'percentPoints' },
              { header: 'Scor', value: (row) => row.total_points, format: 'integer' },
              { header: 'Scor maxim', value: () => 18, format: 'integer' },
              { header: 'Calificativ', value: (row) => row.qualifier },
            ]}
          />
        ) : (
          <ExportTableButton
            filename="management_agenti_evaluare_noua"
            sheetName="Punctaj 0-100"
            rows={v2Rows}
            columns={[
              { header: 'Luna', value: (row) => row.month, format: 'month' },
              { header: 'Firma', value: (row) => row.firma },
              { header: 'Agent', value: (row) => row.agent },
              { header: 'Magazin', value: (row) => row.locatie },
              { header: 'Vanzare', value: (row) => row.total_sales, format: 'currency' },
              { header: 'Scor', value: (row) => row.total_score, format: 'number' },
              { header: 'Rating', value: (row) => row.rating },
              { header: 'Status', value: (row) => row.eligibility_status },
              { header: 'Flaguri', value: (row) => row.confidence_flags.map(flagLabel).join(', ') },
              { header: '% Target', value: (row) => row.target_pct, format: 'percentPoints' },
              { header: 'Productivitate vs reper', value: (row) => row.daily_vs_reference_pct, format: 'percentPoints' },
              { header: 'Bon2Acc', value: (row) => row.bonuri_pct, format: 'percentPoints' },
              { header: 'Focus', value: (row) => row.focus_pct, format: 'percentPoints' },
              { header: 'Folii Premium', value: (row) => row.premium_glass_pct, format: 'percentPoints' },
              { header: 'Valoare reper', value: (row) => row.value_reper, format: 'number' },
              { header: 'Trend 3 luni', value: (row) => row.trend_daily_pct, format: 'percentPoints' },
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
            {!loading && rows.length === 0 && <p className="rounded-2xl border border-slate-200 p-6 text-center text-sm text-slate-400 dark:border-slate-700">Fără agenți pentru filtrele selectate.</p>}
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
