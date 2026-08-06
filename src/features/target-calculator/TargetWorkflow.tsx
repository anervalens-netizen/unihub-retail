type TargetWorkflowProps = { step: 1 | 2 | 3 | 4 };

const STEPS = [
  { number: 1, label: 'Configurare' },
  { number: 2, label: 'Verificare propunere' },
  { number: 3, label: 'Ajustări manageri' },
  { number: 4, label: 'Finalizare' },
] as const;

export function TargetWorkflow({ step }: TargetWorkflowProps) {
  return (
    <nav aria-label="Flux Calculator Target" className="glass rounded-2xl p-3">
      <div className="lg:hidden">
        <div className="mb-2 flex items-center justify-between text-xs font-semibold text-slate-500">
          <span>Pasul {step} din 4</span><span>{STEPS[step - 1]?.label}</span>
        </div>
        <div className="h-2 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700">
          <div className="h-full rounded-full bg-indigo-600 transition-all" style={{ width: `${step * 25}%` }} />
        </div>
      </div>
      <ol className="hidden grid-cols-2 gap-2 lg:grid lg:grid-cols-4">
        {STEPS.map((item) => {
          const complete = item.number < step;
          const active = item.number === step;
          return (
            <li key={item.number} aria-current={active ? 'step' : undefined} className={`flex items-center gap-2 rounded-xl px-3 py-2 text-xs font-semibold ${active ? 'bg-indigo-600 text-white shadow-sm' : complete ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-300' : 'bg-slate-100 text-slate-500 dark:bg-slate-800'}`}>
              <span className={`grid h-6 w-6 shrink-0 place-items-center rounded-full ${active ? 'bg-white/20' : 'bg-white dark:bg-slate-900'}`}>
                {complete ? '✓' : item.number}
              </span>
              {item.label}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
