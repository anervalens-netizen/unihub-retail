import { FileSpreadsheet, Upload } from "lucide-react";

import { cn } from "../../../lib/utils";
import { formatIsoDateTime, formatMonthLabel } from "../../../lib/dates";
import { ErpReconciliationResult } from "./ErpReconciliationResult";
import type { ImportsModel } from "../types";

export function SalesUploadPanel({ model }: { model: ImportsModel }) {
  const clearSelection = (next: File | null) => {
    model.setFile(next); model.setSalesReplaceConfirmed(false);
    model.setPendingSalesGeneration(null); model.setSalesOverrideReason("");
  };
  return (
    <section className="glass min-w-0 rounded-3xl p-4">
      <div className="mb-3 flex items-center gap-2"><Upload size={16} className="text-indigo-500" /><h3 className="text-sm font-bold">Import fișier vânzări</h3></div>
      <label htmlFor="upload-sales-file" className={cn(
        "mb-3 flex cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed px-4 py-6 text-center transition-all",
        model.file ? "border-emerald-400 bg-emerald-50 dark:border-emerald-600 dark:bg-emerald-950/20" : "border-slate-300 bg-slate-50 hover:border-indigo-400 hover:bg-indigo-50/50 dark:border-slate-600 dark:bg-slate-800/60 dark:hover:border-indigo-500",
      )}>
        {model.file ? <>
          <FileSpreadsheet size={20} className="mb-1 text-emerald-500" />
          <span className="text-xs font-semibold text-emerald-700 dark:text-emerald-300">{model.file.name}</span>
          <span className="mt-0.5 text-[11px] text-slate-400">{(model.file.size / 1024).toFixed(1)} KB · Click pentru a schimba</span>
        </> : <>
          <Upload size={20} className="mb-1 text-slate-400" />
          <span className="text-xs font-semibold text-slate-600 dark:text-slate-300">Click sau drag & drop pentru a încărca</span>
          <span className="mt-0.5 text-[11px] text-slate-400">.xlsx, .xls</span>
        </>}
        <input id="upload-sales-file" type="file" accept=".xlsx,.xls" onChange={(event) => clearSelection(event.target.files?.[0] ?? null)} className="hidden" />
      </label>
      {model.file && <div className="mb-3 rounded-2xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-200">
        <p className="font-bold">Verificare înainte de import</p>
        <p className="mt-1">{model.file.name} · {(model.file.size / 1024 / 1024).toFixed(2)} MB · fișier Excel</p>
        <label className="mt-3 block font-semibold">Cutoff declarat
          <input type="date" value={model.salesCutoff} onChange={(event) => model.setSalesCutoff(event.target.value)} className="mt-1 w-full rounded-xl border border-amber-300 bg-white px-3 py-2 text-xs text-slate-800 dark:border-amber-800 dark:bg-slate-900 dark:text-slate-100" required />
        </label>
        <label className="mt-3 flex cursor-pointer items-start gap-2 font-semibold">
          <input type="checkbox" checked={model.salesReplaceConfirmed} onChange={(event) => model.setSalesReplaceConfirmed(event.target.checked)} className="mt-0.5 h-4 w-4 rounded border-amber-300 text-indigo-600" />
          Confirm că fișierul și cutoff-ul sunt corecte. Validarea creează o generație staged; datele live se schimbă numai după promovarea explicită a manifestului.
        </label>
      </div>}
      <button onClick={() => void model.handleUpload()} disabled={!model.file || !model.salesCutoff || !model.salesReplaceConfirmed || model.uploading} className="w-full rounded-2xl bg-indigo-600 px-4 py-3 text-xs font-bold text-white shadow-lg shadow-indigo-500/30 disabled:opacity-60">
        {model.uploading ? "Validare în desfășurare..." : "Validează fișierul"}
      </button>
      {model.message && <p className={cn(
        "mt-3 rounded-2xl px-3 py-2 text-xs font-semibold",
        model.messageType === "error" ? "bg-rose-50 text-rose-700 dark:bg-rose-950/30 dark:text-rose-300" : model.messageType === "warning" ? "bg-amber-50 text-amber-800 dark:bg-amber-950/30 dark:text-amber-300" : "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-300",
      )}>{model.message}</p>}
      <SalesGenerationPanel model={model} />
    </section>
  );
}

function SalesGenerationPanel({ model }: { model: ImportsModel }) {
  const pending = model.pendingSalesGeneration;
  const blocking = pending?.manifest?.anomalies.some((item) => item.blocking) ?? false;
  if (!pending?.manifest) return null;
  return (
    <div className="mt-3 rounded-2xl border border-indigo-200 bg-indigo-50 p-3 text-xs text-slate-700 dark:border-indigo-900/70 dark:bg-indigo-950/30 dark:text-slate-200">
      <p className="font-bold text-indigo-800 dark:text-indigo-200">Generație validată · datele live sunt neschimbate</p>
      <p className="mt-2">{pending.import_month} / {pending.manifest.cutoff_date} · {pending.rows_imported.toLocaleString("ro-RO")} rânduri · hash {pending.manifest.business_sha256 ?? "indisponibil"}</p>
      {pending.manifest.anomalies.map((anomaly) => <p key={`${anomaly.code}-${anomaly.message}`} className={cn("mt-1", anomaly.blocking ? "font-semibold text-rose-700 dark:text-rose-300" : "text-amber-700 dark:text-amber-300")}>
        {anomaly.blocking ? "Blocant" : "Atenție"} · {anomaly.message}
      </p>)}
      {blocking && <label className="mt-3 block font-semibold">Motiv de override (minimum 10 caractere)
        <textarea value={model.salesOverrideReason} onChange={(event) => model.setSalesOverrideReason(event.target.value)} className="mt-1 min-h-20 w-full rounded-xl border border-rose-300 bg-white px-3 py-2 text-xs text-slate-800 dark:border-rose-800 dark:bg-slate-900 dark:text-slate-100" />
      </label>}
      <button onClick={() => void model.handleSalesPromotion()} disabled={model.promotingSales || (blocking && model.salesOverrideReason.trim().length < 10)} className="mt-3 w-full rounded-xl bg-emerald-600 px-4 py-2.5 font-bold text-white disabled:opacity-60">
        {model.promotingSales ? "Promovare în desfășurare..." : "Promovează generația validată"}
      </button>
    </div>
  );
}

export function ErpReconciliationPanel({ model }: { model: ImportsModel }) {
  return (
    <section className="glass min-w-0 rounded-3xl p-4">
      <div className="mb-1 flex items-center gap-2"><FileSpreadsheet size={16} className="text-sky-600" /><h3 className="text-sm font-bold">Verificare raport detaliat ERP</h3></div>
      <p className="mb-3 text-xs text-slate-500">Reconciliere read-only cu luna Retail selectată și Focus. Coloanele de zile din raport sunt ignorate. Fișierul este șters după succes; la eșec, artefactul privat rămâne cel mult 24h pentru retry și apoi expiră.</p>
      <div className="mb-3 grid gap-2 sm:grid-cols-[180px_1fr]">
        <label className="text-[11px] font-semibold text-slate-500">Luna verificată
          <select value={model.erpReconciliationMonth} onChange={(event) => { model.setErpReconciliationMonth(event.target.value); model.setErpReconciliationResult(null); }} disabled={model.erpReconciliationMonths.length === 0} className="mt-1 w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-800 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100">
            {model.erpReconciliationMonths.length === 0 && <option value="">Niciun import Retail disponibil</option>}
            {model.erpReconciliationMonths.map((month) => <option key={month} value={month}>{formatMonthLabel(month, { month: "long" })}</option>)}
          </select>
        </label>
        <label htmlFor="upload-erp-reconciliation-file" className={cn(
          "flex cursor-pointer items-center gap-3 self-end rounded-xl border border-dashed px-3 py-2 transition-colors",
          model.erpReconciliationFile ? "border-sky-400 bg-sky-50 dark:border-sky-700 dark:bg-sky-950/20" : "border-slate-300 bg-slate-50 hover:border-sky-400 dark:border-slate-600 dark:bg-slate-800/60",
        )}>
          <Upload size={18} className={model.erpReconciliationFile ? "text-sky-600" : "text-slate-400"} />
          <span className="min-w-0 truncate text-xs font-semibold text-slate-600 dark:text-slate-300">{model.erpReconciliationFile ? model.erpReconciliationFile.name : "Selectează raportul ERP (.xls sau .xlsx)"}</span>
          <input id="upload-erp-reconciliation-file" type="file" accept=".xlsx,.xls" onChange={(event) => { model.setErpReconciliationFile(event.target.files?.[0] ?? null); model.setErpReconciliationResult(null); model.setErpReconciliationError(""); }} className="hidden" />
        </label>
      </div>
      <button type="button" onClick={() => void model.handleErpReconciliation()} disabled={!model.erpReconciliationFile || !model.erpReconciliationMonth || model.erpReconciliationBusy} className="w-full rounded-2xl bg-sky-600 px-4 py-3 text-xs font-bold text-white shadow-lg shadow-sky-500/25 disabled:opacity-60">
        {model.erpReconciliationBusy ? "Se validează și se compară..." : "Verifică raportul fără import"}
      </button>
      {model.erpReconciliationError && <p className="mt-3 rounded-2xl bg-rose-50 px-3 py-2 text-xs font-semibold text-rose-700 dark:bg-rose-950/30 dark:text-rose-300">{model.erpReconciliationError}</p>}
      {model.erpReconciliationResult && <ErpReconciliationResult result={model.erpReconciliationResult} />}
    </section>
  );
}

export function PromoActualsPanel({ model }: { model: ImportsModel }) {
  return (
    <section className="glass rounded-3xl p-4">
      <div className="mb-3 flex items-center gap-2"><FileSpreadsheet size={16} className="text-emerald-600" /><h3 className="text-sm font-bold">Import tabel promo firmă</h3></div>
      <div className="mb-3 grid gap-2 sm:grid-cols-2">
        <label className="text-[11px] font-semibold text-slate-500">Luna raportului<input type="month" value={model.promoActualsMonth} onChange={(event) => model.setPromoActualsMonth(event.target.value)} className="mt-1 w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-800 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100" /></label>
        <label className="text-[11px] font-semibold text-slate-500">Raport până la data<input type="date" value={model.promoActualsCutoff} onChange={(event) => model.setPromoActualsCutoff(event.target.value)} className="mt-1 w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-800 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100" /></label>
      </div>
      <label htmlFor="upload-promo-actuals-file" className={cn("mb-3 flex cursor-pointer items-center gap-3 rounded-2xl border border-dashed px-3 py-3 transition-colors", model.promoActualsFile ? "border-emerald-400 bg-emerald-50 dark:border-emerald-700 dark:bg-emerald-950/20" : "border-slate-300 bg-slate-50 hover:border-emerald-400 dark:border-slate-600 dark:bg-slate-800/60")}>
        <Upload size={18} className={model.promoActualsFile ? "text-emerald-600" : "text-slate-400"} />
        <span className="min-w-0 truncate text-xs font-semibold text-slate-600 dark:text-slate-300">{model.promoActualsFile ? model.promoActualsFile.name : "Selectează raportul firmei (.xls sau .xlsx)"}</span>
        <input id="upload-promo-actuals-file" type="file" accept=".xlsx,.xls" onChange={(event) => model.setPromoActualsFile(event.target.files?.[0] ?? null)} className="hidden" />
      </label>
      <button type="button" onClick={() => void model.handlePromoActualsUpload()} disabled={!model.promoActualsFile || model.promoActualsUploading} className="w-full rounded-2xl bg-emerald-600 px-4 py-3 text-xs font-bold text-white shadow-lg shadow-emerald-500/25 disabled:opacity-60">
        {model.promoActualsUploading ? "Se validează și se aplică..." : "Importă raport promo"}
      </button>
      {model.promoActualsMessage && <p className="mt-3 rounded-2xl bg-emerald-50 px-3 py-2 text-xs font-semibold text-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-300">{model.promoActualsMessage}</p>}
    </section>
  );
}

export function ImportHistoryPanel({ model }: { model: ImportsModel }) {
  return (
    <section className="glass rounded-3xl p-4">
      <div className="mb-3 flex items-center justify-between"><h3 className="text-sm font-bold">Istoric importuri</h3><span className="text-[11px] text-slate-500">{model.history.length} snapshot-uri</span></div>
      <div className="max-h-40 space-y-2 overflow-y-auto">
        {model.history.slice(0, 8).map((entry) => <div key={entry.id} className="rounded-2xl bg-slate-50 p-3 text-xs dark:bg-slate-800/60">
          <p className="font-semibold">{entry.import_month} · {entry.filename}</p>
          <p className="mt-1 text-slate-500">{entry.rows_imported ?? 0} rânduri · {entry.status} · {entry.is_month_final ? "✓ Final" : "Intermediar"} · {formatIsoDateTime(entry.created_at)}{entry.duration_seconds != null && <> · {entry.duration_seconds < 60 ? `${entry.duration_seconds.toFixed(1)} s` : `${(entry.duration_seconds / 60).toFixed(1)} min`}</>}</p>
          {entry.coverage_report?.active_store_coverage_pct != null && <p className="mt-1 text-slate-500">Coverage magazine active {entry.coverage_report.active_store_coverage_pct}% · {entry.coverage_report.missing_active_store_count ?? 0} absente · {entry.coverage_report.store_activity_writes ?? 0} schimbări de stare</p>}
        </div>)}
        {model.history.length === 0 && <p className="text-sm font-semibold text-slate-500">Nu există istoric încă.</p>}
      </div>
    </section>
  );
}

