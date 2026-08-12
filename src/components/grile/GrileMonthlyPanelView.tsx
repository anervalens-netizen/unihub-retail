import type { ReactNode } from 'react';
import { AlertTriangle, CheckCircle2, ChevronDown, ChevronRight, Download, FileSpreadsheet, FolderArchive, Loader2, RotateCcw, Trash2 } from 'lucide-react';

import type { GrileMonthlyOp } from '../../api/grile';
import { cn } from '../../lib/utils';
import { grileMonthLabel, nextGrileMonthLabel, type GrileMonthlyPanelModel } from './useGrileMonthlyPanel';

export function GrileMonthlyPanelView({ month, model }: { month: string; model: GrileMonthlyPanelModel }) {
  if (model.permissions.data && !model.permissions.data.can_run) return null;
  const labels: Record<GrileMonthlyOp, string> = {
    finalize: 'Finalizare salarii', archive: 'Export arhiva',
    reset: model.job?.dryRun ? 'Reset (simulare)' : 'Reset LIVE',
  };
  return <div className="mt-4 border-t border-slate-100 pt-3 dark:border-slate-800">
    <button type="button" onClick={() => model.setOpen(!model.open)} className="flex w-full flex-wrap items-center justify-between gap-2 rounded-lg px-1 py-1 text-left hover:bg-slate-50 dark:hover:bg-slate-800/60">
      <div className="flex min-w-0 items-center gap-2">{model.open ? <ChevronDown className="h-4 w-4 flex-shrink-0 text-slate-400" /> : <ChevronRight className="h-4 w-4 flex-shrink-0 text-slate-400" />}<div><h3 className="text-sm font-semibold text-slate-800 dark:text-slate-100">Inchidere luna</h3><p className="mt-0.5 text-xs text-slate-500">Finalizare, arhiva si reset pentru luna noua.</p></div></div>
      <div className="text-right text-xs"><div className="text-slate-400">Luna selectata</div><div className="font-semibold text-slate-700 dark:text-slate-200">{month ? grileMonthLabel(month) : '—'}</div></div>
    </button>
    {model.open && <MonthlyPanelBody month={month} model={model} labels={labels} />}
    {!model.open && (model.running || model.result || model.error) && <div className="mt-2 px-1 text-xs text-slate-500">{model.running ? 'Operatie in curs...' : model.error ? model.error : `Ultima operatie: ${labels[model.job!.op]}`}</div>}
  </div>;
}

function MonthlyPanelBody({ month, model, labels }: { month: string; model: GrileMonthlyPanelModel; labels: Record<GrileMonthlyOp, string> }) {
  return <div className="mt-3">
    <p className="text-xs text-slate-500">Salveaza grilele, genereaza tabelul de salarii si reseteaza pentru luna noua. Ruleaza direct in Retail (linkurile magazinelor nu se schimba).</p>
    <MonthlyActions month={month} model={model} />
    <ManifestState model={model} />
    <Downloads month={month} model={model} />
    {model.error && <div className="mt-3 flex items-start gap-1.5 rounded-lg bg-rose-50 px-3 py-2 text-xs text-rose-600 dark:bg-rose-900/30 dark:text-rose-300"><AlertTriangle className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" />{model.error}</div>}
    <JobState model={model} labels={labels} />
  </div>;
}

function MonthlyActions({ month, model }: { month: string; model: GrileMonthlyPanelModel }) {
  return <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
    <ActionButton icon={<FileSpreadsheet className="h-4 w-4" />} label="Finalizeaza salarii" hint="Citeste grilele + genereaza Excel" onClick={() => model.trigger('finalize', false)} disabled={!month || model.running} />
    <ActionButton icon={<FolderArchive className="h-4 w-4" />} label="Exporta arhiva" hint="XLSX per magazin + ZIP complet" onClick={() => model.trigger('archive', false)} disabled={!month || model.running} />
    <ActionButton icon={<RotateCcw className="h-4 w-4" />} label="Reset (simulare)" hint="Verifica resetul fara a atinge grilele" onClick={() => model.trigger('reset', true)} disabled={!month || model.running} />
    <ActionButton icon={<Trash2 className="h-4 w-4" />} label="Reset LIVE" hint={model.approvedManifestId ? `Curata grilele → ${month ? nextGrileMonthLabel(month) : 'luna noua'}, cu backup verificat.` : 'Necesita arhiva verificata si manifest aprobat.'} danger onClick={() => model.trigger('reset', false)} disabled={!month || model.running || !model.approvedManifestId} />
  </div>;
}

function ManifestState({ model }: { model: GrileMonthlyPanelModel }) {
  const manifest = model.manifest;
  if (!manifest) return null;
  return <div className="mt-3 rounded-lg border border-slate-200 px-3 py-2 text-xs dark:border-slate-700"><div className="flex flex-wrap items-center justify-between gap-2">
    <div className="text-slate-600 dark:text-slate-300">Manifest arhiva: {manifest.processed.stores ?? 0}/{manifest.expected.stores ?? 0} magazine · {manifest.processed.agents ?? 0}/{manifest.expected.agents ?? 0} agenti · {manifest.error_count} erori</div>
    {manifest.status === 'verified' && <button type="button" onClick={model.approveManifest} disabled={model.running} className="inline-flex items-center gap-1 rounded-md bg-emerald-600 px-2 py-1 font-semibold text-white disabled:opacity-50">{model.approving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <CheckCircle2 className="h-3.5 w-3.5" />}Aproba manifest</button>}
    {manifest.status === 'approved' && <span className="font-semibold text-emerald-600 dark:text-emerald-400">Aprobat pentru reset</span>}
    {manifest.status === 'consumed' && <span className="font-semibold text-slate-500">Reset consumat</span>}
  </div></div>;
}

function Downloads({ month, model }: { month: string; model: GrileMonthlyPanelModel }) {
  return <div className="mt-3 flex flex-wrap gap-4 text-sm">
    <button onClick={() => model.download('final')} disabled={!month || model.downloading !== null} className="inline-flex items-center gap-1 font-medium text-indigo-600 hover:underline disabled:opacity-50 dark:text-indigo-400">{model.downloading === 'final' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}Descarca Excel final</button>
    <button onClick={() => model.download('archive')} disabled={!month || model.downloading !== null} className="inline-flex items-center gap-1 font-medium text-indigo-600 hover:underline disabled:opacity-50 dark:text-indigo-400">{model.downloading === 'archive' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}Descarca arhiva ZIP</button>
  </div>;
}

function JobState({ model, labels }: { model: GrileMonthlyPanelModel; labels: Record<GrileMonthlyOp, string> }) {
  if (!model.job) return null;
  return <div className="mt-3 rounded-lg border border-slate-200 dark:border-slate-700">
    <div className="flex items-center justify-between gap-2 border-b border-slate-100 px-3 py-1.5 text-xs dark:border-slate-800"><span className="font-medium text-slate-600 dark:text-slate-300">{labels[model.job.op]}</span>{model.running ? <span className="inline-flex items-center gap-1 text-indigo-600 dark:text-indigo-400"><Loader2 className="h-3.5 w-3.5 animate-spin" /> Ruleaza…</span> : model.result ? <span className={cn('rounded px-1.5 py-0.5 font-semibold', model.result.status === 'success' ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300' : 'bg-rose-100 text-rose-700 dark:bg-rose-900/40 dark:text-rose-300')}>{model.result.status === 'success' ? 'Succes' : 'Esuat'}{model.result.dry_run ? ' · simulare' : ''}</span> : null}</div>
    {model.result?.output && <pre className="max-h-64 overflow-auto whitespace-pre-wrap px-3 py-2 font-mono text-[11px] leading-snug text-slate-600 dark:text-slate-300">{model.result.output}</pre>}
  </div>;
}

function ActionButton({ icon, label, hint, onClick, disabled, danger }: { icon: ReactNode; label: string; hint: string; onClick: () => void; disabled?: boolean; danger?: boolean }) {
  return <button onClick={onClick} disabled={disabled} className={cn('flex flex-col items-start gap-0.5 rounded-xl border px-3 py-2 text-left transition-colors disabled:cursor-not-allowed disabled:opacity-50', danger ? 'border-rose-200 bg-rose-50 hover:bg-rose-100 dark:border-rose-900/50 dark:bg-rose-900/20 dark:hover:bg-rose-900/30' : 'border-slate-200 bg-slate-50 hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-800/60 dark:hover:bg-slate-800')}><span className={cn('inline-flex items-center gap-1.5 text-sm font-semibold', danger ? 'text-rose-600 dark:text-rose-300' : 'text-slate-700 dark:text-slate-200')}>{icon}{label}</span><span className="text-[11px] text-slate-400">{hint}</span></button>;
}
