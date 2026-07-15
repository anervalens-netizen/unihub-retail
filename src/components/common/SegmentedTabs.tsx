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
  className,
}: {
  options: readonly SegmentedTabOption<T>[];
  value: T;
  onChange: (value: T) => void;
  ariaLabel: string;
  className?: string;
}) {
  return (
    <div className="min-w-0">
      <div
        role="tablist"
        aria-label={ariaLabel}
        className={cn('segmented-tabs-scroll flex min-w-0 snap-x snap-mandatory gap-1 overflow-x-auto rounded-2xl p-1', className)}
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
                'min-h-11 min-w-fit flex-1 snap-start rounded-xl px-3 py-2 text-xs font-bold transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-1 lg:min-h-10 lg:text-sm',
                active
                  ? 'bg-white text-indigo-600 shadow-sm dark:bg-slate-800 dark:text-indigo-400'
                  : 'text-slate-500 hover:text-indigo-600 dark:hover:text-indigo-300',
                option.disabled && 'cursor-not-allowed opacity-50 hover:text-slate-500',
              )}
            >
              {option.label}
            </button>
          );
        })}
      </div>
      {options.length > 4 && (
        <p className="mt-1 pr-1 text-right text-[10px] font-medium text-slate-400 sm:hidden" aria-hidden="true">
          Glisează pentru toate secțiunile →
        </p>
      )}
    </div>
  );
}
