import type { AvailableMonthsStatus } from '../hooks/useAvailableMonths';

export function AvailableMonthsStatus({
  status,
  onRetry,
}: {
  status: Exclude<AvailableMonthsStatus, 'loading' | 'ready' | 'stale'>;
  onRetry: () => void;
}) {
  const message = status === 'empty'
    ? 'Nu există luni disponibile pentru raportare.'
    : status === 'session_expired'
      ? 'Sesiunea a expirat. Reautentifică-te pentru a încărca lunile disponibile.'
      : 'Lunile disponibile nu au putut fi încărcate.';
  return (
    <div className="flex h-full items-center justify-center px-4">
      <div className="max-w-md rounded-2xl border border-slate-200 bg-white p-6 text-center shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <p className="text-sm font-semibold text-slate-700 dark:text-slate-200">{message}</p>
        {status !== 'session_expired' && (
          <button type="button" onClick={onRetry} className="mt-4 rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white">
            Reîncearcă
          </button>
        )}
      </div>
    </div>
  );
}
