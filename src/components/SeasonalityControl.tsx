export type SeasonalityMode = 'multi' | 'single' | null;

export function SeasonalityControl({
  value,
  disabled = false,
  onChange,
}: {
  value: SeasonalityMode;
  disabled?: boolean;
  onChange: (value: Exclude<SeasonalityMode, null>) => void;
}) {
  return (
    <div className="space-y-1 text-xs text-slate-500">
      Sezonalitate
      <div className="grid grid-cols-2 rounded-xl border border-slate-200 bg-slate-100 p-1 dark:border-slate-700 dark:bg-slate-800">
        <button
          type="button"
          disabled={disabled}
          aria-pressed={value === 'single'}
          onClick={() => onChange('single')}
          className={`rounded-lg px-2 py-1.5 text-xs font-semibold ${value === 'single' ? 'bg-white text-slate-900 shadow-sm dark:bg-slate-950 dark:text-slate-100' : 'text-slate-500 hover:text-slate-700 dark:text-slate-400'}`}
        >
          Anul trecut
        </button>
        <button
          type="button"
          disabled={disabled}
          aria-pressed={value === 'multi'}
          onClick={() => onChange('multi')}
          className={`rounded-lg px-2 py-1.5 text-xs font-semibold ${value === 'multi' ? 'bg-white text-slate-900 shadow-sm dark:bg-slate-950 dark:text-slate-100' : 'text-slate-500 hover:text-slate-700 dark:text-slate-400'}`}
        >
          Multi-year
        </button>
      </div>
    </div>
  );
}
