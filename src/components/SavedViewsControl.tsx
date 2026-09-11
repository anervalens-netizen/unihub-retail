import { useCallback, useEffect, useState } from 'react';
import { Bookmark, LoaderCircle, Plus, Trash2 } from 'lucide-react';

import {
  createSavedView,
  deleteSavedView,
  listSavedViews,
  toRetailContextUrlState,
  type SavedViewItem,
} from '../api/savedViews';
import { getApiErrorMessage } from '../api/client';
import { buildRetailContextUrl, type RetailContextUrlState } from '../lib/insightDeepLink';
import { cn } from '../lib/utils';

const MODULE_LABELS: Record<SavedViewItem['module_id'], string> = {
  hub: 'Hub',
  focus: 'Focus',
  agents: 'Agenți',
  management: 'Management',
};

interface SavedViewsControlProps {
  currentState: RetailContextUrlState | null;
  mode: 'desktop' | 'mobile';
  navigate?: (url: string) => void;
}

function useSavedViewsModel(
  currentState: RetailContextUrlState | null,
  visible: boolean,
  navigate?: (url: string) => void,
) {
  const [loaded, setLoaded] = useState(false);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [name, setName] = useState('');
  const [views, setViews] = useState<SavedViewItem[]>([]);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      setViews(await listSavedViews());
    } catch (caught) {
      setError(getApiErrorMessage(caught, 'Vederile salvate nu au putut fi încărcate.'));
    } finally {
      setLoaded(true);
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (visible && !loaded && !loading) void load();
  }, [visible, loaded, loading, load]);

  const save = async () => {
    const normalizedName = name.trim();
    if (!normalizedName || saving || !currentState) return;
    setSaving(true);
    setError('');
    try {
      const created = await createSavedView(normalizedName, currentState);
      setViews((previous) => [created, ...previous.filter((item) => item.id !== created.id)]);
      setName('');
      setLoaded(true);
    } catch (caught) {
      setError(getApiErrorMessage(caught, 'Vederea nu a putut fi salvată.'));
    } finally {
      setSaving(false);
    }
  };

  const remove = async (view: SavedViewItem) => {
    if (deletingId !== null || !window.confirm(`Ștergi vederea „${view.name}”?`)) return;
    setDeletingId(view.id);
    setError('');
    try {
      await deleteSavedView(view.id);
      setViews((previous) => previous.filter((item) => item.id !== view.id));
    } catch (caught) {
      setError(getApiErrorMessage(caught, 'Vederea nu a putut fi ștearsă.'));
    } finally {
      setDeletingId(null);
    }
  };

  const apply = (view: SavedViewItem) => {
    const url = buildRetailContextUrl(toRetailContextUrlState(view.state));
    (navigate ?? ((target: string) => window.location.assign(target)))(url);
  };

  return {
    apply, deletingId, error, loaded, loading, name, remove, save, saving, setName, views,
  };
}

type SavedViewsModel = ReturnType<typeof useSavedViewsModel>;

function SavedViewList({ model }: { model: SavedViewsModel }) {
  if (model.loading || model.views.length === 0) return null;
  return (
    <ul className="max-h-64 space-y-1 overflow-y-auto" aria-label="Vederi salvate">
      {model.views.map((view) => (
        <li key={view.id} className="flex items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 p-2 dark:border-slate-700 dark:bg-slate-800/70">
          <button
            type="button"
            onClick={() => model.apply(view)}
            aria-label={`Aplică vederea ${view.name}`}
            className="min-w-0 flex-1 text-left"
          >
            <span className="block truncate text-xs font-bold text-slate-800 dark:text-slate-100">{view.name}</span>
            <span className="block truncate text-[10px] text-slate-500 dark:text-slate-400">
              {MODULE_LABELS[view.module_id]}{view.state.period ? ` · ${view.state.period}` : ''}
            </span>
          </button>
          <button
            type="button"
            onClick={() => { void model.remove(view); }}
            disabled={model.deletingId !== null}
            aria-label={`Șterge vederea ${view.name}`}
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-slate-400 hover:bg-red-50 hover:text-red-600 disabled:opacity-50 dark:hover:bg-red-950/30"
          >
            {model.deletingId === view.id ? <LoaderCircle size={14} className="animate-spin" /> : <Trash2 size={14} />}
          </button>
        </li>
      ))}
    </ul>
  );
}

function SavedViewsPanel({ model, mode }: { model: SavedViewsModel; mode: 'desktop' | 'mobile' }) {
  return (
    <div className={cn(mode === 'desktop' && 'w-80', 'space-y-3')}>
      <form
        className="flex gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          void model.save();
        }}
      >
        <label className="min-w-0 flex-1">
          <span className="sr-only">Numele vederii</span>
          <input
            value={model.name}
            onChange={(event) => model.setName(event.target.value)}
            maxLength={80}
            placeholder="Nume vedere..."
            className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs outline-none focus:border-indigo-400 dark:border-slate-700 dark:bg-slate-900"
          />
        </label>
        <button
          type="submit"
          disabled={!model.name.trim() || model.saving}
          className="flex items-center gap-1 rounded-xl bg-indigo-600 px-3 py-2 text-xs font-bold text-white disabled:cursor-not-allowed disabled:opacity-50"
        >
          {model.saving ? <LoaderCircle size={13} className="animate-spin" /> : <Plus size={13} />}
          Salvează
        </button>
      </form>
      {model.error && <div role="alert" className="rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-300">{model.error}</div>}
      {model.loading && <div role="status" className="flex items-center gap-2 py-2 text-xs text-slate-500"><LoaderCircle size={14} className="animate-spin" /> Se încarcă...</div>}
      {!model.loading && model.loaded && model.views.length === 0 && !model.error && <p className="py-2 text-xs text-slate-500">Nu ai încă vederi salvate.</p>}
      <SavedViewList model={model} />
    </div>
  );
}

export function SavedViewsControl({ currentState, mode, navigate }: SavedViewsControlProps) {
  const [open, setOpen] = useState(false);
  const visible = mode === 'mobile' || open;
  const model = useSavedViewsModel(currentState, visible, navigate);
  if (!currentState) return null;

  if (mode === 'mobile') {
    return (
      <section aria-labelledby="saved-views-mobile-title" className="space-y-2">
        <div className="flex items-center gap-2">
          <Bookmark size={15} className="text-indigo-500" />
          <h3 id="saved-views-mobile-title" className="text-sm font-bold">Vederi salvate</h3>
        </div>
        <SavedViewsPanel model={model} mode={mode} />
      </section>
    );
  }

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        aria-expanded={open}
        aria-controls="saved-views-desktop-panel"
        className="flex items-center gap-1.5 rounded-xl border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs font-medium text-slate-600 transition-colors hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-800/60 dark:text-slate-400 dark:hover:bg-slate-700/60"
      >
        <Bookmark size={13} />
        Vederi
      </button>
      {open && (
        <div id="saved-views-desktop-panel" className="absolute right-0 top-full z-50 mt-2 rounded-2xl border border-slate-200 bg-white p-3 shadow-xl dark:border-slate-700 dark:bg-slate-900">
          <SavedViewsPanel model={model} mode={mode} />
        </div>
      )}
    </div>
  );
}
