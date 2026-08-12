import { ChevronDown } from 'lucide-react';

import { MAX_DASHBOARD_BATCH_MONTHS } from '../../api/dashboard';
import { Metric } from '../../components/common/DataDisplay';
import { formatAmount, formatInt, formatPercent } from '../../lib/formatters';
import { CompactCurrency, KpiPerformanceCard, getBon2AccTone, getFocusTone } from './DashboardWidgets';
import type { HistoryDashboardProps, HistoryPointView } from './HistoryDashboard';

type SummaryProps = Pick<HistoryDashboardProps<string, string, string>,
  'includeClosedStores' | 'onIncludeClosedStoresChange' | 'dropdownRef' | 'onDropdownToggle'
  | 'dropdownOpen' | 'draftSelectionLabel' | 'selectionLabel' | 'months' | 'draftSelectedMonths'
  | 'onToggleMonth' | 'onApplyMonths' | 'onApplyPreset' | 'historySummary' | 'historyStatusLabel'
  | 'historyReceiptBucketChartData' | 'historyFocusSubcategoryChartData'>;

export function HistorySelection({ props, visible }: { props: SummaryProps; visible: boolean }) {
  return <div className={`glass relative z-50 rounded-3xl p-4 ${!visible ? 'hidden lg:block' : ''}`}>
    <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
      <div>
        <h3 className="text-sm font-bold">Luni analizate</h3>
        <p className="text-[11px] text-slate-500">Alege un interval rapid sau bifează lunile; rezultatele se agregă automat.</p>
        <div className="mt-2 flex flex-wrap gap-1.5" aria-label="Intervale rapide">
          {[3, 6, 12].map((count) => <button key={count} type="button" onClick={() => props.onApplyPreset?.(count)} className="rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-xs font-semibold text-slate-600 hover:border-indigo-300 hover:text-indigo-600 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300">Ultimele {count} luni</button>)}
        </div>
      </div>
      <div className="flex flex-wrap items-start gap-2">
        <label className="flex items-center gap-2 rounded-2xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-semibold text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
          <input type="checkbox" checked={props.includeClosedStores} onChange={(event) => props.onIncludeClosedStoresChange(event.target.checked)} className="h-3.5 w-3.5 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500" />
          Include magazine inchise
        </label>
        <details ref={props.dropdownRef} onToggle={props.onDropdownToggle} className="group relative z-50">
          <summary className="flex min-w-60 cursor-pointer list-none items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-semibold outline-none transition-colors hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-800 dark:hover:bg-slate-700">
            <span className="truncate">{props.dropdownOpen ? props.draftSelectionLabel : props.selectionLabel}</span>
            <ChevronDown size={14} className="shrink-0 text-slate-400 transition-transform group-open:rotate-180" />
          </summary>
          <div className="absolute right-0 z-[100] mt-2 w-64 rounded-2xl border border-slate-200 bg-white p-2 shadow-xl dark:border-slate-700 dark:bg-slate-900">
            <div className="max-h-72 overflow-auto pr-1">{props.months.map((month) => <MonthOption key={month} month={month} props={props} />)}</div>
            <div className="mt-2 flex items-center justify-between border-t border-slate-100 pt-2 dark:border-slate-800">
              <span className="text-[10px] font-semibold text-slate-400">{props.draftSelectedMonths.length}/{MAX_DASHBOARD_BATCH_MONTHS} selectate</span>
              <button type="button" onClick={props.onApplyMonths} className="rounded-xl bg-indigo-600 px-3 py-1.5 text-xs font-bold text-white shadow-sm transition-colors hover:bg-indigo-700">OK</button>
            </div>
          </div>
        </details>
      </div>
    </div>
    <p className="mt-3 rounded-xl bg-indigo-50 px-3 py-2 text-xs text-indigo-700 dark:bg-indigo-950/30 dark:text-indigo-300">Implicit, comparația păstrează doar magazinele active în cohorta curentă. Activează „Include magazine închise” pentru o vedere istorică completă.</p>
  </div>;
}

function MonthOption({ month, props }: { month: string; props: SummaryProps }) {
  const checked = props.draftSelectedMonths.includes(month);
  const disabled = !checked && props.draftSelectedMonths.length >= MAX_DASHBOARD_BATCH_MONTHS;
  return <label className={`flex items-center gap-2 rounded-xl px-2.5 py-2 text-xs font-semibold transition-colors ${disabled ? 'cursor-not-allowed opacity-40' : 'cursor-pointer'} ${checked ? 'bg-indigo-50 text-indigo-700 dark:bg-indigo-950/50 dark:text-indigo-300' : 'text-slate-600 hover:bg-slate-50 dark:text-slate-300 dark:hover:bg-slate-800'}`}>
    <input type="checkbox" checked={checked} disabled={disabled} onChange={() => props.onToggleMonth(month)} className="h-3.5 w-3.5 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500" />
    <span>{month}</span>
  </label>;
}

export function HistorySummary({ props, selectedPoint, visible }: { props: SummaryProps; selectedPoint: HistoryPointView; visible: boolean }) {
  const summary = props.historySummary;
  const totalReceipts = summary?.total_receipts ?? selectedPoint.total_receipts;
  return <div className={`glass min-w-0 space-y-3 rounded-3xl p-4 ${!visible ? 'hidden lg:block' : ''}`}>
    <div className="flex items-start justify-between gap-2"><div className="min-w-0"><h3 className="truncate text-sm font-bold">Overview — {props.selectionLabel}</h3><p className="mt-0.5 text-[11px] leading-relaxed text-slate-500">{props.historyStatusLabel}</p></div><span className="shrink-0 rounded-xl bg-slate-100 px-2.5 py-1 text-[11px] font-semibold text-slate-600 dark:bg-slate-800 dark:text-slate-300">{summary?.last_sale_date ?? '-'}</span></div>
    <div className="grid min-w-0 items-start gap-3 min-[1500px]:grid-cols-[minmax(0,2fr)_minmax(520px,1.5fr)]">
      <div className="min-w-0 rounded-2xl bg-slate-50 p-3 dark:bg-slate-800/50">
        <div className="mb-3 grid grid-cols-3 gap-2 text-center">
          <div><div className="text-[10px] font-semibold uppercase tracking-wide text-slate-600 dark:text-slate-300">Target</div><div className="mt-0.5 text-[13px] font-bold text-slate-600 dark:text-slate-300"><CompactCurrency value={Number(summary?.total_target ?? selectedPoint.total_target)} /></div></div>
          <div><div className="text-[10px] font-semibold uppercase tracking-wide text-slate-600 dark:text-slate-300">Realizat</div><div className="mt-0.5 text-[13px] font-bold text-slate-800 dark:text-slate-100"><CompactCurrency value={Number(summary?.total_sales ?? selectedPoint.total_sales)} /></div></div>
          <div><div className="text-[10px] font-semibold uppercase tracking-wide text-indigo-700 dark:text-indigo-300">{summary?.is_month_final === false ? 'Previziune' : 'Realizat %'}</div><div className="mt-0.5 text-[13px] font-bold text-indigo-600 dark:text-indigo-400">{summary?.is_month_final === false ? <CompactCurrency value={Number(summary.forecast_sales ?? summary.total_sales)} /> : formatPercent(summary?.target_progress_pct ?? selectedPoint.target_progress_pct)}</div></div>
        </div>
        <div className="relative h-3 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700">{summary?.is_month_final === false && <div className="absolute inset-y-0 left-0 rounded-full bg-indigo-200 dark:bg-indigo-700" style={{ width: `${Math.min(Number(summary.forecast_target_progress_pct ?? 0), 100)}%` }} />}<div className="absolute inset-y-0 left-0 rounded-full bg-indigo-600" style={{ width: `${Math.min(Number(summary?.target_progress_pct ?? selectedPoint.target_progress_pct ?? 0), 100)}%` }} /></div>
        <div className="mt-1.5 flex justify-between text-[10px] font-semibold"><span className="text-indigo-600">Actual {formatPercent(summary?.target_progress_pct ?? selectedPoint.target_progress_pct)}</span>{summary?.is_month_final === false && <span className="text-slate-600 dark:text-slate-300">Forecast {formatPercent(summary.forecast_target_progress_pct)}</span>}</div>
      </div>
      <div className="grid min-w-0 items-start gap-2.5 xl:grid-cols-2 min-[1500px]:col-start-2 min-[1500px]:row-span-2 min-[1500px]:row-start-1"><KpiPerformanceCard title="Bonuri cu accesorii" value={summary?.proc_bon2acc ?? selectedPoint.proc_bon2acc} tone={getBon2AccTone(Number(summary?.proc_bon2acc ?? selectedPoint.proc_bon2acc ?? 0))} chartData={props.historyReceiptBucketChartData} dataKey="receipt_count" nameKey="bucket" formatValue={formatInt} /><KpiPerformanceCard title="Pondere produse Focus" value={summary?.prc_focus_acc_qty ?? selectedPoint.prc_focus_acc_qty} tone={getFocusTone(Number(summary?.prc_focus_acc_qty ?? selectedPoint.prc_focus_acc_qty ?? 0))} chartData={props.historyFocusSubcategoryChartData} dataKey="quantity_total" nameKey="category" formatValue={formatInt} /></div>
      <div className="grid min-w-0 gap-2 [grid-template-columns:repeat(auto-fit,minmax(min(100%,78px),1fr))] min-[1500px]:col-start-1 min-[1500px]:row-start-2">
        <Metric label="Bonuri" value={formatInt(totalReceipts)} className="p-2" /><Metric label="Accesorii nete" value={formatInt(summary?.total_quantity ?? selectedPoint.total_quantity)} className="p-2" /><Metric label="Magazine / Agenți" value={<span className="flex items-baseline gap-1.5"><span>{formatInt(summary?.total_stores ?? selectedPoint.total_stores)}</span><span className="text-slate-300 dark:text-slate-600">/</span><span>{formatInt(summary?.total_agents ?? selectedPoint.total_agents)}</span></span>} className="p-2" /><Metric label="Zile lucrate" value={formatInt(summary?.working_days ?? selectedPoint.working_days)} className="p-2" /><Metric label="Med. zilnica" value={formatAmount(summary?.daily_average ?? selectedPoint.daily_average ?? 0)} className="p-2" /><Metric label="Medie produs" value={formatAmount(summary?.medie_produs ?? selectedPoint.medie_produs ?? 0)} className="p-2" /><Metric label="Val. medie bon" value={formatAmount(totalReceipts > 0 ? Number(summary?.total_sales ?? selectedPoint.total_sales) / Number(totalReceipts) : 0)} className="p-2" /><Metric label="Cartele" value={formatInt(summary?.cartele_qty ?? 0)} className="p-2" />
      </div>
    </div>
  </div>;
}
