import {
  Download,
  Eye,
  LineChart as LineChartIcon,
  SlidersHorizontal,
  Table2,
  XCircle,
} from "lucide-react";

import { TableHeaderCell } from "../../../components/common/TableHeader";
import { cn } from "../../../lib/utils";
import type { ExportsModel } from "../types";
import {
  ALL_DAYS,
  CheckRow,
  ColumnBlock,
  FieldBlock,
  FilterBlock,
  LevelBlock,
  ModeButton,
  PeriodSelector,
  type ExportStep,
} from "./controls";

const toggle = (values: string[], value: string, minOne = false) =>
  values.includes(value)
    ? minOne && values.length === 1 ? values : values.filter((item) => item !== value)
    : [...values, value];

const updateValues = (
  model: ExportsModel,
  setter: ExportsModel["setExportDimensions"],
  key: string,
  minOne = false,
) => {
  setter((current) => toggle(current, key, minOne));
  model.setPreview(null);
};

export function ExportSetupPanel({ model }: { model: ExportsModel }) {
  return (
    <section className={cn("glass relative z-40 overflow-visible rounded-3xl p-4", model.exportStep === 4 && "hidden")}>
      <div className="mb-3 flex items-center gap-2"><SlidersHorizontal size={16} className="text-indigo-500" /><h3 className="text-sm font-bold">Builder export Excel</h3></div>
      <div className={cn("mb-4 grid gap-2 sm:grid-cols-2", model.exportStep !== 1 && "hidden")}>
        <ModeButton active={model.exportMode === "table"} icon={<Table2 size={16} />} title="Tabel detaliat" subtitle="Coloane si metrici selectate" onClick={() => model.handleExportModeChange("table")} />
        <ModeButton active={model.exportMode === "daily_comparison"} icon={<LineChartIcon size={16} />} title="Evolutie zilnica" subtitle="Comparatie pe zile si niveluri" onClick={() => model.handleExportModeChange("daily_comparison")} />
      </div>
      <div className="grid gap-3 lg:grid-cols-4">
        <div className={cn(model.exportStep !== 1 && "hidden")}>
          {model.exportMode === "table" ? <FieldBlock title="Dataset">
            <select value={model.exportDataset} onChange={(event) => model.handleDatasetChange(event.target.value)} className="w-full rounded-2xl border border-slate-200 bg-white px-3 py-2 text-xs font-semibold outline-none dark:border-slate-700 dark:bg-slate-900">
              {model.catalog?.datasets.map((dataset) => <option key={dataset.key} value={dataset.key}>{dataset.label}</option>)}
            </select>
            {model.selectedDataset && <p className="mt-2 text-[11px] text-slate-500">{model.selectedDataset.description}</p>}
          </FieldBlock> : <FieldBlock title="Analiza"><p className="rounded-2xl border border-emerald-100 bg-emerald-50 px-3 py-2 text-xs font-semibold text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/30 dark:text-emerald-300">Evolutie pe ziua lunii</p></FieldBlock>}
        </div>
        <div className={cn("lg:col-span-2", model.exportStep !== 2 && "hidden")}>
          <FieldBlock title="Perioada"><PeriodSelector
            years={model.availableYears} selectedYears={model.selectedYears} onYearToggle={model.toggleYear}
            monthNumbers={model.availableMonthNumbers} selectedMonthNumbers={model.selectedMonthNumbers} onMonthToggle={model.toggleMonthNumber}
            selectedDays={model.selectedDays} onDayToggle={model.toggleDay}
            onSelectAllDays={() => { model.setSelectedDays(ALL_DAYS); model.setPreview(null); }}
            onSelectFirstNineDays={() => { model.setSelectedDays(ALL_DAYS.slice(0, 9)); model.setPreview(null); }}
            selectedMonthCount={model.exportMonths.length}
          /></FieldBlock>
        </div>
        <div className={cn(model.exportStep !== 2 && "hidden")}><FieldBlock title="Optiuni">
          <div className="space-y-1 rounded-2xl border border-slate-200 bg-white p-2 dark:border-slate-700 dark:bg-slate-900">
            {!model.isIncentiveProductsExport && <CheckRow label="Include magazine inchise" checked={model.includeClosedStores} onChange={() => { model.setIncludeClosedStores((value) => !value); model.setPreview(null); }} />}
            {model.exportMode === "table" && !model.isIncentiveProductsExport && <CheckRow label="Vanzare lunara pe perioada selectata" checked={model.monthlyMetrics.includes("total_sales")} onChange={() => updateValues(model, model.setMonthlyMetrics, "total_sales")} />}
          </div>
        </FieldBlock></div>
      </div>
    </section>
  );
}

export function ExportFiltersPanel({ model }: { model: ExportsModel }) {
  return (
    <section className={cn("glass rounded-3xl p-4", model.exportStep !== 2 && "hidden")}>
      <h3 className="mb-3 text-sm font-bold">Filtre</h3>
      <FilterBlock title="Firma" values={model.filterOptions?.firme ?? []} selected={model.exportFilters.firma} onToggle={(value) => model.toggleFilter("firma", value)} />
      <FilterBlock title="RM" values={model.filterOptions?.regionali ?? []} selected={model.exportFilters.regional} onToggle={(value) => model.toggleFilter("regional", value)} />
      <FilterBlock title="ASM" values={model.filterOptions?.asmi ?? []} selected={model.exportFilters.asm} onToggle={(value) => model.toggleFilter("asm", value)} />
      <FilterBlock title="Magazine" values={(model.filterOptions?.magazine ?? []).map((item) => ({ key: item.site_code, label: item.locatie }))} selected={model.exportFilters.site_code} onToggle={(value) => model.toggleFilter("site_code", value)} />
      <FilterBlock title="Agenti" values={(model.filterOptions?.agenti ?? []).map((item) => ({ key: `${item.agent}|${item.site_code}`, value: item.agent, label: `${item.agent} · ${item.locatie}` }))} selected={model.exportFilters.agent} onToggle={(value) => model.toggleFilter("agent", value)} />
    </section>
  );
}

function TableColumnSelection({ model }: { model: ExportsModel }) {
  if (model.isIncentiveProductsExport) return <p className="rounded-2xl bg-amber-50 px-3 py-2 text-[11px] font-semibold text-amber-800 dark:bg-amber-950/30 dark:text-amber-200">Coloane fixe: categorie, subcategorie, produs, vanzari, excluderi promo, unitati eligibile si plata. Vanzarile respecta zilele bifate; pragul de plata ramane lunar, ca in Focus.</p>;
  return <>
    <ColumnBlock title="Identificare" columns={model.selectedDataset?.dimensions ?? []} selected={model.exportDimensions} onToggle={(key) => updateValues(model, model.setExportDimensions, key, true)} />
    <ColumnBlock title="Metrici total" columns={model.catalog?.metrics ?? []} selected={model.exportMetrics} onToggle={(key) => updateValues(model, model.setExportMetrics, key, true)} />
    <ColumnBlock title="Evolutie lunara" columns={model.catalog?.monthly_metrics ?? []} selected={model.monthlyMetrics} onToggle={(key) => updateValues(model, model.setMonthlyMetrics, key)} />
    <ColumnBlock title="Evolutie zilnica" columns={model.catalog?.daily_metrics ?? []} selected={model.dailyMetrics} onToggle={(key) => updateValues(model, model.setDailyMetrics, key)} />
  </>;
}

export function ExportColumnsPanel({ model }: { model: ExportsModel }) {
  return (
    <section className={cn("glass rounded-3xl p-4", model.exportStep !== 3 && "hidden")}>
      <h3 className="mb-3 text-sm font-bold">{model.exportMode === "table" ? "Coloane" : "Grafic si tabele"}</h3>
      {model.exportMode === "table" ? <TableColumnSelection model={model} /> : <>
        <ColumnBlock title="Metrici zilnice" columns={model.catalog?.daily_metrics ?? []} selected={model.dailyMetrics.length > 0 ? model.dailyMetrics : ["total_sales"]} onToggle={(key) => {
          model.setDailyMetrics((current) => toggle(current.length > 0 ? current : ["total_sales"], key, true)); model.setPreview(null);
        }} />
        <LevelBlock levels={model.catalog?.comparison_levels ?? []} selected={model.comparisonLevels} onToggle={(key) => updateValues(model, model.setComparisonLevels, key, true)} />
      </>}
    </section>
  );
}

function ExportOperationStatus({ model }: { model: ExportsModel }) {
  if (!model.exportOperation) return null;
  const operation = model.exportOperation;
  return (
    <div className={cn("mb-3 flex items-center justify-between gap-3 rounded-2xl px-3 py-2 text-xs font-semibold", ["failed", "cancelled", "expired"].includes(operation.status) ? "bg-rose-50 text-rose-700 dark:bg-rose-950/30 dark:text-rose-300" : "bg-indigo-50 text-indigo-700 dark:bg-indigo-950/30 dark:text-indigo-300")}>
      <span>Export complex #{operation.id} · {operation.status}{operation.artifact_size ? ` · ${operation.artifact_size.toLocaleString("ro-RO")} bytes` : ""}</span>
      {(["queued", "running"].includes(operation.status)) && <button type="button" onClick={() => void model.handleCancelExport()} disabled={model.exportCancelling} className="inline-flex shrink-0 items-center gap-1 rounded-xl border border-current px-2 py-1 disabled:opacity-50"><XCircle size={13} />{model.exportCancelling ? "Se anulează" : "Anulează"}</button>}
      {operation.status === "completed" && model.exportMessage && <button type="button" onClick={() => void model.handleRetryExportDownload()} disabled={model.exportBusy} className="inline-flex shrink-0 items-center gap-1 rounded-xl border border-current px-2 py-1 disabled:opacity-50"><Download size={13} />Reîncearcă descărcarea</button>}
    </div>
  );
}

function ExportPreviewTable({ model }: { model: ExportsModel }) {
  if (!model.preview) return null;
  return (
    <div className="overflow-auto rounded-2xl border border-slate-200 dark:border-slate-700"><table className="min-w-max border-collapse text-xs">
      <thead className="bg-slate-50 dark:bg-slate-800"><tr>{model.preview.columns.map((column) => <TableHeaderCell key={column.key} className="whitespace-nowrap">{column.label}</TableHeaderCell>)}</tr></thead>
      <tbody>{model.preview.rows.map((row, index) => <tr key={index} className={index % 2 === 0 ? "bg-white dark:bg-slate-900/40" : "bg-slate-50/60 dark:bg-slate-800/40"}>{model.preview?.columns.map((column) => <td key={column.key} className="whitespace-nowrap px-3 py-2">{String(row[column.key] ?? "")}</td>)}</tr>)}</tbody>
    </table></div>
  );
}

export function ExportPreviewPanel({ model }: { model: ExportsModel }) {
  return (
    <section className={cn("glass rounded-3xl p-4", model.exportStep !== 4 && "hidden")}>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div><h3 className="text-sm font-bold">Preview si export</h3><p className="text-[11px] text-slate-500">{model.preview ? `${model.preview.total_rows} randuri${model.preview.truncated ? " · preview limitat" : ""}` : model.exportMode === "daily_comparison" ? "Preview pe nivelul General." : "Genereaza preview inainte de export."}</p></div>
        <div className="flex gap-2">
          <button type="button" onClick={() => void model.handlePreviewExport()} disabled={model.exportBusy || model.exportMonths.length === 0 || model.selectedDays.length === 0} className="inline-flex items-center gap-2 rounded-2xl border border-slate-200 bg-white px-3 py-2 text-xs font-bold text-slate-600 shadow-sm disabled:opacity-60 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300"><Eye size={14} />Preview</button>
          <button type="button" onClick={() => void model.handleDownloadExport()} disabled={model.exportBusy || model.exportMonths.length === 0 || model.selectedDays.length === 0} className="inline-flex items-center gap-2 rounded-2xl bg-indigo-600 px-3 py-2 text-xs font-bold text-white shadow-lg shadow-indigo-500/25 disabled:opacity-60"><Download size={14} />Export Excel</button>
        </div>
      </div>
      <ExportOperationStatus model={model} />
      {model.exportMessage && <p className="mb-3 rounded-2xl bg-rose-50 px-3 py-2 text-xs font-semibold text-rose-700 dark:bg-rose-950/30 dark:text-rose-300">{model.exportMessage}</p>}
      <ExportPreviewTable model={model} />
    </section>
  );
}

export function ExportNavigation({ model }: { model: ExportsModel }) {
  return (
    <div className="export-mobile-actions sticky bottom-[calc(4.75rem+env(safe-area-inset-bottom))] z-30 flex items-center justify-between rounded-2xl border border-slate-200 bg-white/95 p-3 shadow-lg backdrop-blur-xl dark:border-slate-700 dark:bg-slate-900/95 lg:bottom-4 lg:static">
      <button type="button" onClick={() => model.setExportStep(Math.max(1, model.exportStep - 1) as ExportStep)} disabled={model.exportStep === 1} className="rounded-xl border border-slate-200 px-4 py-2 text-xs font-bold text-slate-600 disabled:opacity-40 dark:border-slate-700 dark:text-slate-300">Înapoi</button>
      <span className="text-xs font-semibold text-slate-500">Pasul {model.exportStep} din 4</span>
      <button type="button" onClick={() => model.setExportStep(Math.min(4, model.exportStep + 1) as ExportStep)} disabled={model.exportStep === 4 || (model.exportStep === 2 && model.exportMonths.length === 0)} className="rounded-xl bg-indigo-600 px-4 py-2 text-xs font-bold text-white disabled:opacity-40">Continuă</button>
    </div>
  );
}

