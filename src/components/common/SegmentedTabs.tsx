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
    <div className={cn('min-w-0', secondary && 'relative -top-4 z-10 -mb-4 !mt-0 px-10 sm:px-14 lg:px-20')}>
      <div
        role="tablist"
        aria-label={ariaLabel}
        data-tab-level={level}
        className={cn(
          'segmented-tabs-scroll flex min-w-0 snap-x snap-mandatory overflow-x-auto',
          secondary
            ? 'gap-0.5 rounded-b-lg border-x border-b border-slate-200/60 bg-slate-100/65 p-0.5 shadow-[0_5px_10px_-11px_rgba(15,23,42,0.6)] backdrop-blur-sm dark:border-slate-700/50 dark:bg-slate-800/55 lg:mx-auto lg:max-w-2xl'
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
                  ? 'min-h-6 rounded-b-md px-2 py-0.5 text-[9px] font-semibold lg:min-h-7 lg:px-2.5 lg:text-[10px]'
                  : 'min-h-11 rounded-xl px-3 py-2 text-xs font-bold lg:min-h-10 lg:text-sm',
                active
                  ? secondary
                    ? 'bg-white/75 text-indigo-700 dark:bg-slate-900/55 dark:text-indigo-300'
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
