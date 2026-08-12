import { useEffect, useRef, useState, type ReactNode } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { ChevronDown, ChevronRight, ExternalLink, RefreshCw } from 'lucide-react';

import { refreshGrileStore, type GrileStore } from '../../api/grile';
import { cn } from '../../lib/utils';
import { FirmaBadge } from '../FirmaBadge';
import { RefreshStatusError } from './RefreshStatusError';
import { formatGrileDifference, formatGrileNumber, relativeGrileTime } from './grileFormatting';

const GRID_COLS = 'grid-cols-[minmax(240px,1.7fr)_96px_76px_1fr_1fr_112px] gap-2';
const DESKTOP_ROW = `hidden lg:grid ${GRID_COLS}`;

function businessStatusInfo(store: GrileStore) {
  const rose = 'bg-rose-100 text-rose-700 dark:bg-rose-900/40 dark:text-rose-300';
  const amber = 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300';
  const slate = 'bg-slate-200 text-slate-600 dark:bg-slate-700 dark:text-slate-300';
  const emerald = 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300';
  if (store.fill_status === null && store.target_status === null && store.sales_status === null) return { label: 'Fără rezultat', cls: slate };
  if (store.fill_status === 'NECOMPLETAT') return { label: 'Necompletat', cls: slate };
  const targetDiff = store.target_status === 'DIFERENTA';
  const salesDiff = store.sales_status === 'DIFERENTA';
  const behind = store.sales_status === 'IN_URMA';
  if (targetDiff && (salesDiff || behind)) return { label: 'Target + Realizat', cls: rose };
  if (targetDiff) return { label: 'Target', cls: rose };
  if (salesDiff) return { label: 'Realizat', cls: rose };
  if (behind) return { label: 'În urmă', cls: amber };
  return { label: 'OK', cls: emerald };
}

function providerStatusInfo(store: GrileStore) {
  const rose = 'bg-rose-50 text-rose-700 ring-1 ring-rose-200 dark:bg-rose-950/30 dark:text-rose-300 dark:ring-rose-800';
  const amber = 'bg-amber-50 text-amber-700 ring-1 ring-amber-200 dark:bg-amber-950/30 dark:text-amber-300 dark:ring-amber-800';
  const slate = 'bg-slate-100 text-slate-600 ring-1 ring-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:ring-slate-700';
  if (store.provider_status.state === 'error') return { label: 'Google: eroare', cls: rose };
  if (store.provider_status.state === 'stale') return { label: 'Google: vechi', cls: amber };
  if (store.provider_status.state === 'unknown') return { label: 'Google: neverificat', cls: slate };
  return null;
}

function useStoreRowModel(store: GrileStore, month: string) {
  const [open, setOpen] = useState(false);
  const queryClient = useQueryClient();
  const refreshController = useRef<AbortController | null>(null);
  useEffect(() => () => refreshController.current?.abort(), []);
  const refresh = useMutation({
    mutationFn: () => {
      refreshController.current?.abort();
      const controller = new AbortController();
      refreshController.current = controller;
      return refreshGrileStore(month, store.site_code, controller.signal);
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['grile-overview', month] }),
    onSettled: () => { refreshController.current = null; },
  });
  const missing = store.missing_days ?? [];
  const providerError = store.provider_status.last_error_message;
  return {
    open, toggle: () => setOpen((value) => !value), refresh, missing, providerError,
    hasDetail: missing.length > 0 || !!providerError || store.completion_window_status === 'legacy_incomplete_window',
    businessStatus: businessStatusInfo(store), providerStatus: providerStatusInfo(store),
  };
}

type StoreModel = ReturnType<typeof useStoreRowModel>;

export function StoreRow({ s, month }: { s: GrileStore; month: string }) {
  const model = useStoreRowModel(s, month);
  return <div className="border-t border-slate-100 dark:border-slate-800">
    <StoreRowMobile store={s} model={model} />
    <StoreRowDesktop store={s} model={model} />
    <StoreRowDetails store={s} model={model} />
  </div>;
}

function StoreRowMobile({ store, model }: { store: GrileStore; model: StoreModel }) {
  return <div className="px-3 py-2.5 lg:hidden">
    <div className="flex items-center justify-between gap-2"><div className="flex min-w-0 items-center gap-1"><FirmaBadge firma={store.firma} /><StoreIdentity store={store} /><RefreshButton store={store} model={model} /></div><div className="flex-shrink-0"><StatusBadges store={store} model={model} /></div></div>
    {model.refresh.data && <div className="mt-1 text-[10px] text-slate-400">Verificare finalizată: {model.refresh.data.projection_applied ? 'datele curente au fost actualizate' : 'observația nu a înlocuit o generație mai nouă'}</div>}
    {model.refresh.isError && <RefreshStatusError error={model.refresh.error} />}
    <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-2">
      <MobileField label="Completare"><CompletionBadge pct={store.completion_pct} model={model} /></MobileField>
      <MobileField label="Editat"><span className="text-xs text-slate-500">{relativeGrileTime(store.last_edit)}</span></MobileField>
      <MobileField label="Verificat"><span className="text-xs text-slate-500">{relativeGrileTime(store.provider_status.last_attempt_at)}</span></MobileField>
      <MobileField label="Target"><DiffCell status={store.target_status} grila={store.grila_target} db={store.db_target} diff={store.target_diff} /></MobileField>
      <MobileField label="Realizat"><DiffCell status={store.sales_status} grila={store.grila_sales} db={store.db_sales_mtd} diff={store.sales_diff} /></MobileField>
    </div>
  </div>;
}

function StoreRowDesktop({ store, model }: { store: GrileStore; model: StoreModel }) {
  return <div className={cn(DESKTOP_ROW, 'items-center px-4 py-2 text-sm transition-colors hover:bg-slate-50/80 dark:hover:bg-slate-800/30')}>
    <div className="flex items-center gap-1 truncate"><FirmaBadge firma={store.firma} /><StoreIdentity store={store} /><RefreshButton store={store} model={model} />{model.refresh.data && <span className="flex-shrink-0 text-[10px] text-slate-400">{model.refresh.data.projection_applied ? 'actualizată' : 'depășită'}</span>}{model.refresh.isError && <RefreshStatusError error={model.refresh.error} compact />}</div>
    <div className="flex items-center justify-center gap-1"><CompletionBadge pct={store.completion_pct} model={model} /></div>
    <div className="text-center text-xs text-slate-400">{relativeGrileTime(store.last_edit)}</div>
    <div><DiffCell status={store.target_status} grila={store.grila_target} db={store.db_target} diff={store.target_diff} /></div>
    <div><DiffCell status={store.sales_status} grila={store.grila_sales} db={store.db_sales_mtd} diff={store.sales_diff} /></div>
    <div><StatusBadges store={store} model={model} /></div>
  </div>;
}

function StoreRowDetails({ store, model }: { store: GrileStore; model: StoreModel }) {
  if (!model.open || !model.hasDetail) return null;
  return <div className="bg-slate-50 px-3 py-2 text-xs text-slate-600 lg:pl-9 dark:bg-slate-800/40 dark:text-slate-300">
    {model.missing.length > 0 && <div><span className="font-semibold">Zile necompletate ({model.missing.length}):</span>{' '}{model.missing.join(', ')}</div>}
    {model.providerError && <div className="mt-1 text-rose-500">Ultima încercare Google: {model.providerError}</div>}
    {store.completion_window_status === 'legacy_incomplete_window' && <div className="mt-1 text-amber-600 dark:text-amber-300">Completarea provine din algoritmul vechi și trebuie recalculată pentru această lună.</div>}
  </div>;
}

function StoreIdentity({ store }: { store: GrileStore }) {
  if (!store.sheet_id) return <span className="truncate font-medium text-slate-700 dark:text-slate-200">{store.locatie}</span>;
  return <a href={`https://docs.google.com/spreadsheets/d/${store.sheet_id}`} target="_blank" rel="noreferrer" title="Deschide grila" className="group inline-flex min-w-0 items-center gap-1 truncate font-medium text-slate-700 hover:text-indigo-600 hover:underline dark:text-slate-200 dark:hover:text-indigo-400"><span className="truncate">{store.locatie}</span><ExternalLink className="h-3 w-3 flex-shrink-0 opacity-60 group-hover:opacity-100" /></a>;
}

function RefreshButton({ store, model }: { store: GrileStore; model: StoreModel }) {
  return <button type="button" onClick={() => model.refresh.mutate()} disabled={model.refresh.isPending} title={`Verifică doar ${store.locatie}`} aria-label={`Reîmprospătează grila ${store.locatie}`} className="inline-flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-lg text-slate-400 transition-colors hover:bg-indigo-50 hover:text-indigo-600 disabled:cursor-wait disabled:opacity-60 dark:hover:bg-indigo-950/40 dark:hover:text-indigo-300"><RefreshCw className={cn('h-3.5 w-3.5', model.refresh.isPending && 'animate-spin')} /></button>;
}

function StatusBadges({ store, model }: { store: GrileStore; model: StoreModel }) {
  return <div className="flex flex-wrap items-center justify-end gap-1">
    <span className={cn('rounded px-1.5 py-0.5 text-[11px] font-semibold', model.businessStatus.cls)}>{model.businessStatus.label}</span>
    {model.providerStatus && <span className={cn('rounded px-1.5 py-0.5 text-[10px] font-semibold', model.providerStatus.cls)}>{model.providerStatus.label}</span>}
    {store.completion_window_status === 'legacy_incomplete_window' && <span className="rounded bg-amber-50 px-1.5 py-0.5 text-[10px] font-semibold text-amber-700 ring-1 ring-amber-200 dark:bg-amber-950/30 dark:text-amber-300 dark:ring-amber-800">completare legacy</span>}
  </div>;
}

function DiffCell({ status, grila, db, diff }: { status: string | null; grila: number | null; db: number | null; diff: number | null }) {
  if (status === null || status === 'NECOMPLETAT') return <span className="text-xs text-slate-400">—</span>;
  if (status === 'OK') return <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-[11px] font-semibold text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300">OK</span>;
  return <div className="text-xs leading-tight"><div className={cn('font-bold', status === 'IN_URMA' ? 'text-amber-600' : 'text-rose-500')}>{formatGrileDifference(diff)}</div><div className="text-[11px] text-slate-400">Raport {formatGrileNumber(db)}</div><div className="text-[11px] text-slate-400">Grilă {formatGrileNumber(grila)}</div></div>;
}

function CompletionBadge({ pct, model }: { pct: number | null; model: StoreModel }) {
  if (pct === null) return <span className="text-slate-400">—</span>;
  return <button onClick={() => model.hasDetail && model.toggle()} className={cn('inline-flex items-center gap-0.5 rounded px-1.5 py-0.5 text-[11px] font-semibold', model.hasDetail && 'cursor-pointer hover:ring-1 hover:ring-slate-300', pct >= 80 ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300' : pct >= 50 ? 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300' : 'bg-rose-100 text-rose-700 dark:bg-rose-900/40 dark:text-rose-300')}>{pct}%{model.hasDetail && (model.open ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />)}</button>;
}

function MobileField({ label, children }: { label: string; children: ReactNode }) {
  return <div className="flex flex-col gap-0.5"><span className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">{label}</span><div>{children}</div></div>;
}

export function DesktopTableHeader() {
  return <div className={cn(DESKTOP_ROW, 'sticky top-2 z-10 items-center rounded-xl border border-slate-200 bg-slate-100 px-4 py-2 text-xs font-bold uppercase tracking-[0.04em] text-slate-600 shadow-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300')}><span>Magazin / structură</span><span className="text-center">Completare</span><span className="text-center">Editat</span><span>Target</span><span>Realizat</span><span>Status</span></div>;
}
