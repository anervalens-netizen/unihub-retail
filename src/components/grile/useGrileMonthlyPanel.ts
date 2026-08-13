import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';

import { getApiErrorMessage } from '../../api/client';
import {
  approveGrileMonthlyManifest, downloadGrileMonthly, getGrileMonthlyJob,
  getGrileMonthlyManifest, getGrileMonthlyPermissions, runGrileMonthly,
  type GrileMonthlyOp,
} from '../../api/grile';
import { formatMonthLabel, shiftMonth } from '../../lib/dates';

export type ActiveMonthlyJob = { jobId: string; op: GrileMonthlyOp; dryRun: boolean };

export function grileMonthLabel(month: string) { return formatMonthLabel(month, { month: 'long' }); }
export function nextGrileMonthLabel(month: string) { return formatMonthLabel(shiftMonth(month, 1), { month: 'long' }); }

function useMonthlyQueries(month: string, job: ActiveMonthlyJob | null) {
  const permissions = useQuery({
    queryKey: ['grile-monthly-perms'],
    queryFn: ({ signal }) => getGrileMonthlyPermissions(signal),
    staleTime: 5 * 60_000,
  });
  const jobQuery = useQuery({
    queryKey: ['grile-monthly-job', job?.jobId],
    queryFn: ({ signal }) => getGrileMonthlyJob(job!.jobId, signal),
    enabled: !!job,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status && status !== 'complete' && status !== 'not_found' ? 2000 : false;
    },
  });
  const manifestQuery = useQuery({
    queryKey: ['grile-monthly-manifest', month],
    queryFn: ({ signal }) => getGrileMonthlyManifest(month, signal),
    enabled: !!month && permissions.data?.can_run === true,
    staleTime: 10_000,
  });
  const refetchManifest = manifestQuery.refetch;
  useEffect(() => {
    if (jobQuery.data?.status === 'complete') void refetchManifest();
  }, [jobQuery.data?.status, refetchManifest]);
  return { permissions, jobQuery, manifestQuery };
}

function useMonthlyActions(
  month: string,
  job: ActiveMonthlyJob | null,
  setJob: (job: ActiveMonthlyJob | null) => void,
  queries: ReturnType<typeof useMonthlyQueries>,
) {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [downloading, setDownloading] = useState<'final' | 'archive' | null>(null);
  const [approving, setApproving] = useState(false);
  const manifest = queries.manifestQuery.data ?? null;
  const jobStatus = queries.jobQuery.data?.status;
  const running = busy || approving || (!!job && jobStatus !== 'complete' && jobStatus !== 'not_found');
  const approvedManifestId = manifest?.status === 'approved' ? manifest.id : null;
  useEffect(() => {
    if (jobStatus === 'complete' && queries.jobQuery.data?.error) setError(`Operatia a esuat in worker: ${queries.jobQuery.data.error}`);
  }, [jobStatus, queries.jobQuery.data?.error]);

  async function trigger(op: GrileMonthlyOp, dryRun: boolean) {
    if (!month || running) return;
    if (op === 'reset' && !dryRun && !window.confirm(`Reset LIVE pentru ${grileMonthLabel(month)}: sterge celulele editabile din TOATE grilele si le pregateste pentru ${nextGrileMonthLabel(month)}. Operatie IREVOCABILA.\n\nRuleaza intai Finalizeaza + Exporta arhiva. Continui?`)) return;
    setError(null); setBusy(true);
    try {
      const response = await runGrileMonthly({
        op, month, dry_run: dryRun,
        approved_manifest_id: op === 'reset' && !dryRun ? approvedManifestId : undefined,
      });
      if (response.status === 'already_completed') {
        setError('Resetul LIVE pentru luna selectata este deja marcat finalizat. Nu il reluam automat.');
      } else if (!response.job_id) {
        setError(response.status === 'already_running' ? 'Exista deja o operatie lunara Grile in curs pentru luna selectata.' : 'Nu am primit id-ul jobului pentru operatia lunara.');
      } else {
        setJob({ jobId: response.job_id, op: response.op, dryRun: response.dry_run ?? dryRun });
      }
    } catch (exception: unknown) {
      setError(getApiErrorMessage(exception, 'Nu am putut porni operatia. Verifica permisiunile / serviciul grile.'));
    } finally { setBusy(false); }
  }

  async function approveManifest() {
    if (!manifest || manifest.status !== 'verified' || running) return;
    const expected = manifest.expected;
    if (!window.confirm(`Aprobi manifestul verificat pentru ${grileMonthLabel(month)}: ${expected.stores ?? 0} magazine si ${expected.agents ?? 0} agenti, zero erori? Resetul LIVE va fi permis numai pentru acest manifest.`)) return;
    setError(null); setApproving(true);
    try { await approveGrileMonthlyManifest(manifest.id); await queries.manifestQuery.refetch(); }
    catch (exception: unknown) { setError(getApiErrorMessage(exception, 'Manifestul nu a putut fi aprobat.')); }
    finally { setApproving(false); }
  }

  async function download(kind: 'final' | 'archive') {
    setError(null); setDownloading(kind);
    try { await downloadGrileMonthly(kind, month); }
    catch { setError(kind === 'final' ? 'Fisierul de salarii nu exista inca. Ruleaza intai „Finalizeaza salarii".' : 'Arhiva nu exista inca. Ruleaza intai „Exporta arhiva".'); }
    finally { setDownloading(null); }
  }
  return { error, running, downloading, approving, manifest, approvedManifestId, trigger, approveManifest, download };
}

export function useGrileMonthlyPanel(month: string) {
  const [job, setJob] = useState<ActiveMonthlyJob | null>(null);
  const [open, setOpen] = useState(false);
  const queries = useMonthlyQueries(month, job);
  const actions = useMonthlyActions(month, job, setJob, queries);
  return {
    job, open, setOpen, ...queries, ...actions,
    result: queries.jobQuery.data?.result ?? null,
  };
}

export type GrileMonthlyPanelModel = ReturnType<typeof useGrileMonthlyPanel>;
