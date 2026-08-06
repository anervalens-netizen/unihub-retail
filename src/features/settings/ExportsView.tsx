import {
  Download,
  Eye,
  LineChart as LineChartIcon,
  SlidersHorizontal,
  Table2,
  XCircle,
} from "lucide-react";

import { cn } from "../../lib/utils";
import { TableHeaderCell } from "../../components/common/TableHeader";
import {
  ALL_DAYS,
  CheckRow,
  ColumnBlock,
  ExportWorkflow,
  FieldBlock,
  FilterBlock,
  LevelBlock,
  ModeButton,
  PeriodSelector,
  type ExportStep,
} from "./exports/controls";
import type { ExportsModel } from "./types";

const toggle = (values: string[], value: string, minOne = false) =>
  values.includes(value)
    ? minOne && values.length === 1
      ? values
      : values.filter((item) => item !== value)
    : [...values, value];

export function ExportsView({ model }: { model: ExportsModel }) {
  const {
    catalog,
    filterOptions,
    exportMode,
    handleExportModeChange,
    exportDataset,
    handleDatasetChange,
    selectedDataset,
    availableYears,
    selectedYears,
    toggleYear,
    availableMonthNumbers,
    selectedMonthNumbers,
    toggleMonthNumber,
    selectedDays,
    setSelectedDays,
    toggleDay,
    exportMonths,
    includeClosedStores,
    setIncludeClosedStores,
    isIncentiveProductsExport,
    exportFilters,
    toggleFilter,
    exportDimensions,
    setExportDimensions,
    exportMetrics,
    setExportMetrics,
    monthlyMetrics,
    setMonthlyMetrics,
    dailyMetrics,
    setDailyMetrics,
    comparisonLevels,
    setComparisonLevels,
    exportStep,
    setExportStep,
    exportBusy,
    exportCancelling,
    handlePreviewExport,
    handleDownloadExport,
    handleCancelExport,
    handleRetryExportDownload,
    exportMessage,
    exportOperation,
    preview,
    setPreview,
  } = model;

  const resetPreview = () => setPreview(null);
  const updateValues = (
    setter: typeof setExportDimensions,
    key: string,
    minOne = false,
  ) => {
    setter((current) => toggle(current, key, minOne));
    resetPreview();
  };

  return (
    <div className="space-y-3">
      <ExportWorkflow step={exportStep} onChange={setExportStep} />
      <section
        className={cn(
          "glass relative z-40 overflow-visible rounded-3xl p-4",
          exportStep === 4 && "hidden",
        )}
      >
        <div className="mb-3 flex items-center gap-2">
          <SlidersHorizontal size={16} className="text-indigo-500" />
          <h3 className="text-sm font-bold">Builder export Excel</h3>
        </div>
        <div
          className={cn(
            "mb-4 grid gap-2 sm:grid-cols-2",
            exportStep !== 1 && "hidden",
          )}
        >
          <ModeButton
            active={exportMode === "table"}
            icon={<Table2 size={16} />}
            title="Tabel detaliat"
            subtitle="Coloane si metrici selectate"
            onClick={() => handleExportModeChange("table")}
          />
          <ModeButton
            active={exportMode === "daily_comparison"}
            icon={<LineChartIcon size={16} />}
            title="Evolutie zilnica"
            subtitle="Comparatie pe zile si niveluri"
            onClick={() => handleExportModeChange("daily_comparison")}
          />
        </div>
        <div className="grid gap-3 lg:grid-cols-4">
          <div className={cn(exportStep !== 1 && "hidden")}>
            {exportMode === "table" ? (
              <FieldBlock title="Dataset">
                <select
                  value={exportDataset}
                  onChange={(event) => handleDatasetChange(event.target.value)}
                  className="w-full rounded-2xl border border-slate-200 bg-white px-3 py-2 text-xs font-semibold outline-none dark:border-slate-700 dark:bg-slate-900"
                >
                  {catalog?.datasets.map((dataset) => (
                    <option key={dataset.key} value={dataset.key}>
                      {dataset.label}
                    </option>
                  ))}
                </select>
                {selectedDataset && (
                  <p className="mt-2 text-[11px] text-slate-500">
                    {selectedDataset.description}
                  </p>
                )}
              </FieldBlock>
            ) : (
              <FieldBlock title="Analiza">
                <p className="rounded-2xl border border-emerald-100 bg-emerald-50 px-3 py-2 text-xs font-semibold text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/30 dark:text-emerald-300">
                  Evolutie pe ziua lunii
                </p>
              </FieldBlock>
            )}
          </div>
          <div className={cn("lg:col-span-2", exportStep !== 2 && "hidden")}>
            <FieldBlock title="Perioada">
              <PeriodSelector
                years={availableYears}
                selectedYears={selectedYears}
                onYearToggle={toggleYear}
                monthNumbers={availableMonthNumbers}
                selectedMonthNumbers={selectedMonthNumbers}
                onMonthToggle={toggleMonthNumber}
                selectedDays={selectedDays}
                onDayToggle={toggleDay}
                onSelectAllDays={() => {
                  setSelectedDays(ALL_DAYS);
                  resetPreview();
                }}
                onSelectFirstNineDays={() => {
                  setSelectedDays(ALL_DAYS.slice(0, 9));
                  resetPreview();
                }}
                selectedMonthCount={exportMonths.length}
              />
            </FieldBlock>
          </div>
          <div className={cn(exportStep !== 2 && "hidden")}>
            <FieldBlock title="Optiuni">
              <div className="space-y-1 rounded-2xl border border-slate-200 bg-white p-2 dark:border-slate-700 dark:bg-slate-900">
                {!isIncentiveProductsExport && (
                  <CheckRow
                    label="Include magazine inchise"
                    checked={includeClosedStores}
                    onChange={() => {
                      setIncludeClosedStores((value) => !value);
                      resetPreview();
                    }}
                  />
                )}
                {exportMode === "table" && !isIncentiveProductsExport && (
                  <CheckRow
                    label="Vanzare lunara pe perioada selectata"
                    checked={monthlyMetrics.includes("total_sales")}
                    onChange={() =>
                      updateValues(setMonthlyMetrics, "total_sales")
                    }
                  />
                )}
              </div>
            </FieldBlock>
          </div>
        </div>
      </section>

      <div className="relative z-0 grid gap-3 lg:grid-cols-2">
        <section
          className={cn("glass rounded-3xl p-4", exportStep !== 2 && "hidden")}
        >
          <h3 className="mb-3 text-sm font-bold">Filtre</h3>
          <FilterBlock
            title="Firma"
            values={filterOptions?.firme ?? []}
            selected={exportFilters.firma}
            onToggle={(value) => toggleFilter("firma", value)}
          />
          <FilterBlock
            title="RM"
            values={filterOptions?.regionali ?? []}
            selected={exportFilters.regional}
            onToggle={(value) => toggleFilter("regional", value)}
          />
          <FilterBlock
            title="ASM"
            values={filterOptions?.asmi ?? []}
            selected={exportFilters.asm}
            onToggle={(value) => toggleFilter("asm", value)}
          />
          <FilterBlock
            title="Magazine"
            values={(filterOptions?.magazine ?? []).map((item) => ({
              key: item.site_code,
              label: item.locatie,
            }))}
            selected={exportFilters.site_code}
            onToggle={(value) => toggleFilter("site_code", value)}
          />
          <FilterBlock
            title="Agenti"
            values={(filterOptions?.agenti ?? []).map((item) => ({
              key: `${item.agent}|${item.site_code}`,
              value: item.agent,
              label: `${item.agent} · ${item.locatie}`,
            }))}
            selected={exportFilters.agent}
            onToggle={(value) => toggleFilter("agent", value)}
          />
        </section>
        <section
          className={cn("glass rounded-3xl p-4", exportStep !== 3 && "hidden")}
        >
          <h3 className="mb-3 text-sm font-bold">
            {exportMode === "table" ? "Coloane" : "Grafic si tabele"}
          </h3>
          {exportMode === "table" ? (
            isIncentiveProductsExport ? (
              <p className="rounded-2xl bg-amber-50 px-3 py-2 text-[11px] font-semibold text-amber-800 dark:bg-amber-950/30 dark:text-amber-200">
                Coloane fixe: categorie, subcategorie, produs, vanzari,
                excluderi promo, unitati eligibile si plata. Vanzarile respecta
                zilele bifate; pragul de plata ramane lunar, ca in Focus.
              </p>
            ) : (
              <>
                <ColumnBlock
                  title="Identificare"
                  columns={selectedDataset?.dimensions ?? []}
                  selected={exportDimensions}
                  onToggle={(key) =>
                    updateValues(setExportDimensions, key, true)
                  }
                />
                <ColumnBlock
                  title="Metrici total"
                  columns={catalog?.metrics ?? []}
                  selected={exportMetrics}
                  onToggle={(key) => updateValues(setExportMetrics, key, true)}
                />
                <ColumnBlock
                  title="Evolutie lunara"
                  columns={catalog?.monthly_metrics ?? []}
                  selected={monthlyMetrics}
                  onToggle={(key) => updateValues(setMonthlyMetrics, key)}
                />
                <ColumnBlock
                  title="Evolutie zilnica"
                  columns={catalog?.daily_metrics ?? []}
                  selected={dailyMetrics}
                  onToggle={(key) => updateValues(setDailyMetrics, key)}
                />
              </>
            )
          ) : (
            <>
              <ColumnBlock
                title="Metrici zilnice"
                columns={catalog?.daily_metrics ?? []}
                selected={
                  dailyMetrics.length > 0 ? dailyMetrics : ["total_sales"]
                }
                onToggle={(key) => {
                  setDailyMetrics((current) =>
                    toggle(
                      current.length > 0 ? current : ["total_sales"],
                      key,
                      true,
                    ),
                  );
                  resetPreview();
                }}
              />
              <LevelBlock
                levels={catalog?.comparison_levels ?? []}
                selected={comparisonLevels}
                onToggle={(key) => updateValues(setComparisonLevels, key, true)}
              />
            </>
          )}
        </section>
      </div>

      <section
        className={cn("glass rounded-3xl p-4", exportStep !== 4 && "hidden")}
      >
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div>
            <h3 className="text-sm font-bold">Preview si export</h3>
            <p className="text-[11px] text-slate-500">
              {preview
                ? `${preview.total_rows} randuri${preview.truncated ? " · preview limitat" : ""}`
                : exportMode === "daily_comparison"
                  ? "Preview pe nivelul General."
                  : "Genereaza preview inainte de export."}
            </p>
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => void handlePreviewExport()}
              disabled={
                exportBusy ||
                exportMonths.length === 0 ||
                selectedDays.length === 0
              }
              className="inline-flex items-center gap-2 rounded-2xl border border-slate-200 bg-white px-3 py-2 text-xs font-bold text-slate-600 shadow-sm disabled:opacity-60 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300"
            >
              <Eye size={14} />
              Preview
            </button>
            <button
              type="button"
              onClick={() => void handleDownloadExport()}
              disabled={
                exportBusy ||
                exportMonths.length === 0 ||
                selectedDays.length === 0
              }
              className="inline-flex items-center gap-2 rounded-2xl bg-indigo-600 px-3 py-2 text-xs font-bold text-white shadow-lg shadow-indigo-500/25 disabled:opacity-60"
            >
              <Download size={14} />
              Export Excel
            </button>
          </div>
        </div>
        {exportOperation && (
          <div
            className={cn(
              "mb-3 flex items-center justify-between gap-3 rounded-2xl px-3 py-2 text-xs font-semibold",
              exportOperation.status === "failed" ||
                exportOperation.status === "cancelled" ||
                exportOperation.status === "expired"
                ? "bg-rose-50 text-rose-700 dark:bg-rose-950/30 dark:text-rose-300"
                : "bg-indigo-50 text-indigo-700 dark:bg-indigo-950/30 dark:text-indigo-300",
            )}
          >
            <span>
              Export complex #{exportOperation.id} · {exportOperation.status}
              {exportOperation.artifact_size
                ? ` · ${exportOperation.artifact_size.toLocaleString("ro-RO")} bytes`
                : ""}
            </span>
            {(exportOperation.status === "queued" ||
              exportOperation.status === "running") && (
              <button
                type="button"
                onClick={() => void handleCancelExport()}
                disabled={exportCancelling}
                className="inline-flex shrink-0 items-center gap-1 rounded-xl border border-current px-2 py-1 disabled:opacity-50"
              >
                <XCircle size={13} />
                {exportCancelling ? "Se anulează" : "Anulează"}
              </button>
            )}
            {exportOperation.status === "completed" && exportMessage && (
              <button
                type="button"
                onClick={() => void handleRetryExportDownload()}
                disabled={exportBusy}
                className="inline-flex shrink-0 items-center gap-1 rounded-xl border border-current px-2 py-1 disabled:opacity-50"
              >
                <Download size={13} />
                Reîncearcă descărcarea
              </button>
            )}
          </div>
        )}
        {exportMessage && (
          <p className="mb-3 rounded-2xl bg-rose-50 px-3 py-2 text-xs font-semibold text-rose-700 dark:bg-rose-950/30 dark:text-rose-300">
            {exportMessage}
          </p>
        )}
        {preview && (
          <div className="overflow-auto rounded-2xl border border-slate-200 dark:border-slate-700">
            <table className="min-w-max border-collapse text-xs">
              <thead className="bg-slate-50 dark:bg-slate-800">
                <tr>
                  {preview.columns.map((column) => (
                    <TableHeaderCell
                      key={column.key}
                      className="whitespace-nowrap"
                    >
                      {column.label}
                    </TableHeaderCell>
                  ))}
                </tr>
              </thead>
              <tbody>
                {preview.rows.map((row, index) => (
                  <tr
                    key={index}
                    className={
                      index % 2 === 0
                        ? "bg-white dark:bg-slate-900/40"
                        : "bg-slate-50/60 dark:bg-slate-800/40"
                    }
                  >
                    {preview.columns.map((column) => (
                      <td
                        key={column.key}
                        className="whitespace-nowrap px-3 py-2"
                      >
                        {String(row[column.key] ?? "")}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      <div className="export-mobile-actions sticky bottom-[calc(4.75rem+env(safe-area-inset-bottom))] z-30 flex items-center justify-between rounded-2xl border border-slate-200 bg-white/95 p-3 shadow-lg backdrop-blur-xl dark:border-slate-700 dark:bg-slate-900/95 lg:bottom-4 lg:static">
        <button
          type="button"
          onClick={() =>
            setExportStep(Math.max(1, exportStep - 1) as ExportStep)
          }
          disabled={exportStep === 1}
          className="rounded-xl border border-slate-200 px-4 py-2 text-xs font-bold text-slate-600 disabled:opacity-40 dark:border-slate-700 dark:text-slate-300"
        >
          Înapoi
        </button>
        <span className="text-xs font-semibold text-slate-500">
          Pasul {exportStep} din 4
        </span>
        <button
          type="button"
          onClick={() =>
            setExportStep(Math.min(4, exportStep + 1) as ExportStep)
          }
          disabled={
            exportStep === 4 || (exportStep === 2 && exportMonths.length === 0)
          }
          className="rounded-xl bg-indigo-600 px-4 py-2 text-xs font-bold text-white disabled:opacity-40"
        >
          Continuă
        </button>
      </div>
    </div>
  );
}
