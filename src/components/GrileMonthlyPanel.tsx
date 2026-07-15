import { useEffect, useState, type ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Download,
  FileSpreadsheet,
  FolderArchive,
  Loader2,
  RotateCcw,
  Trash2,
} from 'lucide-react';
import {
  approveGrileMonthlyManifest,
  downloadGrileMonthly,
  getGrileMonthlyManifest,
  getGrileMonthlyJob,
  getGrileMonthlyPermissions,
  runGrileMonthly,
  type GrileMonthlyOp,
} from '../api/grile';
import {getApiErrorMessage} from '../api/client';
import { formatMonthLabel, shiftMonth } from '../lib/dates';
import { cn } from '../lib/utils';

function roLabel(ym: string): string {
  return formatMonthLabel(ym, { month: 'long' });
}

function nextLabel(ym: string): string {
  return formatMonthLabel(shiftMonth(ym, 1), { month: 'long' });
}

type ActiveJob = { jobId: string; op: GrileMonthlyOp; dryRun: boolean };

export function GrileMonthlyPanel({ month }: { month: string }) {
  const [job, setJob] = useState<ActiveJob | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);
  const [downloading, setDownloading] = useState<'final' | 'archive' | null>(null);
  const [approving, setApproving] = useState(false);

  const perms = useQuery({
    queryKey: ['grile-monthly-perms'],
    queryFn: getGrileMonthlyPermissions,
    staleTime: 5 * 60_000,
  });

  const jobQuery = useQuery({
    queryKey: ['grile-monthly-job', job?.jobId],
    queryFn: () => getGrileMonthlyJob(job!.jobId),
    enabled: !!job,
    refetchInterval: (q) => {
      const s = q.state.data?.status;
      return s && s !== 'complete' && s !== 'not_found' ? 2000 : false;
    },
  });

  const {
    data: closeoutManifest = null,
    refetch: refetchManifest,
  } = useQuery({
    queryKey: ['grile-monthly-manifest', month],
    queryFn: () => getGrileMonthlyManifest(month),
    enabled: !!month && perms.data?.can_run === true,
    staleTime: 10_000,
  });

  useEffect(() => {
    if (jobQuery.data?.status === 'complete') {
      void refetchManifest();
    }
  }, [jobQuery.data?.status, refetchManifest]);

  // Ascuns complet daca utilizatorul nu e admin grile (gate-ul real e server-side)
  if (perms.data && !perms.data.can_run) return null;

  const result = jobQuery.data?.result ?? null;
  const jobStatus = jobQuery.data?.status;
  const running = busy || approving || (!!job && jobStatus !== 'complete' && jobStatus !== 'not_found');
  const approvedManifestId = closeoutManifest?.status === 'approved' ? closeoutManifest.id : null;

  async function trigger(op: GrileMonthlyOp, dryRun: boolean) {
    if (!month || running) return;
    if (op === 'reset' && !dryRun) {
      const ok = window.confirm(
        `Reset LIVE pentru ${roLabel(month)}: sterge celulele editabile din TOATE grilele ` +
          `si le pregateste pentru ${nextLabel(month)}. Operatie IREVOCABILA.\n\n` +
          `Ruleaza intai Finalizeaza + Exporta arhiva. Continui?`,
      );
      if (!ok) return;
    }
    setError(null);
    setBusy(true);
    try {
      const res = await runGrileMonthly({
        op,
        month,
        dry_run: dryRun,
        approved_manifest_id: op === 'reset' && !dryRun ? approvedManifestId : undefined,
      });
      if (res.status === 'already_completed') {
        setError('Resetul LIVE pentru luna selectata este deja marcat finalizat. Nu il reluam automat.');
        return;
      }
      if (!res.job_id) {
        setError(
          res.status === 'already_running'
            ? 'Exista deja o operatie lunara Grile in curs pentru luna selectata.'
            : 'Nu am primit id-ul jobului pentru operatia lunara.',
        );
        return;
      }
      setJob({ jobId: res.job_id, op, dryRun });
    } catch (exc: unknown) {
      setError(getApiErrorMessage(
        exc,
        'Nu am putut porni operatia. Verifica permisiunile / serviciul grile.',
      ));
    } finally {
      setBusy(false);
    }
  }

  async function approveManifest() {
    if (!closeoutManifest || closeoutManifest.status !== 'verified' || running) return;
    const expectedStores = closeoutManifest.expected.stores ?? 0;
    const expectedAgents = closeoutManifest.expected.agents ?? 0;
    if (!window.confirm(
      `Aprobi manifestul verificat pentru ${roLabel(month)}: ${expectedStores} magazine si ` +
        `${expectedAgents} agenti, zero erori? Resetul LIVE va fi permis numai pentru acest manifest.`,
    )) return;
    setError(null);
    setApproving(true);
    try {
      await approveGrileMonthlyManifest(closeoutManifest.id);
      await refetchManifest();
    } catch (exc: unknown) {
      setError(getApiErrorMessage(exc, 'Manifestul nu a putut fi aprobat.'));
    } finally {
      setApproving(false);
    }
  }

  async function download(kind: 'final' | 'archive') {
    setError(null);
    setDownloading(kind);
    try {
      await downloadGrileMonthly(kind, month);
    } catch {
      setError(
        kind === 'final'
          ? 'Fisierul de salarii nu exista inca. Ruleaza intai „Finalizeaza salarii".'
          : 'Arhiva nu exista inca. Ruleaza intai „Exporta arhiva".',
      );
    } finally {
      setDownloading(null);
    }
  }

  const opLabel: Record<GrileMonthlyOp, string> = {
    finalize: 'Finalizare salarii',
    archive: 'Export arhiva',
    reset: job?.dryRun ? 'Reset (simulare)' : 'Reset LIVE',
  };

  return (
    <div className="mt-4 border-t border-slate-100 pt-3 dark:border-slate-800">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="flex w-full flex-wrap items-center justify-between gap-2 rounded-lg px-1 py-1 text-left hover:bg-slate-50 dark:hover:bg-slate-800/60"
      >
        <div className="flex min-w-0 items-center gap-2">
          {open ? (
            <ChevronDown className="h-4 w-4 flex-shrink-0 text-slate-400" />
          ) : (
            <ChevronRight className="h-4 w-4 flex-shrink-0 text-slate-400" />
          )}
          <div>
            <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-100">
              Inchidere luna
            </h3>
            <p className="mt-0.5 text-xs text-slate-500">
              Finalizare, arhiva si reset pentru luna noua.
            </p>
          </div>
        </div>
        <div className="text-right text-xs">
          <div className="text-slate-400">Luna inchisa</div>
          <div className="font-semibold text-slate-700 dark:text-slate-200">
            {month ? roLabel(month) : '—'}
          </div>
        </div>
      </button>

      {open && (
        <div className="mt-3">
          <p className="text-xs text-slate-500">
            Salveaza grilele, genereaza tabelul de salarii si reseteaza pentru luna noua.
            Ruleaza direct in Retail (linkurile magazinelor nu se schimba).
          </p>

          {/* Actiuni */}
          <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
            <ActionButton
              icon={<FileSpreadsheet className="h-4 w-4" />}
              label="Finalizeaza salarii"
              hint="Citeste grilele + genereaza Excel"
              onClick={() => trigger('finalize', false)}
              disabled={!month || running}
            />
            <ActionButton
              icon={<FolderArchive className="h-4 w-4" />}
              label="Exporta arhiva"
              hint="XLSX per magazin + ZIP complet"
              onClick={() => trigger('archive', false)}
              disabled={!month || running}
            />
            <ActionButton
              icon={<RotateCcw className="h-4 w-4" />}
              label="Reset (simulare)"
              hint="Verifica resetul fara a atinge grilele"
              onClick={() => trigger('reset', true)}
              disabled={!month || running}
            />
            <ActionButton
              icon={<Trash2 className="h-4 w-4" />}
              label="Reset LIVE"
              hint={approvedManifestId
                ? `Curata grilele → ${month ? nextLabel(month) : 'luna noua'}, cu backup verificat.`
                : 'Necesita arhiva verificata si manifest aprobat.'}
              danger
              onClick={() => trigger('reset', false)}
              disabled={!month || running || !approvedManifestId}
            />
          </div>

          {closeoutManifest && (
            <div className="mt-3 rounded-lg border border-slate-200 px-3 py-2 text-xs dark:border-slate-700">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="text-slate-600 dark:text-slate-300">
                  Manifest arhiva: {closeoutManifest.processed.stores ?? 0}/{closeoutManifest.expected.stores ?? 0} magazine ·{' '}
                  {closeoutManifest.processed.agents ?? 0}/{closeoutManifest.expected.agents ?? 0} agenti ·{' '}
                  {closeoutManifest.error_count} erori
                </div>
                {closeoutManifest.status === 'verified' && (
                  <button
                    type="button"
                    onClick={approveManifest}
                    disabled={running}
                    className="inline-flex items-center gap-1 rounded-md bg-emerald-600 px-2 py-1 font-semibold text-white disabled:opacity-50"
                  >
                    {approving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <CheckCircle2 className="h-3.5 w-3.5" />}
                    Aproba manifest
                  </button>
                )}
                {closeoutManifest.status === 'approved' && (
                  <span className="font-semibold text-emerald-600 dark:text-emerald-400">Aprobat pentru reset</span>
                )}
                {closeoutManifest.status === 'consumed' && (
                  <span className="font-semibold text-slate-500">Reset consumat</span>
                )}
              </div>
            </div>
          )}

          {/* Download */}
          <div className="mt-3 flex flex-wrap gap-4 text-sm">
            <button
              onClick={() => download('final')}
              disabled={!month || downloading !== null}
              className="inline-flex items-center gap-1 font-medium text-indigo-600 hover:underline disabled:opacity-50 dark:text-indigo-400"
            >
              {downloading === 'final' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
              Descarca Excel final
            </button>
            <button
              onClick={() => download('archive')}
              disabled={!month || downloading !== null}
              className="inline-flex items-center gap-1 font-medium text-indigo-600 hover:underline disabled:opacity-50 dark:text-indigo-400"
            >
              {downloading === 'archive' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
              Descarca arhiva ZIP
            </button>
          </div>

          {error && (
            <div className="mt-3 flex items-start gap-1.5 rounded-lg bg-rose-50 px-3 py-2 text-xs text-rose-600 dark:bg-rose-900/30 dark:text-rose-300">
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" />
              {error}
            </div>
          )}

          {/* Status + log ultima rulare */}
          {job && (
            <div className="mt-3 rounded-lg border border-slate-200 dark:border-slate-700">
              <div className="flex items-center justify-between gap-2 border-b border-slate-100 px-3 py-1.5 text-xs dark:border-slate-800">
                <span className="font-medium text-slate-600 dark:text-slate-300">{opLabel[job.op]}</span>
                {running ? (
                  <span className="inline-flex items-center gap-1 text-indigo-600 dark:text-indigo-400">
                    <Loader2 className="h-3.5 w-3.5 animate-spin" /> Ruleaza…
                  </span>
                ) : result ? (
                  <span
                    className={cn(
                      'rounded px-1.5 py-0.5 font-semibold',
                      result.status === 'success'
                        ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300'
                        : 'bg-rose-100 text-rose-700 dark:bg-rose-900/40 dark:text-rose-300',
                    )}
                  >
                    {result.status === 'success' ? 'Succes' : 'Esuat'}
                    {result.dry_run ? ' · simulare' : ''}
                  </span>
                ) : null}
              </div>
              {result?.output && (
                <pre className="max-h-64 overflow-auto whitespace-pre-wrap px-3 py-2 font-mono text-[11px] leading-snug text-slate-600 dark:text-slate-300">
                  {result.output}
                </pre>
              )}
            </div>
          )}
        </div>
      )}

      {!open && (running || result || error) && (
        <div className="mt-2 px-1 text-xs text-slate-500">
          {running ? 'Operatie in curs...' : error ? error : `Ultima operatie: ${opLabel[job!.op]}`}
        </div>
      )}
    </div>
  );
}

function ActionButton({
  icon,
  label,
  hint,
  onClick,
  disabled,
  danger,
}: {
  icon: ReactNode;
  label: string;
  hint: string;
  onClick: () => void;
  disabled?: boolean;
  danger?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={cn(
        'flex flex-col items-start gap-0.5 rounded-xl border px-3 py-2 text-left transition-colors disabled:cursor-not-allowed disabled:opacity-50',
        danger
          ? 'border-rose-200 bg-rose-50 hover:bg-rose-100 dark:border-rose-900/50 dark:bg-rose-900/20 dark:hover:bg-rose-900/30'
          : 'border-slate-200 bg-slate-50 hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-800/60 dark:hover:bg-slate-800',
      )}
    >
      <span
        className={cn(
          'inline-flex items-center gap-1.5 text-sm font-semibold',
          danger ? 'text-rose-600 dark:text-rose-300' : 'text-slate-700 dark:text-slate-200',
        )}
      >
        {icon}
        {label}
      </span>
      <span className="text-[11px] text-slate-400">{hint}</span>
    </button>
  );
}
