import { useState } from 'react';
import type { ReactNode } from 'react';
import { cn } from '../../../lib/utils';
import type { ExportColumnDef } from '../../../api/exports';

export const MONTH_LABELS = [
  'Ianuarie', 'Februarie', 'Martie', 'Aprilie', 'Mai', 'Iunie',
  'Iulie', 'August', 'Septembrie', 'Octombrie', 'Noiembrie', 'Decembrie',
];
export const ALL_DAYS = Array.from({ length: 31 }, (_, index) => index + 1);
export type ExportStep = 1 | 2 | 3 | 4;

export function ExportWorkflow({ step, onChange }: { step: ExportStep; onChange: (step: ExportStep) => void }) {
  const steps: Array<{ value: ExportStep; label: string }> = [
    { value: 1, label: 'Dataset' },
    { value: 2, label: 'Perioadă și scope' },
    { value: 3, label: 'Coloane' },
    { value: 4, label: 'Preview și export' },
  ];
  return (
    <nav aria-label="Pași export Excel" className="glass rounded-2xl p-2">
      <div className="p-1 lg:hidden">
        <div className="mb-2 flex items-center justify-between text-xs font-semibold text-slate-500"><span>Pasul {step} din 4</span><span>{steps[step - 1]?.label ?? ''}</span></div>
        <div className="h-2 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700"><div className="h-full rounded-full bg-indigo-600 transition-all" style={{ width: `${step * 25}%` }} /></div>
      </div>
      <ol className="hidden grid-cols-2 gap-2 lg:grid lg:grid-cols-4">
        {steps.map((item) => (
          <li key={item.value}>
            <button
              type="button"
              onClick={() => onChange(item.value)}
              aria-current={step === item.value ? 'step' : undefined}
              className={cn(
                'flex min-h-10 w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-xs font-bold transition-colors',
                step === item.value
                  ? 'bg-indigo-600 text-white shadow-sm'
                  : item.value < step
                    ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-300'
                    : 'bg-slate-100 text-slate-500 dark:bg-slate-800',
              )}
            >
              <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-white/80 text-slate-700 dark:bg-slate-900 dark:text-slate-200">
                {item.value < step ? '✓' : item.value}
              </span>
              {item.label}
            </button>
          </li>
        ))}
      </ol>
    </nav>
  );
}
export function PeriodSelector({
  years,
  selectedYears,
  onYearToggle,
  monthNumbers,
  selectedMonthNumbers,
  onMonthToggle,
  selectedDays,
  onDayToggle,
  onSelectAllDays,
  onSelectFirstNineDays,
  selectedMonthCount,
}: {
  years: string[];
  selectedYears: string[];
  onYearToggle: (year: string) => void;
  monthNumbers: string[];
  selectedMonthNumbers: string[];
  onMonthToggle: (month: string) => void;
  selectedDays: number[];
  onDayToggle: (day: number) => void;
  onSelectAllDays: () => void;
  onSelectFirstNineDays: () => void;
  selectedMonthCount: number;
}) {
  return (
    <div className="space-y-2 rounded-2xl border border-slate-200 bg-white p-2 dark:border-slate-700 dark:bg-slate-900">
      <div className="grid gap-2 sm:grid-cols-3">
        <PeriodDropdown label="Ani" summary={selectedYears.join(', ')}>
          {years.map((year) => (
            <CheckRow key={year} label={year} checked={selectedYears.includes(year)} onChange={() => onYearToggle(year)} />
          ))}
        </PeriodDropdown>
        <PeriodDropdown
          label="Luni"
          summary={selectedMonthNumbers.length <= 2
            ? selectedMonthNumbers.map((month) => MONTH_LABELS[Number(month) - 1] ?? month).join(', ')
            : `${selectedMonthNumbers.length} selectate`}
        >
          {monthNumbers.map((month) => (
            <CheckRow
              key={month}
              label={MONTH_LABELS[Number(month) - 1] ?? month}
              checked={selectedMonthNumbers.includes(month)}
              onChange={() => onMonthToggle(month)}
            />
          ))}
        </PeriodDropdown>
        <PeriodDropdown label="Zile" summary={selectedDays.length === 31 ? 'Toata luna' : `${selectedDays.length} selectate`}>
          <div className="mb-2 flex gap-1">
            <button type="button" onClick={onSelectAllDays} className="rounded-lg border border-slate-200 px-2 py-1 text-[10px] font-bold dark:border-slate-700">
              Toate
            </button>
            <button type="button" onClick={onSelectFirstNineDays} className="rounded-lg border border-slate-200 px-2 py-1 text-[10px] font-bold dark:border-slate-700">
              Primele 9
            </button>
          </div>
          <div className="grid grid-cols-4 gap-1">
            {ALL_DAYS.map((day) => (
              <CheckRow key={day} label={String(day)} checked={selectedDays.includes(day)} onChange={() => onDayToggle(day)} />
            ))}
          </div>
        </PeriodDropdown>
      </div>
      <div className="text-[11px] font-semibold text-slate-500">
        {selectedMonthCount} luni rezultate · {selectedDays.length === 31 ? 'toate zilele' : `zilele ${selectedDays.join(', ')}`}
      </div>
    </div>
  );
}

export function PeriodDropdown({ label, summary, children }: { label: string; summary: string; children: ReactNode }) {
  return (
    <details className="relative open:z-50 rounded-xl border border-slate-200 bg-slate-50 dark:border-slate-700 dark:bg-slate-800">
      <summary className="cursor-pointer list-none px-2 py-2 text-xs font-bold text-slate-600 dark:text-slate-200">
        <span className="block text-[10px] uppercase text-slate-400">{label}</span>
        <span>{summary}</span>
      </summary>
      <div className="absolute left-0 z-[60] mt-1 max-h-72 min-w-full overflow-auto rounded-xl border border-slate-200 bg-white p-2 shadow-xl dark:border-slate-700 dark:bg-slate-900">
        {children}
      </div>
    </details>
  );
}

export function ModeButton({
  active,
  icon,
  title,
  subtitle,
  onClick,
}: {
  active: boolean;
  icon: ReactNode;
  title: string;
  subtitle: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'flex items-center gap-3 rounded-2xl border px-3 py-3 text-left transition-colors',
        active
          ? 'border-indigo-500 bg-indigo-50 text-indigo-700 dark:border-indigo-400 dark:bg-indigo-950/30 dark:text-indigo-200'
          : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800'
      )}
    >
      <span className={cn(
        'grid h-8 w-8 place-items-center rounded-xl',
        active ? 'bg-indigo-600 text-white' : 'bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-300'
      )}>
        {icon}
      </span>
      <span className="min-w-0">
        <span className="block text-xs font-bold">{title}</span>
        <span className="block truncate text-[11px] opacity-75">{subtitle}</span>
      </span>
    </button>
  );
}

export function FieldBlock({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div>
      <div className="mb-1.5 text-[11px] font-bold uppercase tracking-wide text-slate-400">{title}</div>
      {children}
    </div>
  );
}

export function CheckRow({ label, checked, onChange }: { label: string; checked: boolean; onChange: () => void }) {
  return (
    <label className="flex cursor-pointer items-center gap-2 rounded-xl px-2 py-1.5 text-xs font-semibold text-slate-600 hover:bg-slate-50 dark:text-slate-300 dark:hover:bg-slate-800">
      <input
        type="checkbox"
        checked={checked}
        onChange={onChange}
        className="h-3.5 w-3.5 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
      />
      <span className="truncate">{label}</span>
    </label>
  );
}

export function ColumnBlock({
  title,
  columns,
  selected,
  onToggle,
}: {
  title: string;
  columns: ExportColumnDef[];
  selected: string[];
  onToggle: (key: string) => void;
}) {
  return (
    <details className="mb-2 rounded-2xl border border-slate-200 bg-white p-2 dark:border-slate-700 dark:bg-slate-900">
      <summary className="cursor-pointer text-xs font-bold text-slate-600 dark:text-slate-300">
        {title} · {selected.filter((key) => columns.some((column) => column.key === key)).length}
      </summary>
      <div className="mt-2 grid gap-1 sm:grid-cols-2">
        {columns.map((column) => (
          <CheckRow
            key={column.key}
            label={column.label}
            checked={selected.includes(column.key)}
            onChange={() => onToggle(column.key)}
          />
        ))}
      </div>
    </details>
  );
}

export function LevelBlock({
  levels,
  selected,
  onToggle,
}: {
  levels: Array<{ key: string; label: string }>;
  selected: string[];
  onToggle: (key: string) => void;
}) {
  return (
    <details open className="mb-2 rounded-2xl border border-slate-200 bg-white p-2 dark:border-slate-700 dark:bg-slate-900">
      <summary className="cursor-pointer text-xs font-bold text-slate-600 dark:text-slate-300">
        Niveluri exportate · {selected.length}
      </summary>
      <div className="mt-2 grid gap-1 sm:grid-cols-2">
        {levels.map((level) => (
          <CheckRow
            key={level.key}
            label={level.label}
            checked={selected.includes(level.key)}
            onChange={() => onToggle(level.key)}
          />
        ))}
      </div>
    </details>
  );
}

export function FilterBlock({
  title,
  values,
  selected,
  onToggle,
}: {
  title: string;
  values: Array<string | { key: string; value?: string; label: string }>;
  selected: string[];
  onToggle: (value: string) => void;
}) {
  const [query, setQuery] = useState('');
  const normalized = query.trim().toLowerCase();
  const items = values
    .map((item) => typeof item === 'string' ? { key: item, value: item, label: item } : { ...item, value: item.value ?? item.key })
    .filter((item) => !normalized || item.label.toLowerCase().includes(normalized))
    .slice(0, 80);

  return (
    <details className="mb-2 rounded-2xl border border-slate-200 bg-white p-2 dark:border-slate-700 dark:bg-slate-900">
      <summary className="cursor-pointer text-xs font-bold text-slate-600 dark:text-slate-300">
        {title} · {selected.length}
      </summary>
      <input
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        placeholder="Cauta..."
        className="mt-2 w-full rounded-xl border border-slate-200 bg-slate-50 px-2 py-1.5 text-xs outline-none dark:border-slate-700 dark:bg-slate-800"
      />
      <div className="mt-2 max-h-44 overflow-auto">
        {items.map((item) => (
          <CheckRow
            key={item.key}
            label={item.label}
            checked={selected.includes(item.value)}
            onChange={() => onToggle(item.value)}
          />
        ))}
      </div>
    </details>
  );
}
