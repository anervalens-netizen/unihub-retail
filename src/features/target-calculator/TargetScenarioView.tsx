import { type Dispatch, type RefObject, type SetStateAction } from 'react';
import { AlertTriangle } from 'lucide-react';

import type { TargetCalculatorContext, TargetScenario, TargetScenarioRow } from '../../api/targetCalculator';
import { formatCurrency } from '../../lib/formatters';
import { TargetWorkflow } from './TargetWorkflow';
import { TargetAgentDetails } from './TargetAgentDetails';
import { TargetAllocationTable } from './TargetAllocationTable';
import { TargetConfiguration } from './TargetConfiguration';
import { TargetRegionalOverview } from './TargetRegionalOverview';
import { TargetStoreAllocation } from './TargetStoreAllocation';
import { monthLabel } from './model';
import type { SeasonalityMode } from '../../components/SeasonalityControl';

function SummaryCard({ label, value, detail, emphasis, grouped = false }: {
  label: string;
  value: string;
  detail?: string;
  emphasis?: 'good' | 'warning' | 'attention';
  grouped?: boolean;
}) {
  const color = emphasis === 'good'
    ? 'text-emerald-600 dark:text-emerald-400'
    : emphasis === 'warning'
      ? 'text-amber-600 dark:text-amber-400'
      : emphasis === 'attention'
        ? 'text-amber-700 dark:text-amber-300'
      : 'text-slate-900 dark:text-slate-100';
  const surface = grouped
    ? 'min-w-0 p-3'
    : emphasis === 'attention'
    ? 'rounded-2xl border border-amber-300 bg-amber-50/80 p-4 min-w-0 dark:border-amber-700 dark:bg-amber-950/20'
    : 'glass rounded-2xl p-4 min-w-0';
  return (
    <div className={surface}>
      <p className="text-[11px] font-medium uppercase tracking-wide text-slate-400">{label}</p>
      <p className={`mt-1 break-words font-bold tabular-nums ${grouped ? 'text-base sm:text-lg xl:text-xl' : 'text-xl'} ${color}`}>{value}</p>
      {detail && <p className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">{detail}</p>}
    </div>
  );
}

export type TargetAllocationViewRow = {
  manager: string;
  storeCount: number;
  targetShare: number;
  targetVsPreviousSharePp: number | null;
  target: number;
  targetVsPreviousPct: number | null;
  targetVsSeasonalPct: number | null;
  targetVsPreviousYearPct: number | null;
  targetVsForecastPct: number | null;
  signal: string;
};

export type TargetRegionalViewRow = {
  regional: string;
  store_count: number;
  proposed_total: number;
  final_total: number;
  current_month: string | null;
  current_forecast_total: number;
  proposed_growth_vs_current_pct: number | null;
  last_year_base_month: string | null;
  last_year_target_month: string | null;
  last_year_base_total: number;
  last_year_target_total: number;
  last_year_growth_pct: number | null;
};

export type TargetSourceViewRow = {
  month: string;
  target: number;
  realized: number;
  actualRealized: number;
  isForecast: boolean;
  showTarget: boolean;
};

type TargetTableTotals = {
  history: Array<{ month: string; target: number; realized: number; attainment: number | null }>;
  normalizedWeight: number;
  proposedTarget: number;
  finalTarget: number | null;
  salary: number;
  operatingCosts: number | null;
  breakEven: number | null;
  forecast: number | null;
};

export interface TargetScenarioViewProps {
  workflowStep: 1 | 2 | 3 | 4;
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
  error: string | null;
  conflictRetryAvailable: boolean;
  scenario: TargetScenario | null;
  savingRows: Set<string>;
  dirty: boolean;
  displayWarnings: string[];
  activeSeasonalityLabel: string;
  regionalChart: TargetRegionalViewRow[];
  sourceChart: TargetSourceViewRow[];
  isDesktop: boolean;
  regionalFilter: string;
  setRegionalFilter: (value: string) => void;
  regionals: string[];
  regionalAllocation: TargetAllocationViewRow[];
  filteredRows: TargetScenarioRow[];
  resetToProposal: () => void;
  handleSave: () => Promise<void>;
  handleFinalize: () => Promise<void>;
  handleExport: () => Promise<void>;
  profitabilitySummary: TargetScenario['profitability_summary'];
  locationFilterRef: RefObject<HTMLDivElement | null>;
  locationDropdownOpen: boolean;
  setLocationDropdownOpen: Dispatch<SetStateAction<boolean>>;
  selectedLocationCodes: string[];
  selectedLocationSet: Set<string>;
  setSelectedLocationCodes: Dispatch<SetStateAction<string[]>>;
  locationOptions: TargetScenarioRow[];
  toggleLocationFilter: (siteCode: string) => void;
  removeLocationFilter: (siteCode: string) => void;
  displaySourceMonths: Array<{ month: string; label: string; role: string }>;
  tableTotals: TargetTableTotals;
  updateRow: (siteCode: string, field: 'final_target' | 'note', value: number | string | null) => void;
  detailSiteCode: string | null;
  setDetailSiteCode: Dispatch<SetStateAction<string | null>>;
}

export function TargetErrorNotice({
  error,
  conflictRetryAvailable,
  busy,
  dirty,
  onRetry,
}: {
  error: string;
  conflictRetryAvailable: boolean;
  busy: boolean;
  dirty: boolean;
  onRetry: () => void;
}) {
  return (
    <div role="alert" className="flex flex-wrap items-center gap-2 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-900/20 dark:text-red-300">
      <AlertTriangle size={15} />
      <span className="flex-1">{error}</span>
      {conflictRetryAvailable && (
        <button
          type="button"
          onClick={onRetry}
          disabled={busy || !dirty}
          className="rounded-xl bg-red-100 px-3 py-1.5 text-xs font-semibold text-red-800 hover:bg-red-200 disabled:opacity-50 dark:bg-red-900/40 dark:text-red-100 dark:hover:bg-red-900/60"
        >
          Reîncearcă salvarea
        </button>
      )}
    </div>
  );
}

export function TargetScenarioView(props: TargetScenarioViewProps) {
  const {
    workflowStep, context, busy, loadInitial, targetMonth, setTargetMonth, totalTarget, setTotalTarget,
    minFloor, setMinFloor, seasonalityMode, selectSeasonalityMode, handleCalculate, logicOpen,
    setLogicOpen, error, conflictRetryAvailable, scenario, savingRows, dirty, displayWarnings,
    activeSeasonalityLabel, regionalFilter, setRegionalFilter, regionals, regionalAllocation, handleSave,
    detailSiteCode, setDetailSiteCode,
  } = props;

  return (
    <div className="p-4 lg:p-6 space-y-4">
      <TargetWorkflow step={workflowStep} />
      <TargetConfiguration
        context={context} busy={busy} loadInitial={loadInitial} targetMonth={targetMonth}
        setTargetMonth={setTargetMonth} totalTarget={totalTarget} setTotalTarget={setTotalTarget}
        minFloor={minFloor} setMinFloor={setMinFloor} seasonalityMode={seasonalityMode}
        selectSeasonalityMode={selectSeasonalityMode} handleCalculate={handleCalculate}
        logicOpen={logicOpen} setLogicOpen={setLogicOpen}
      />
      {error && <TargetErrorNotice error={error} conflictRetryAvailable={conflictRetryAvailable} busy={busy} dirty={dirty} onRetry={() => void handleSave()} />}
      {scenario && (
        <div className="sticky top-2 z-20 flex flex-wrap items-center gap-3 rounded-2xl border border-slate-200 bg-white/95 px-4 py-3 shadow-sm backdrop-blur-xl dark:border-slate-700 dark:bg-slate-900/95">
          <span className="text-xs font-medium text-slate-500 dark:text-slate-400">Target {monthLabel(scenario.target_month)} · revizia {scenario.revision}</span>
          <span className={`rounded-full px-3 py-1 text-xs font-semibold ${scenario.status === 'finalized' ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300' : 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300'}`}>
            {scenario.status === 'finalized' ? 'Finalizat' : savingRows.size > 0 ? 'Se salveaza automat...' : dirty ? 'Modificari in curs...' : 'Salvat în baza de date'}
          </span>
          {scenario.status === 'draft' && <span className="text-xs text-slate-500 dark:text-slate-400">{scenario.pending_final_count} locații de completat · {formatCurrency(scenario.remaining_difference)} rămas de distribuit</span>}
        </div>
      )}
      {scenario && (
        <>
          {displayWarnings.length > 0 && <div className="rounded-2xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800 dark:border-amber-900 dark:bg-amber-900/20 dark:text-amber-300">{displayWarnings.map((warning) => <p key={warning}>{warning}</p>)}</div>}
          <div className="glass grid grid-cols-2 divide-x divide-y divide-slate-200 overflow-hidden rounded-2xl sm:grid-cols-4 sm:divide-y-0 dark:divide-slate-700">
            <SummaryCard grouped label="Target total" value={formatCurrency(scenario.total_target)} detail={monthLabel(scenario.target_month)} />
            <SummaryCard grouped label="Calculat" value={formatCurrency(scenario.proposed_total)} detail={`${scenario.store_count} magazine active · ${activeSeasonalityLabel}`} />
            <SummaryCard grouped label="Final manager" value={formatCurrency(scenario.final_total)} detail={scenario.status === 'draft' ? `${scenario.pending_final_count} necompletate · ${scenario.manual_adjustments_count} ajustari` : 'Publicat in targetele oficiale'} emphasis="attention" />
            <SummaryCard grouped label="Ramas de distribuit" value={formatCurrency(scenario.remaining_difference)} detail="trebuie sa fie 0 la finalizare" emphasis={Math.abs(scenario.remaining_difference) <= 0.01 ? 'good' : 'warning'} />
          </div>
          <TargetRegionalOverview model={props} />
          <div className="glass rounded-2xl p-3">
            <div className="flex flex-wrap items-center gap-2">
              <span className="mr-1 text-xs font-medium text-slate-500 dark:text-slate-400">Manager</span>
              {['all', ...regionals].map((regional) => {
                const active = regionalFilter === regional;
                return (
                  <button
                    key={regional}
                    onClick={() => setRegionalFilter(regional)}
                    className={`rounded-xl px-3 py-2 text-xs font-semibold transition-colors ${
                      active
                        ? 'bg-indigo-600 text-white shadow-sm'
                        : 'bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700'
                    }`}
                  >
                    {regional === 'all' ? 'Toti managerii' : regional}
                  </button>
                );
              })}
            </div>
          </div>
          <TargetAllocationTable regionalAllocation={regionalAllocation} />
          <TargetStoreAllocation model={props} />
        </>
      )}
      {scenario && <TargetAgentDetails scenarioId={scenario.id} siteCode={detailSiteCode} onClose={() => setDetailSiteCode(null)} />}
    </div>
  );
}
