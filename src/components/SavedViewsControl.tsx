import { useCallback, useEffect, useState } from 'react';
import { Bookmark, LoaderCircle, Plus, Trash2 } from 'lucide-react';

import type { SavedViewItem } from '../api/savedViews';
import { buildRetailContextUrl, type RetailContextUrlState } from '../lib/insightDeepLink';

const MODULE_LABELS: Record<SavedViewItem['module_id'], string> = {
  hub: 'Hub', focus: 'Focus', agents: 'Agenți', management: 'Management',
};

/**
 * Transport for personal Saved Views, injected by the shell.
 *
 * This lazy chunk must not import the shared api client itself: when a dynamic
 * chunk becomes an importer of that shared chunk, rolldown folds its
 * CommonJS/ESM interop runtime into it, and that runtime then sits inside the
 * client -> vendor -> charts cycle, so the charts chunk calls
 * `__commonJSMin()` before it is initialised ("TypeError: __commonJSMin is not
 * a function") and the first paint renders nothing.
 */
export interface SavedViewsApi {
  createSavedView: (name: string, state: RetailContextUrlState) => Promise<SavedViewItem>;
  deleteSavedView: (viewId: number) => Promise<void>;
  getApiErrorMessage: (error: unknown, fallback: string) => string;
  listSavedViews: (signal?: AbortSignal) => Promise<SavedViewItem[]>;
  toRetailContextUrlState: (state: SavedViewItem['state']) => RetailContextUrlState;
}

interface SavedViewsControlProps {
  currentState: RetailContextUrlState | null;
  mode: 'desktop' | 'mobile';
  api: SavedViewsApi;
  navigate?: (url: string) => void;
}

function useSavedViewsModel(api: SavedViewsApi, currentState: RetailContextUrlState | null, visible: boolean, navigate?: (url: string) => void) {
  const [attempted, setAttempted] = useState(false);
  const [ready, setReady] = useState(false);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [name, setName] = useState('');
  const [views, setViews] = useState<SavedViewItem[]>([]);
  const [error, setError] = useState('');
  const load = useCallback(async () => {
    setAttempted(true); setLoading(true); setReady(false); setError('');
    try { setViews(await api.listSavedViews()); setReady(true); }
    catch (caught) { setError(api.getApiErrorMessage(caught, 'Vederile salvate nu au putut fi încărcate.')); }
    finally { setLoading(false); }
  }, [api]);
  useEffect(() => { if (visible && !attempted && !loading) void load(); }, [visible, attempted, loading, load]);
  const save = async () => {
    const normalizedName = name.trim();
    if (!normalizedName || saving || loading || !ready || !currentState) return;
    setSaving(true); setError('');
    try {
      const created = await api.createSavedView(normalizedName, currentState);
      setViews((previous) => [created, ...previous.filter((item) => item.id !== created.id)]);
      setName('');
    } catch (caught) { setError(api.getApiErrorMessage(caught, 'Vederea nu a putut fi salvată.')); }
    finally { setSaving(false); }
  };
  const remove = async (view: SavedViewItem) => {
    if (deletingId !== null || !window.confirm(`Ștergi vederea „${view.name}”?`)) return;
    setDeletingId(view.id); setError('');
    try { await api.deleteSavedView(view.id); setViews((previous) => previous.filter((item) => item.id !== view.id)); }
    catch (caught) { setError(api.getApiErrorMessage(caught, 'Vederea nu a putut fi ștearsă.')); }
    finally { setDeletingId(null); }
  };
  const apply = (view: SavedViewItem) => {
    const url = buildRetailContextUrl(api.toRetailContextUrlState(view.state));
    (navigate ?? ((target: string) => window.location.assign(target)))(url);
  };
  return { apply, canSave: currentState !== null, deletingId, error, load, loading, name, ready, remove, save, saving, setName, views };
}

type SavedViewsModel = ReturnType<typeof useSavedViewsModel>;

function SavedViewList({ model }: { model: SavedViewsModel }) {
  if (model.loading || model.views.length === 0) return null;
  return <ul className="max-h-64 overflow-y-auto" aria-label="Vederi salvate">{model.views.map((view) => <li key={view.id} className="flex items-center gap-2 border-b border-slate-100 px-2 py-2 dark:border-slate-800">
    <button type="button" onClick={() => model.apply(view)} aria-label={`Aplică vederea ${view.name}`} className="min-w-0 flex-1 text-left"><span className="block truncate text-xs font-bold">{view.name}</span><span className="block truncate text-[10px] text-slate-500">{MODULE_LABELS[view.module_id]}{view.state.period ? ` · ${view.state.period}` : ''}</span></button>
    <button type="button" onClick={() => { void model.remove(view); }} disabled={model.deletingId !== null} aria-label={`Șterge vederea ${view.name}`} className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-slate-100 text-slate-500 disabled:opacity-50 dark:bg-slate-800">{model.deletingId === view.id ? <LoaderCircle size={14} className="animate-spin" /> : <Trash2 size={14} />}</button>
  </li>)}</ul>;
}

function SavedViewsPanel({ model, mode }: { model: SavedViewsModel; mode: 'desktop' | 'mobile' }) {
  return <div className={mode === 'desktop' ? 'w-80 space-y-3' : 'space-y-3'}>
    {model.canSave ? <form className="flex gap-2" onSubmit={(event) => { event.preventDefault(); void model.save(); }}>
      <label className="min-w-0 flex-1"><span className="sr-only">Numele vederii</span><input value={model.name} onChange={(event) => model.setName(event.target.value)} maxLength={80} placeholder="Nume vedere..." className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-3 py-3 text-xs outline-none dark:border-slate-700 dark:bg-slate-800" /></label>
      <button type="submit" disabled={!model.name.trim() || model.saving || model.loading || !model.ready} className="flex items-center gap-1 rounded-2xl bg-indigo-600 px-4 py-3 text-xs font-bold text-white disabled:opacity-50">{model.saving ? <LoaderCircle size={13} className="animate-spin" /> : <Plus size={13} />}Salvează</button>
    </form> : <p className="text-xs text-slate-500">Contextul curent nu poate fi salvat, dar poți aplica sau șterge vederile existente.</p>}
    {model.error && <div role="alert" className="rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700 dark:border-red-800 dark:bg-red-900/30 dark:text-red-300"><span>{model.error}</span><button type="button" disabled={model.loading} onClick={() => { void model.load(); }} className="ml-2 font-bold underline">Reîncearcă</button></div>}
    {model.loading && <div role="status" className="flex items-center gap-2 py-2 text-xs text-slate-500"><LoaderCircle size={14} className="animate-spin" /> Se încarcă...</div>}
    {!model.loading && model.ready && model.views.length === 0 && !model.error && <p className="py-2 text-xs text-slate-500">Nu ai încă vederi salvate.</p>}
    <SavedViewList model={model} />
  </div>;
}

export function SavedViewsControl({ currentState, mode, api, navigate }: SavedViewsControlProps) {
  const [open, setOpen] = useState(false);
  const model = useSavedViewsModel(api, currentState, mode === 'mobile' || open, navigate);
  if (mode === 'mobile') return <section aria-labelledby="saved-views-mobile-title" className="space-y-2"><div className="flex items-center gap-2"><Bookmark size={15} className="text-indigo-500" /><h3 id="saved-views-mobile-title" className="text-sm font-bold">Vederi salvate</h3></div><SavedViewsPanel model={model} mode={mode} /></section>;
  return <div className="relative"><button type="button" onClick={() => setOpen((current) => !current)} aria-expanded={open} aria-controls="saved-views-desktop-panel" className="flex items-center gap-1.5 rounded-xl border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs font-medium text-slate-600 transition-colors hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-800/60 dark:text-slate-400 dark:hover:bg-slate-700/60"><Bookmark size={13} />Vederi</button>{open && <div id="saved-views-desktop-panel" className="absolute right-0 top-full z-50 mt-2 w-80 rounded-2xl bg-white p-4 shadow-2xl dark:bg-slate-900"><SavedViewsPanel model={model} mode={mode} /></div>}</div>;
}
