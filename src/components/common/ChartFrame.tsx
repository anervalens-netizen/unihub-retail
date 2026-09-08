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
  compactMobile?: boolean;
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
  compactMobile = false,
  children,
}: ChartFrameProps) {
  const showingState = loading || empty;
  const content = loading ? loadingLabel : empty ? emptyLabel : children;
  const rootSpacing = compactMobile ? 'p-3 sm:p-4' : 'p-4';
  const headerSpacing = compactMobile ? 'mb-2 sm:mb-3' : 'mb-3';

  return (
    <div className={`glass rounded-3xl ${rootSpacing} ${className}`.trim()}>
      <div
        className={`${headerSpacing} flex justify-between gap-2 ${
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
