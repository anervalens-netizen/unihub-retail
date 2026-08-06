export function ForecastDefinition({ term, description }: { term: string; description: string }) {
  return (
    <div className="rounded-xl bg-white px-3 py-2 dark:bg-slate-900/60">
      <span className="font-bold text-slate-800 dark:text-slate-100">{term}: </span>
      <span>{description}</span>
    </div>
  );
}

export function ForecastLine({ label, value, valueClassName = '' }: { label: string; value: string; valueClassName?: string }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-2xl bg-slate-50 px-3 py-2 dark:bg-slate-800/60">
      <span className="text-slate-500">{label}</span>
      <span className={`text-right font-bold text-slate-700 dark:text-slate-200 ${valueClassName}`}>{value}</span>
    </div>
  );
}
