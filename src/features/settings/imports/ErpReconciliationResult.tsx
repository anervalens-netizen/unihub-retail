import { AlertTriangle, CheckCircle2, Info } from 'lucide-react';
import type { ErpReconciliationMetric, ErpReconciliationResponse } from '../../../api/imports';
import { cn } from '../../../lib/utils';
import * as settingsPresenters from '../presenters';

export function ErpReconciliationResult({ result }: { result: ErpReconciliationResponse }) {
  const hasDifferences = result.status === 'differences';
  return (
    <div className="mt-4 min-w-0 space-y-3 border-t border-slate-200 pt-4 dark:border-slate-700">
      <div className={cn(
        'flex items-start gap-3 rounded-2xl border p-3',
        hasDifferences
          ? 'border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-100'
          : 'border-emerald-200 bg-emerald-50 text-emerald-900 dark:border-emerald-900/60 dark:bg-emerald-950/30 dark:text-emerald-100',
      )}>
        {hasDifferences ? <AlertTriangle size={18} className="mt-0.5 shrink-0" /> : <CheckCircle2 size={18} className="mt-0.5 shrink-0" />}
        <div>
          <div className="text-xs font-bold">
            {hasDifferences
              ? result.issue_count > 0
                ? `${result.issue_count} diferențe de detaliu de verificat`
                : 'Au fost găsite diferențe în totalurile comparate'
              : 'Raportul coincide cu datele verificabile din Retail'}
          </div>
          <div className="mt-1 text-[11px] opacity-80">
            {result.import_month} · perioadă comparată 01–{settingsPresenters.formatReconciliationDate(result.report_cutoff_date)} · snapshot Retail disponibil până la {result.retail_cutoff_date ? settingsPresenters.formatReconciliationDate(result.retail_cutoff_date) : 'fără date'} · hash {result.file_digest}
          </div>
          <div className="mt-1 text-[11px] opacity-80">
            Magazine {result.report_store_count}/{result.retail_store_count} · Agenți {result.report_agent_count}/{result.retail_agent_count}
          </div>
        </div>
      </div>

      <div className="grid min-w-0 grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {result.metrics.map((metric) => (
          <ReconciliationMetricCard key={metric.key} metric={metric} />
        ))}
      </div>

      {result.issues.length > 0 && (
        <details open className="rounded-2xl border border-amber-200 bg-white p-3 dark:border-amber-900/50 dark:bg-slate-900">
          <summary className="cursor-pointer text-xs font-bold text-amber-800 dark:text-amber-200">
            Unde sunt diferențele · {result.issue_count}
          </summary>
          <div className="mt-2 max-h-80 max-w-full overflow-auto">
            <table className="w-full min-w-[680px] text-left text-[11px]">
              <thead className="sticky top-0 bg-white text-slate-400 dark:bg-slate-900">
                <tr>
                  <th className="px-2 py-2">Nivel</th>
                  <th className="px-2 py-2">Magazin / entitate</th>
                  <th className="px-2 py-2">Metrică</th>
                  <th className="px-2 py-2 text-right">ERP</th>
                  <th className="px-2 py-2 text-right">Retail</th>
                  <th className="px-2 py-2 text-right">Dif.</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                {result.issues.map((issue, index) => (
                  <tr key={`${issue.scope}-${issue.site_code}-${issue.entity}-${issue.metric}-${index}`} title={issue.note}>
                    <td className="px-2 py-2 font-semibold">{issue.scope === 'agent' ? 'Agent' : issue.scope === 'store' ? 'Magazin' : 'Raport'}</td>
                    <td className="px-2 py-2"><span className="font-semibold">{issue.site_code ?? '—'}</span> · {issue.entity}</td>
                    <td className="px-2 py-2">{issue.metric}</td>
                    <td className="px-2 py-2 text-right tabular-nums">{settingsPresenters.formatReconciliationNumber(issue.report_value)}</td>
                    <td className="px-2 py-2 text-right tabular-nums">{settingsPresenters.formatReconciliationNumber(issue.retail_value)}</td>
                    <td className="px-2 py-2 text-right font-bold tabular-nums text-amber-700 dark:text-amber-300">{settingsPresenters.formatSignedReconciliationNumber(issue.difference)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {result.omitted_issue_count > 0 && (
            <div className="mt-2 text-[11px] text-slate-500">Încă {result.omitted_issue_count} diferențe nu sunt afișate în listă.</div>
          )}
        </details>
      )}

      <div className="rounded-2xl border border-sky-200 bg-sky-50 p-3 dark:border-sky-900/50 dark:bg-sky-950/20">
        <div className="mb-2 flex items-center gap-2 text-xs font-bold text-sky-800 dark:text-sky-200">
          <Info size={15} /> Promo și Incentive — valori Retail, necomparabile direct
        </div>
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {result.app_only_metrics.map((metric) => (
            <div key={metric.key} className="rounded-xl bg-white/80 p-2 dark:bg-slate-900/70" title={metric.note}>
              <div className="text-[10px] font-semibold text-slate-500">{metric.label}</div>
              <div className="mt-1 text-sm font-bold tabular-nums">
                {settingsPresenters.formatReconciliationValue(metric.value, metric.unit)}
              </div>
            </div>
          ))}
        </div>
        <p className="mt-2 text-[11px] text-sky-700 dark:text-sky-300">
          Raportul agregat nu conține codurile de produs, identitatea bonului și unitățile promo necesare pentru certificarea independentă a acestor valori.
        </p>
      </div>

      <details className="rounded-2xl bg-slate-50 p-3 text-[11px] text-slate-500 dark:bg-slate-800/60">
        <summary className="cursor-pointer font-bold">Cum a fost făcută verificarea</summary>
        <ul className="mt-2 list-disc space-y-1 pl-4">
          {result.notes.map((note) => <li key={note}>{note}</li>)}
        </ul>
      </details>
    </div>
  );
}
function ReconciliationMetricCard({ metric }: { metric: ErpReconciliationMetric }) {
  const tone = metric.status === 'difference'
    ? 'border-amber-200 bg-amber-50 dark:border-amber-900/50 dark:bg-amber-950/20'
    : metric.status === 'explained'
      ? 'border-sky-200 bg-sky-50 dark:border-sky-900/50 dark:bg-sky-950/20'
      : 'border-emerald-200 bg-emerald-50 dark:border-emerald-900/50 dark:bg-emerald-950/20';
  return (
    <div className={cn('rounded-2xl border p-3', tone)} title={metric.note ?? undefined}>
      <div className="flex items-start justify-between gap-2">
        <div className="text-[11px] font-bold text-slate-700 dark:text-slate-200">{metric.label}</div>
        {metric.status === 'difference'
          ? <AlertTriangle size={14} className="shrink-0 text-amber-600" />
          : metric.status === 'explained'
            ? <Info size={14} className="shrink-0 text-sky-600" />
            : <CheckCircle2 size={14} className="shrink-0 text-emerald-600" />}
      </div>
      <div className="mt-2 grid grid-cols-2 gap-2 text-[10px] text-slate-500">
        <div>ERP <strong className="block text-xs text-slate-800 dark:text-slate-100">{settingsPresenters.formatReconciliationValue(metric.report_value, metric.unit)}</strong></div>
        <div>Retail <strong className="block text-xs text-slate-800 dark:text-slate-100">{settingsPresenters.formatReconciliationValue(metric.retail_value, metric.unit)}</strong></div>
      </div>
      {metric.note && <p className="mt-2 text-[10px] leading-snug text-slate-500">{metric.note}</p>}
    </div>
  );
}
