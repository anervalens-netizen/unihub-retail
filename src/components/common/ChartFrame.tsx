import type { ReactNode } from 'react';

interface ChartFrameProps {
  title: ReactNode;
  icon?: ReactNode;
  subtitle?: ReactNode;
  controls?: ReactNode;
  loading?: boolean;
  loadingLabel?: ReactNode;
  empty?: boolean;
  emptyLabel?: ReactNode;
  contentClassName: string;
  className?: string;
  headerAlign?: 'start' | 'center';
  children: ReactNode;
}

export function ChartFrame({
  title,
  icon,
  subtitle,
  controls,
  loading = false,
  loadingLabel = 'Se incarca...',
  empty = false,
  emptyLabel,
  contentClassName,
  className = '',
  headerAlign = 'center',
  children,
}: ChartFrameProps) {
  const showingState = loading || empty;
  const content = loading ? loadingLabel : empty ? emptyLabel : children;

  return (
    <div className={`glass rounded-3xl p-4 ${className}`.trim()}>
      <div
        className={`mb-3 flex justify-between gap-2 ${
          headerAlign === 'start' ? 'items-start' : 'items-center'
        }`}
      >
        <div>
          <div className={icon ? 'flex items-center gap-2' : undefined}>
            {icon}
            <h3 className="text-sm font-bold">{title}</h3>
          </div>
          {subtitle !== undefined && subtitle !== null && (
            <p className="text-[11px] text-slate-500">{subtitle}</p>
          )}
        </div>
        {controls}
      </div>
      <div
        className={`${contentClassName} ${
          showingState ? 'flex items-center justify-center text-xs text-slate-400' : ''
        }`.trim()}
      >
        {content}
      </div>
    </div>
  );
}
