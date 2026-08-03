import type { ReactNode } from 'react';

import { cn } from '../../lib/utils';

export function DesktopPageFrame({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn('mx-auto w-full max-w-6xl lg:max-w-[1600px]', className)}>
      {children}
    </div>
  );
}

export function PageHeader({
  title,
  description,
  actions,
  className,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <header className={cn('space-y-1 lg:flex lg:items-end lg:justify-between lg:gap-6', className)}>
      <div className="min-w-0">
        <h1 className="text-xl font-bold tracking-tight lg:text-2xl">{title}</h1>
        {description && (
          <p className="text-xs text-slate-500 dark:text-slate-400 lg:text-sm">
            {description}
          </p>
        )}
      </div>
      {actions && <div className="shrink-0">{actions}</div>}
    </header>
  );
}

export function DesktopKpiGrid({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn('grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-4', className)}>
      {children}
    </div>
  );
}

export function DashboardGrid({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn('grid min-w-0 gap-3 xl:grid-cols-2 xl:[&>:only-child]:col-span-2', className)}>
      {children}
    </div>
  );
}
export function DesktopDashboardGrid({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("space-y-3 min-w-0 lg:space-y-0 lg:grid lg:gap-3 xl:grid-cols-2 xl:[&>:only-child]:col-span-2", className)}>
      {children}
    </div>
  );
}


export function DashboardPanel({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return <section className={cn('min-w-0', className)}>{children}</section>;
}
