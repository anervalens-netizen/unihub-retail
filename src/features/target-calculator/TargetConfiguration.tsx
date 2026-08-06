import { Calculator, ChevronDown, RefreshCw } from 'lucide-react';
import type { Dispatch, SetStateAction } from 'react';

import { SeasonalityControl, type SeasonalityMode } from '../../components/SeasonalityControl';
import type { TargetCalculatorContext } from './api';
import { monthLabel } from './model';

const inputCls = 'rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300';

type TargetConfigurationProps = {
  context: TargetCalculatorContext | null;
  busy: boolean;
  loadInitial: () => Promise<void>;
  targetMonth: string;
  setTargetMonth: (value: string) => void;
  totalTarget: string;
  setTotalTarget: (value: string) => void;
  minFloor: string;
  setMinFloor: (value: string) => void;
  seasonalityMode: SeasonalityMode;
  selectSeasonalityMode: (mode: 'multi' | 'single') => void;
  handleCalculate: () => Promise<void>;
  logicOpen: boolean;
  setLogicOpen: Dispatch<SetStateAction<boolean>>;
};

export function TargetConfiguration({
  context, busy, loadInitial, targetMonth, setTargetMonth, totalTarget, setTotalTarget,
  minFloor, setMinFloor, seasonalityMode, selectSeasonalityMode, handleCalculate,
  logicOpen, setLogicOpen,
}: TargetConfigurationProps) {
  if (!context?.can_finalize) return null;

  return (
    <div className="glass space-y-3 rounded-2xl p-3 sm:p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="flex items-center gap-2 text-base font-semibold text-slate-900 dark:text-slate-100"><Calculator size={18} className="text-indigo-500" />Calculator Target</h2>
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">Propunerea se calculeaza si se salveaza ca draft comun pentru magazinele cu vanzari in ultima luna disponibila anterior targetului.</p>
        </div>
        <button onClick={() => void loadInitial()} disabled={busy} className="rounded-xl bg-slate-100 p-2 text-slate-500 hover:bg-slate-200 disabled:opacity-50 dark:bg-slate-800 dark:hover:bg-slate-700" title="Reincarca"><RefreshCw size={15} className={busy ? 'animate-spin' : ''} /></button>
      </div>
      <div className="grid grid-cols-2 gap-2.5 xl:grid-cols-5">
        <label className="col-span-2 space-y-1 text-xs text-slate-500 sm:col-span-1">Luna target<input className={`w-full ${inputCls}`} type="month" value={targetMonth} onChange={(event) => setTargetMonth(event.target.value)} /></label>
        <label className="space-y-1 text-xs text-slate-500">Target total (RON)<input className={`w-full ${inputCls}`} type="number" min="1" value={totalTarget} onChange={(event) => setTotalTarget(event.target.value)} /></label>
        <label className="space-y-1 text-xs text-slate-500">Prag minim (RON)<input className={`w-full ${inputCls}`} type="number" min="0" value={minFloor} onChange={(event) => setMinFloor(event.target.value)} /></label>
        <div className="col-span-2 sm:col-span-1"><SeasonalityControl value={seasonalityMode} disabled={busy || seasonalityMode === null} onChange={selectSeasonalityMode} /></div>
        <div className="col-span-2 flex items-end sm:col-span-1"><button onClick={handleCalculate} disabled={busy || seasonalityMode === null} className="w-full rounded-xl bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-indigo-700 disabled:opacity-50">{busy ? 'Se proceseaza...' : 'Calculeaza propunerea'}</button></div>
      </div>
      <div className="rounded-xl border border-slate-200 bg-white/70 dark:border-slate-700 dark:bg-slate-900/50">
        <button type="button" onClick={() => setLogicOpen((open) => !open)} aria-expanded={logicOpen} className="flex w-full items-center justify-between gap-3 px-3 py-2 text-left text-xs font-semibold text-slate-700 hover:text-indigo-600 dark:text-slate-200 dark:hover:text-indigo-300"><span className="flex items-center gap-2"><Calculator size={14} className="text-indigo-500" />Logica de calcul si formula</span><ChevronDown size={14} className={`shrink-0 transition-transform ${logicOpen ? 'rotate-180' : ''}`} /></button>
        {logicOpen && <div className="border-t border-slate-200 px-3 py-3 text-xs leading-5 text-slate-600 dark:border-slate-700 dark:text-slate-300"><p>Calculatorul porneste de la forecastul lunii curente si il transforma intr-o estimare pentru luna target cu sezonalitate, trend, prag minim si cap.</p><p className="mt-2 font-semibold text-slate-800 dark:text-slate-100">Estimare bruta = Forecast luna curenta x Factor sezonier folosit x Ajustare trend.</p><p className="mt-2">Factor sezonier folosit = factor magazin x pondere magazin + factor manager x pondere manager + factor retea x pondere retea. Un magazin stabil foloseste 50% / 30% / 20%; istoricul slab muta greutatea spre manager si retea.</p><p className="mt-2">In modul Anul trecut se compara luna target cu luna baza din Y-1. In modul Multi-year se folosesc pana la 3 ani, cu pondere mai mare pentru anii recenti; anii fara date suficiente sunt sariti automat.</p><p className="mt-2">Daca luna curenta este partiala, vanzarile sunt forecastate din importul disponibil si folosite ca baza curenta. Propunerea finala distribuie targetul total top-down proportional cu estimarile brute, apoi aplica pragul minim, cap-ul operational si rotunjirea. Valoarea Final manager ramane decizia editabila si trebuie sa insumeze targetul total la finalizare.</p></div>}
      </div>
      <p className="text-xs text-slate-500 dark:text-slate-400">Ultima luna cu vanzari: <strong>{monthLabel(context.latest_sales_month)}</strong>. Pentru noul target, cohorta curenta contine <strong>{context.active_store_count}</strong> magazine active. Magazinele fara vanzari in luna cohortei nu vor fi publicate in targetul final.</p>
    </div>
  );
}
