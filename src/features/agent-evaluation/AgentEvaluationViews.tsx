import { RefreshCw } from 'lucide-react';

import type { AgentEvaluationRow, AgentEvaluationV2Row } from '../../api/agents';
import { ExportTableButton } from '../../components/ExportTableButton';
import { CompactSummary, FirmSelector, MechanismCard, MonthDropdown, StoreDropdown } from './AgentEvaluationControls';
import { AgentLegacyMobileCard, AgentRow, flagLabel, SortHeader, type SortKey } from './AgentEvaluationTables';
import { NewEvaluationSubsection } from './AgentEvaluationV2Table';
import type { AgentEvaluationController } from './useAgentEvaluationController';

export function EvaluationFilters({ model }: { model: AgentEvaluationController }) {
  return <div className="grid grid-cols-[minmax(0,1fr)_auto] gap-1.5 sm:grid-cols-[160px_86px_150px_minmax(260px,1fr)]">
    <MonthDropdown months={model.optionData.months} selectedMonths={model.selectedMonths} onToggle={model.toggleMonth} onClear={() => model.setSelectedMonths([])} />
    <FirmSelector options={model.optionData.firmas} selected={model.firma} onChange={model.setFirma} />
    <select value={model.asm} onChange={(event) => model.resetManager(event.target.value)} className="col-span-2 h-9 w-full rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 sm:col-span-1">
      <option value="">Manageri</option>
      {model.optionData.asms.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
    </select>
    <div className="col-span-2 sm:col-span-1"><StoreDropdown stores={model.optionData.stores} selectedStores={model.selectedStores} onToggle={model.toggleStore} onClear={() => model.setSelectedStores([])} /></div>
  </div>;
}

function LegacyEvaluationExport({ rows }: { rows: AgentEvaluationRow[] }) {
  return <ExportTableButton filename="management_agenti_evaluare_actuala" sheetName="Analiza" rows={rows} columns={[
    { header: 'Luna', value: (row) => row.month, format: 'month' }, { header: 'Firma', value: (row) => row.firma },
    { header: 'Agent', value: (row) => row.agent }, { header: 'Magazin', value: (row) => row.locatie },
    { header: 'Vanzare', value: (row) => row.total_sales, format: 'currency' }, { header: 'Target', value: (row) => row.target_value, format: 'currency' },
    { header: '% Target', value: (row) => row.target_pct, format: 'percentPoints' }, { header: 'Medie zilnica', value: (row) => row.daily_average, format: 'number' },
    { header: 'Valoare reper', value: (row) => row.value_reper, format: 'number' }, { header: 'Bon2Acc', value: (row) => row.bonuri_pct, format: 'percentPoints' },
    { header: 'Focus', value: (row) => row.focus_pct, format: 'percentPoints' }, { header: 'Folii Premium', value: (row) => row.premium_glass_pct, format: 'percentPoints' },
    { header: 'Scor', value: (row) => row.total_points, format: 'integer' }, { header: 'Scor maxim', value: () => 18, format: 'integer' },
    { header: 'Calificativ', value: (row) => row.qualifier },
  ]} />;
}

function NewEvaluationExport({ rows }: { rows: AgentEvaluationV2Row[] }) {
  return <ExportTableButton filename="management_agenti_evaluare_noua" sheetName="Punctaj 0-100" rows={rows} columns={[
    { header: 'Luna', value: (row) => row.month, format: 'month' }, { header: 'Firma', value: (row) => row.firma },
    { header: 'Agent', value: (row) => row.agent }, { header: 'Magazin', value: (row) => row.locatie },
    { header: 'Vanzare', value: (row) => row.total_sales, format: 'currency' }, { header: 'Scor', value: (row) => row.total_score, format: 'number' },
    { header: 'Rating', value: (row) => row.rating }, { header: 'Status', value: (row) => row.eligibility_status },
    { header: 'Flaguri', value: (row) => row.confidence_flags.map(flagLabel).join(', ') }, { header: '% Target', value: (row) => row.target_pct, format: 'percentPoints' },
    { header: 'Productivitate vs reper', value: (row) => row.daily_vs_reference_pct, format: 'percentPoints' }, { header: 'Bon2Acc', value: (row) => row.bonuri_pct, format: 'percentPoints' },
    { header: 'Focus', value: (row) => row.focus_pct, format: 'percentPoints' }, { header: 'Folii Premium', value: (row) => row.premium_glass_pct, format: 'percentPoints' },
    { header: 'Valoare reper', value: (row) => row.value_reper, format: 'number' }, { header: 'Trend 3 luni', value: (row) => row.trend_daily_pct, format: 'percentPoints' },
  ]} />;
}

export function EvaluationHeader({ model }: { model: AgentEvaluationController }) {
  const modes = [{ key: 'current' as const, label: 'Analiză' }, { key: 'new' as const, label: 'Punctaj 0–100' }];
  return <div className="sticky top-2 z-20 flex flex-wrap items-center justify-between gap-2 rounded-2xl border border-slate-200 bg-white/95 p-3 shadow-sm backdrop-blur-xl dark:border-slate-700 dark:bg-slate-900/95">
    <div><h3 className="text-xs font-bold uppercase tracking-wider text-slate-500">Analiză agenți</h3><p className="mt-0.5 text-[11px] text-slate-400">Din ianuarie 2025</p></div>
    <div className="hidden h-9 rounded-lg border border-slate-200 bg-white p-1 dark:border-slate-700 dark:bg-slate-800 lg:inline-flex">{modes.map((item) => <button key={item.key} type="button" onClick={() => model.setMode(item.key)} className={`rounded-md px-3 py-1 text-xs font-semibold transition ${model.mode === item.key ? 'bg-indigo-600 text-white shadow-sm' : 'text-slate-500 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-700'}`}>{item.label}</button>)}</div>
    <button type="button" onClick={() => model.setMobileFiltersOpen(true)} className="min-h-11 rounded-xl border border-indigo-200 bg-indigo-50 px-3 text-xs font-bold text-indigo-700 dark:border-indigo-800 dark:bg-indigo-950/40 dark:text-indigo-300 lg:hidden">Filtre</button>
    <details className="relative lg:hidden"><summary className="flex min-h-11 cursor-pointer list-none items-center rounded-xl border border-slate-200 bg-white px-3 text-xs font-bold text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">Mod</summary><div className="absolute right-0 z-40 mt-1 w-48 rounded-xl border border-slate-200 bg-white p-1 shadow-xl dark:border-slate-700 dark:bg-slate-900">{modes.map((item) => <button key={item.key} type="button" onClick={() => model.setMode(item.key)} className="min-h-11 w-full rounded-lg px-3 text-left text-xs font-semibold hover:bg-slate-100 dark:hover:bg-slate-800">{item.label}</button>)}</div></details>
    <button onClick={model.load} aria-label="Reîncarcă analiza" className="flex h-11 w-11 items-center justify-center rounded-xl bg-slate-100 text-slate-500 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700"><RefreshCw size={13} className={model.loading ? 'animate-spin' : ''} /></button>
    {model.mode === 'current' ? <LegacyEvaluationExport rows={model.rows} /> : <NewEvaluationExport rows={model.v2Rows} />}
  </div>;
}

export function EvaluationMobileFilters({ model }: { model: AgentEvaluationController }) {
  if (!model.mobileFiltersOpen) return null;
  return <div className="fixed inset-0 z-50 flex items-end bg-slate-950/40 lg:hidden" onClick={() => model.setMobileFiltersOpen(false)}><div className="mobile-filter-sheet w-full rounded-t-3xl bg-white p-4 shadow-2xl dark:bg-slate-900" onClick={(event) => event.stopPropagation()}>
    <div className="mb-3 flex items-center justify-between"><h3 className="text-base font-bold">Filtre analiză</h3><button type="button" onClick={() => model.setMobileFiltersOpen(false)} className="h-11 rounded-xl bg-slate-100 px-3 text-xs font-bold dark:bg-slate-800">Închide</button></div>
    <EvaluationFilters model={model} />
    <button type="button" onClick={() => model.setMobileFiltersOpen(false)} className="mt-4 min-h-11 w-full rounded-xl bg-indigo-600 px-4 text-sm font-bold text-white">Aplică filtrele</button>
  </div></div>;
}

function LegacyEvaluationTable({ model }: { model: AgentEvaluationController }) {
  const headers: Array<{ label: string; key: SortKey; align?: 'right' }> = [
    { label: 'Lună', key: 'month' }, { label: 'Agent', key: 'agent' }, { label: 'Vânzare', key: 'total_sales', align: 'right' },
    { label: 'Target', key: 'target_value', align: 'right' }, { label: '% Target', key: 'target_pct', align: 'right' },
    { label: 'Medie zilnică', key: 'daily_average', align: 'right' }, { label: 'Valoare reper', key: 'value_reper', align: 'right' },
    { label: '% Bonuri', key: 'bonuri_pct', align: 'right' }, { label: 'Focus', key: 'focus_pct', align: 'right' },
    { label: 'Folii Premium', key: 'premium_glass_pct', align: 'right' }, { label: 'Scor', key: 'total_points', align: 'right' },
  ];
  return <>
    <div className="space-y-2 lg:hidden">{model.rows.map((row) => <AgentLegacyMobileCard key={`${row.month}:${row.site_code}:${row.agent}:legacy-mobile`} row={row} />)}{!model.loading && model.rows.length === 0 && <p className="rounded-2xl border border-slate-200 p-6 text-center text-sm text-slate-400 dark:border-slate-700">Fără agenți pentru filtrele selectate.</p>}</div>
    <div className="hidden rounded-2xl border border-slate-200 bg-white/70 dark:border-slate-700 dark:bg-slate-900/40 lg:block lg:overflow-hidden"><div className="max-h-[68vh] overflow-auto"><table className="min-w-[1060px] w-full text-left xl:min-w-0">
      <thead className="sticky top-0 z-10 bg-slate-100 text-[10px] uppercase tracking-wider text-slate-500 dark:bg-slate-800"><tr>{headers.map((header) => <SortHeader key={header.key} label={header.label} sortKey={header.key} align={header.align} currentKey={model.sortKey} direction={model.sortDirection} onSort={model.handleSort} />)}</tr></thead>
      <tbody>{model.rows.map((row) => <AgentRow key={`${row.month}:${row.site_code}:${row.agent}`} row={row} />)}{!model.loading && model.rows.length === 0 && <tr><td colSpan={11} className="px-3 py-8 text-center text-sm text-slate-400">Fără agenți pentru filtrele selectate.</td></tr>}</tbody>
    </table></div></div>
  </>;
}

export function EvaluationContent({ model }: { model: AgentEvaluationController }) {
  if (model.mode === 'new') return <><div className="hidden rounded-xl border border-slate-200 bg-white/80 p-2.5 dark:border-slate-700 dark:bg-slate-900/50 lg:block"><EvaluationFilters model={model} /></div><NewEvaluationSubsection rows={model.v2Rows} sortKey={model.v2SortKey} sortDirection={model.v2SortDirection} onSort={model.handleV2Sort} /></>;
  return <><MechanismCard /><CompactSummary rows={model.rows} summary={model.summary}><div className="hidden lg:block"><EvaluationFilters model={model} /></div></CompactSummary><LegacyEvaluationTable model={model} /></>;
}

