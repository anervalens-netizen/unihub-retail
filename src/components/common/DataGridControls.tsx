import {
  ChevronLeft,
  ChevronRight,
  Columns3,
  RotateCcw,
} from 'lucide-react';
import { useEffect, useRef, type ChangeEvent, type RefObject } from 'react';

import {
  isDataGridFilterActive,
  type DataGridFilters,
  type DataGridFilterValue,
} from '../../lib/dataGrid';
import type { DataGridColumn } from './dataGridTypes';

function parseNumericInput(value: string): number | null {
  if (value.trim() === '') return null;
  const parsed = Number(value.replace(',', '.'));
  return Number.isFinite(parsed) ? parsed : null;
}

export function DataGridFilterControl<Row, Key extends string>({
  column,
  filter,
  onChange,
}: {
  column: DataGridColumn<Row, Key>;
  filter: DataGridFilterValue | undefined;
  onChange: (filter: DataGridFilterValue | undefined) => void;
}) {
  if (!column.filter) return <span aria-hidden="true" />;
  if (column.filter.kind === 'text') {
    return (
      <input
        type="search"
        value={filter?.kind === 'text' ? filter.value : ''}
        onChange={(event: ChangeEvent<HTMLInputElement>) =>
          onChange({ kind: 'text', value: event.target.value })}
        placeholder={column.filter.placeholder ?? 'Filtru'}
        aria-label={`Filtrează ${column.label}`}
        className="w-full min-w-20 rounded-md border border-slate-200 bg-white px-1.5 py-1 text-[11px] font-medium text-slate-700 outline-none focus:border-indigo-400 focus:ring-1 focus:ring-indigo-400 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
      />
    );
  }
  if (column.filter.kind === 'enum') {
    return (
      <select
        value={filter?.kind === 'enum' ? filter.value : ''}
        onChange={(event: ChangeEvent<HTMLSelectElement>) =>
          onChange({ kind: 'enum', value: event.target.value })}
        aria-label={`Filtrează ${column.label}`}
        className="w-full min-w-20 rounded-md border border-slate-200 bg-white px-1 py-1 text-[11px] font-medium text-slate-700 outline-none focus:border-indigo-400 focus:ring-1 focus:ring-indigo-400 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
      >
        <option value="">{column.filter.allLabel ?? 'Toate'}</option>
        {column.filter.options.map((option) => (
          <option key={option.value} value={option.value}>{option.label}</option>
        ))}
      </select>
    );
  }
  const range = filter?.kind === 'number'
    ? filter
    : { kind: 'number' as const, min: null, max: null };
  return (
    <div className="grid min-w-24 grid-cols-2 gap-1">
      <input
        type="number"
        inputMode="decimal"
        step={column.filter.step ?? 'any'}
        value={range.min ?? ''}
        onChange={(event: ChangeEvent<HTMLInputElement>) => onChange({
          ...range,
          min: parseNumericInput(event.target.value),
        })}
        placeholder="min"
        aria-label={`Minim ${column.label}`}
        className="min-w-0 rounded-md border border-slate-200 bg-white px-1 py-1 text-[10px] tabular-nums text-slate-700 outline-none focus:border-indigo-400 focus:ring-1 focus:ring-indigo-400 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
      />
      <input
        type="number"
        inputMode="decimal"
        step={column.filter.step ?? 'any'}
        value={range.max ?? ''}
        onChange={(event: ChangeEvent<HTMLInputElement>) => onChange({
          ...range,
          max: parseNumericInput(event.target.value),
        })}
        placeholder="max"
        aria-label={`Maxim ${column.label}`}
        className="min-w-0 rounded-md border border-slate-200 bg-white px-1 py-1 text-[10px] tabular-nums text-slate-700 outline-none focus:border-indigo-400 focus:ring-1 focus:ring-indigo-400 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
      />
    </div>
  );
}

export function DataGridColumnMenu<Row, Key extends string>({
  columns,
  allKeys,
  order,
  hidden,
  onMove,
  onToggle,
  onReset,
}: {
  columns: ReadonlyMap<Key, DataGridColumn<Row, Key>>;
  allKeys: readonly Key[];
  order: readonly Key[];
  hidden: readonly Key[];
  onMove: (key: Key, offset: -1 | 1) => void;
  onToggle: (key: Key) => void;
  onReset: () => void;
}) {
  const hiddenSet = new Set(hidden);
  const visibleCount = allKeys.filter((key) => !hiddenSet.has(key)).length;
  const customized = hidden.length > 0
    || order.some((key, index) => key !== allKeys[index]);
  return (
    <details className="relative">
      <summary
        data-grid-column-menu-trigger
        className="inline-flex cursor-pointer list-none items-center gap-1 rounded-lg border border-slate-200 bg-white px-2 py-1 text-[11px] font-bold text-slate-600 hover:border-indigo-200 hover:text-indigo-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 [&::-webkit-details-marker]:hidden"
      >
        <Columns3 size={12} />
        Coloane
      </summary>
      <div className="absolute right-0 z-30 mt-2 w-72 rounded-2xl border border-slate-200 bg-white p-2 shadow-xl dark:border-slate-700 dark:bg-slate-950">
        <div className="mb-2 px-1 text-[10px] font-bold uppercase tracking-wide text-slate-400">
          Vizibilitate și ordine
        </div>
        <div className="max-h-80 space-y-1 overflow-y-auto">
          {order.map((key, index) => {
            const column = columns.get(key);
            if (!column) return null;
            const visible = !hiddenSet.has(key);
            const cannotHide = column.hideable === false || (visible && visibleCount <= 1);
            return (
              <div key={key} className="flex items-center gap-2 rounded-lg px-1.5 py-1 hover:bg-slate-50 dark:hover:bg-slate-900">
                <label className="flex min-w-0 flex-1 items-center gap-2 text-xs font-semibold text-slate-700 dark:text-slate-200">
                  <input
                    type="checkbox"
                    checked={visible}
                    disabled={cannotHide}
                    onChange={() => onToggle(key)}
                    aria-label={`Afișează ${column.label}`}
                  />
                  <span className="truncate">{column.label}</span>
                </label>
                <button
                  type="button"
                  onClick={() => onMove(key, -1)}
                  disabled={index === 0}
                  aria-label={`Mută ${column.label} la stânga`}
                  className="rounded p-1 text-slate-500 hover:bg-slate-100 disabled:opacity-30 dark:hover:bg-slate-800"
                >
                  <ChevronLeft size={13} />
                </button>
                <button
                  type="button"
                  onClick={() => onMove(key, 1)}
                  disabled={index === order.length - 1}
                  aria-label={`Mută ${column.label} la dreapta`}
                  className="rounded p-1 text-slate-500 hover:bg-slate-100 disabled:opacity-30 dark:hover:bg-slate-800"
                >
                  <ChevronRight size={13} />
                </button>
              </div>
            );
          })}
        </div>
        {customized && (
          <button
            type="button"
            onClick={onReset}
            className="mt-2 inline-flex w-full items-center justify-center gap-1 rounded-lg border border-slate-200 px-2 py-1.5 text-xs font-bold text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-900"
          >
            <RotateCcw size={12} />
            Resetează coloanele
          </button>
        )}
      </div>
    </details>
  );
}

function hiddenFilterDescription<Row, Key extends string>(
  column: DataGridColumn<Row, Key>,
  filter: DataGridFilterValue,
): string {
  if (filter.kind === 'number') {
    const min = filter.min !== null && Number.isFinite(filter.min) ? filter.min : null;
    const max = filter.max !== null && Number.isFinite(filter.max) ? filter.max : null;
    if (min !== null && max !== null) return `${min} – ${max}`;
    return min !== null ? `≥ ${min}` : `≤ ${max}`;
  }
  if (filter.kind === 'enum' && column.filter?.kind === 'enum') {
    return column.filter.options.find((option) => option.value === filter.value)?.label
      ?? filter.value;
  }
  return filter.value;
}

export function DataGridHiddenFilters<Row, Key extends string>({
  columns,
  hidden,
  filters,
  tableId,
  onClear,
  searchInputRef,
  clearAllRef,
}: {
  columns: readonly DataGridColumn<Row, Key>[];
  hidden: readonly Key[];
  filters: DataGridFilters<Key>;
  tableId: string;
  onClear: (key: Key) => void;
  searchInputRef?: RefObject<HTMLInputElement | null>;
  clearAllRef?: RefObject<HTMLButtonElement | null>;
}) {
  const active = columns.flatMap((column) => {
    const filter = filters[column.key];
    if (!hidden.includes(column.key) || !filter || !isDataGridFilterActive(filter)) return [];
    return [{ key: column.key, label: `${column.label}: ${hiddenFilterDescription(column, filter)}` }];
  });
  const containerRef = useRef<HTMLDivElement>(null);
  const pendingFocusKeyRef = useRef<Key | null>(null);
  const stableFallbackRef = useRef<HTMLElement | null>(null);
  useEffect(() => {
    if (pendingFocusKeyRef.current === null) return;
    const removedKey = pendingFocusKeyRef.current;
    pendingFocusKeyRef.current = null;
    if (active.length === 0) {
      const fallback = clearAllRef?.current
        ?? searchInputRef?.current
        ?? stableFallbackRef.current;
      fallback?.focus();
      return;
    }
    const removedIndex = columns.findIndex((column) => column.key === removedKey);
    const afterRemoved = active.find(({ key }) =>
      columns.findIndex((column) => column.key === key) > removedIndex,
    );
    const successor = afterRemoved ?? active[active.length - 1];
    if (!successor) return;
    const target = containerRef.current?.querySelector<HTMLButtonElement>(
      `button[data-hidden-filter-key="${CSS.escape(successor.key)}"]`,
    );
    target?.focus();
  }, [active, columns, clearAllRef, searchInputRef]);
  if (active.length === 0) return null;
  const handleClear = (key: Key) => {
    pendingFocusKeyRef.current = key;
    stableFallbackRef.current = containerRef.current?.parentElement
      ?.querySelector<HTMLElement>('[data-grid-column-menu-trigger]') ?? null;
    onClear(key);
  };

  return (
    <div
      ref={containerRef}
      role="group"
      aria-label="Filtre pe coloane ascunse"
      className="flex min-w-0 flex-wrap items-center gap-1.5 border-b border-slate-100 px-3 py-2 text-[11px] text-slate-600 dark:border-slate-800 dark:text-slate-300"
    >
      <span>Filtre pe coloane ascunse:</span>
      {active.map(({ key, label }) => (
        <button
          key={key}
          type="button"
          data-hidden-filter-key={key}
          aria-label={`Șterge filtrul ${label}`}
          aria-controls={tableId}
          onClick={() => handleClear(key)}
          className="inline-flex min-w-0 max-w-full items-center gap-1 rounded-lg border border-slate-200 px-2 py-1 text-left font-semibold hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 dark:border-slate-700 dark:hover:bg-slate-800"
        >
          <span className="min-w-0 break-all">{label}</span>
          <RotateCcw size={12} aria-hidden="true" className="shrink-0" />
        </button>
      ))}
    </div>
  );
}
