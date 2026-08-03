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
    <div className={cn('min-w-0', secondary && 'relative -top-3 z-10 !mb-0 px-12 sm:px-16 lg:px-24')}>
      <div
        role="tablist"
        aria-label={ariaLabel}
        data-tab-level={level}
        className={cn(
          'segmented-tabs-scroll flex min-w-0 snap-x snap-mandatory overflow-x-auto !border-0 !bg-slate-100/80 !shadow-none dark:!bg-slate-800/70',
          secondary
            ? 'gap-0.5 rounded-2xl p-0.5 lg:mx-auto lg:max-w-2xl'
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
                  ? 'min-h-[26px] rounded-xl px-2 py-0.5 text-xs font-semibold lg:min-h-7 lg:px-2.5'
                  : 'min-h-11 rounded-xl px-3 py-2 text-sm font-bold lg:min-h-10',
                active
                  ? 'bg-white text-indigo-600 shadow-sm ring-1 ring-black/5 dark:bg-slate-900 dark:text-indigo-300 dark:ring-white/10'
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
