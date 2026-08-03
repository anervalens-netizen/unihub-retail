import { cn } from '../../lib/utils';

export interface SegmentedTabOption<T extends string> {
  label: string;
  value: T;
  disabled?: boolean;
}

export function SegmentedTabs<T extends string>({
  options,
  value,
  onChange,
  ariaLabel,
  level = 'primary',
  className,
}: {
  options: readonly SegmentedTabOption<T>[];
  value: T;
  onChange: (value: T) => void;
  ariaLabel: string;
  level?: 'primary' | 'secondary';
  className?: string;
}) {
  const secondary = level === 'secondary';

  return (
    <div className={cn('min-w-0', secondary && 'px-2 sm:px-3')}>
      <div
        role="tablist"
        aria-label={ariaLabel}
        data-tab-level={level}
        className={cn(
          'segmented-tabs-scroll flex min-w-0 snap-x snap-mandatory overflow-x-auto',
          secondary
            ? 'gap-0.5 rounded-xl border border-indigo-100/80 bg-indigo-50/35 p-0.5 dark:border-indigo-900/50 dark:bg-indigo-950/15'
            : 'gap-1 rounded-2xl p-1',
          className,
        )}
      >
        {options.map((option) => {
          const active = option.value === value;
          return (
            <button
              key={option.value}
              type="button"
              role="tab"
              aria-selected={active}
              disabled={option.disabled}
              onClick={() => {
                if (!option.disabled) onChange(option.value);
              }}
              className={cn(
                'min-w-fit flex-1 snap-start transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-1',
                secondary
                  ? 'min-h-8 rounded-lg px-2.5 py-1.5 text-[11px] font-semibold lg:min-h-9 lg:text-xs'
                  : 'min-h-11 rounded-xl px-3 py-2 text-xs font-bold lg:min-h-10 lg:text-sm',
                active
                  ? secondary
                    ? 'bg-indigo-100/75 text-indigo-700 ring-1 ring-inset ring-indigo-200/70 dark:bg-indigo-950/45 dark:text-indigo-300 dark:ring-indigo-800/70'
                    : 'bg-white text-indigo-600 shadow-sm dark:bg-slate-800 dark:text-indigo-400'
                  : 'text-slate-500 hover:text-indigo-600 dark:hover:text-indigo-300',
                option.disabled && 'cursor-not-allowed opacity-50 hover:text-slate-500',
              )}
            >
              {option.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}
