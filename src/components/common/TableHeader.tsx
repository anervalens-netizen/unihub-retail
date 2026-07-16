import { ArrowUpDown, ChevronDown, ChevronUp } from 'lucide-react';
import type { ReactNode } from 'react';

import { cn } from '../../lib/utils';

export type TableSortDirection = 'asc' | 'desc';

const ALIGNMENT = {
  left: 'items-start text-left',
  center: 'items-center text-center',
  right: 'items-end text-right',
} as const;

export function TableHeaderCell({
  children,
  align = 'left',
  className,
  title,
}: {
  children: ReactNode;
  align?: keyof typeof ALIGNMENT;
  className?: string;
  title?: string;
}) {
  return (
    <th
      className={cn(
        'px-2.5 py-2 align-bottom text-[11px] font-bold leading-tight text-slate-500 lg:text-xs',
        align === 'right' && 'text-right',
        align === 'center' && 'text-center',
        className,
      )}
      title={title}
    >
      {children}
    </th>
  );
}

export function SortableTableHeader({
  label,
  active,
  direction,
  onClick,
  className,
  title,
  align = 'left',
}: {
  label: string;
  active: boolean;
  direction: TableSortDirection;
  onClick: () => void;
  className?: string;
  title?: string;
  align?: keyof typeof ALIGNMENT;
}) {
  return (
    <TableHeaderCell align={align} className={className} title={title}>
      <button
        type="button"
        onClick={onClick}
        title={title}
        className={cn(
          'flex w-full min-w-0 flex-col gap-0.5 transition-colors hover:text-indigo-600 focus-visible:rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 dark:hover:text-indigo-300',
          ALIGNMENT[align],
        )}
      >
        <span className="max-w-full whitespace-normal break-words leading-tight">{label}</span>
        <span className={cn('flex h-3 items-center', active ? 'text-indigo-600 dark:text-indigo-300' : 'text-slate-300 dark:text-slate-600')} aria-hidden="true">
          {active ? (
            direction === 'asc' ? <ChevronUp size={11} /> : <ChevronDown size={11} />
          ) : (
            <ArrowUpDown size={10} />
          )}
        </span>
      </button>
    </TableHeaderCell>
  );
}

export const TABLE_HEAD_CLASS =
  'sticky top-0 z-10 bg-slate-50 text-slate-500 dark:bg-slate-800/95 dark:text-slate-300';

export const TABLE_ROW_CLASS =
  'border-t border-slate-100 transition-colors hover:bg-slate-50/80 dark:border-slate-800 dark:hover:bg-slate-800/40';

export const TABLE_CELL_CLASS = 'px-2.5 py-2 text-[12px] leading-tight lg:text-[13px]';
