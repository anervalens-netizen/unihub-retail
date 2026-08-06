import { AlertCircle, RefreshCw } from 'lucide-react';
import type { ReactNode } from 'react';

export function Metric({
  label,
  value,
  detail,
  emphasize = false,
  compact = false,
  accent = 'slate',
  className = '',
}: {
  label: string;
  value: ReactNode;
  detail?: string;
  emphasize?: boolean;
  compact?: boolean;
  accent?: 'slate' | 'indigo';
  className?: string;
}) {
  const accentClasses =
    accent === 'indigo'
      ? 'bg-indigo-50/80 dark:bg-indigo-900/20'
      : 'bg-slate-50 dark:bg-slate-800/60';

  return (
    <div className={`min-w-0 rounded-2xl ${compact ? 'p-1.5 sm:p-2' : 'p-3'} ${accentClasses} ${emphasize || compact ? 'flex h-full flex-col' : ''} ${emphasize ? 'justify-between' : ''} ${className}`}>
      <div className={`break-words font-bold uppercase tracking-wide text-slate-500 ${compact ? 'text-[10px] leading-snug sm:text-[11px]' : 'text-[11px]'}`}>{label}</div>
      <div className={`min-w-0 font-black ${emphasize ? 'mt-4 text-[2rem] leading-none' : compact ? 'mt-1 whitespace-nowrap text-[clamp(0.75rem,3.6vw,1rem)] leading-tight tracking-tight tabular-nums sm:text-base' : 'mt-1 break-words text-base leading-tight'}`}>{value ?? '-'}</div>
      {detail ? <div className="mt-2 text-xs leading-relaxed text-slate-500">{detail}</div> : null}
    </div>
  );
}

export function LoadingCard({ label }: { label: string }) {
  return (
    <div className="glass flex flex-col items-center justify-center gap-3 rounded-3xl p-8">
      <div className="h-8 w-8 animate-spin rounded-full border-4 border-indigo-200 border-t-indigo-600" />
      <div className="text-sm font-medium text-slate-500">{label}</div>
    </div>
  );
}

export function ErrorCard({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="glass flex flex-col items-center gap-4 rounded-3xl p-6">
      <div className="flex items-center gap-2 text-amber-600">
        <AlertCircle className="h-5 w-5" />
        <span className="text-sm font-medium">{message}</span>
      </div>
      <button
        type="button"
        onClick={onRetry}
        className="flex items-center gap-2 rounded-xl bg-indigo-600 px-4 py-2 text-xs font-semibold text-white transition-colors hover:bg-indigo-700"
      >
        <RefreshCw className="h-4 w-4" />
        Reincearca
      </button>
    </div>
  );
}
