import { PnlDataView, PnlFilters, PnlNotices } from '../features/pnl/PnlViews';
import { usePnlController } from '../features/pnl/usePnlController';
import { monthLabel } from '../features/pnl/model';

export { defaultPnlRange, monthLabel, pnlStoreOptionValue } from '../features/pnl/model';

export function PnlSubtab() {
  const model = usePnlController();
  if (model.monthsQuery.isLoading) return <div className="p-8 text-sm text-slate-500">Se încarcă istoricul P&amp;L…</div>;
  if (model.monthsQuery.isError) return <div className="m-6 rounded-xl bg-rose-50 p-4 text-sm text-rose-700">Nu am putut încărca lunile P&amp;L.</div>;
  return (
    <div className="space-y-6 p-4 sm:p-6 lg:space-y-4 lg:p-0">
      <PnlFilters model={model} />
      <div className="sticky top-2 z-20 flex items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-white/95 px-3 py-2 text-xs shadow-sm backdrop-blur-xl dark:border-slate-700 dark:bg-slate-900/95 lg:hidden"><div className="min-w-0"><p className="font-bold text-slate-800 dark:text-slate-100">{monthLabel(model.startMonth)} – {monthLabel(model.endMonth)}</p><p className="truncate text-slate-500">{model.selectedStore?.location ?? (model.regional || model.company || 'Toată rețeaua')}</p></div><span className="shrink-0 rounded-xl bg-indigo-50 px-2 py-1 font-bold text-indigo-700 dark:bg-indigo-950/40 dark:text-indigo-300">P&amp;L</span></div>
      <PnlNotices model={model} />
      {model.overviewQuery.isLoading && <div className="py-16 text-center text-sm text-slate-500">Calculez indicatorii financiari…</div>}
      {model.overviewQuery.isError && <div className="rounded-xl bg-rose-50 p-4 text-sm text-rose-700">Nu am putut încărca raportul P&amp;L.</div>}
      {model.data && <PnlDataView model={model} />}
    </div>
  );
}
