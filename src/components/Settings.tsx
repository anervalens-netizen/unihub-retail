import { useEffect, useMemo, useState, type Dispatch, type SetStateAction } from 'react';
import { useQuery } from '@tanstack/react-query';

import { ThemeSwitcher } from './ThemeSwitcher';
import { Download, Eye, FileSpreadsheet, LineChart as LineChartIcon, SlidersHorizontal, Table2, Upload } from 'lucide-react';
import { downloadExport, getExportCatalog, previewExport } from '../api/exports';
import type { ExportFilters, ExportPreview, ExportRequest } from '../api/exports';
import { getFilterOptions } from '../api/filters';
import { getImportHistory, getImportJobStatus, promoteSalesGeneration, uploadErpReconciliationFile, uploadPromoActualsFile, uploadSalesFile } from '../api/imports';
import type { ErpReconciliationResponse } from '../api/imports';
import type { FilterOptions, ImportHistoryEntry, ImportResponse } from '../api/types';
import { cn } from '../lib/utils';
import { getCachedView, setCachedView } from '../lib/viewCache';
import { downloadBlob } from '../lib/download';
import { useAuth } from '../auth/AuthContext';
import { canAdministerImports, canExportReports } from '../auth/permissions';
import { ApiError } from '../api/client';
import { pollImportJob } from '../lib/importJobPolling';
import { formatIsoDateInput, formatIsoDateTime, getCurrentYearMonth, shiftIsoDate, formatMonthLabel } from '../lib/dates';
import { SegmentedTabs } from './common/SegmentedTabs';
import { PageHeader } from './common/DesktopLayout';
import { TableHeaderCell } from './common/TableHeader';
import { useAvailableMonths } from '../hooks/useAvailableMonths';
import * as settingsPresenters from '../features/settings/presenters';
import {
  ALL_DAYS,
  ColumnBlock,
  ExportWorkflow,
  FieldBlock,
  FilterBlock,
  LevelBlock,
  ModeButton,
  PeriodSelector,
  CheckRow,
  type ExportStep,
} from '../features/settings/exports/controls';
import { ErpReconciliationResult } from '../features/settings/imports/ErpReconciliationResult';

interface SettingsProps {
  theme: string;
  setTheme: (theme: string) => void;
  onImportCompleted: (month: string) => void;
}

const SETTINGS_CACHE_TTL_MS = 5 * 60 * 1000;
const IMPORT_POLL_INTERVAL_MS = 1500;
const IMPORT_POLL_LIMIT = 1200;
const IMPORT_POLL_MAX_CONSECUTIVE_ERRORS = 20;
const CACHE_KEY = 'settings:imports';
const EMPTY_EXPORT_FILTERS: ExportFilters = {
  firma: [],
  regional: [],
  asm: [],
  site_code: [],
  agent: [],
};
const DEFAULT_EXPORT_METRICS = [
  'total_sales',
  'total_quantity',
  'total_receipts',
  'target',
  'target_progress_pct',
  'proc_bon2acc',
  'prc_focus_acc_qty',
  'daily_average',
];
const DEFAULT_DAILY_COMPARISON_METRICS = ['total_sales'];
const DEFAULT_COMPARISON_LEVELS = ['general', 'asms', 'stores', 'agents'];
type ExportMode = 'table' | 'daily_comparison';
type SettingsSection = 'imports' | 'exports' | 'preferences';
const INCENTIVE_PRODUCTS_DATASET = 'incentive_products';

type SettingsCatalog = Awaited<ReturnType<typeof getExportCatalog>>;
type SettingsDataset = SettingsCatalog['datasets'][number];

interface SettingsViewProps {
  theme: string;
  setTheme: (theme: string) => void;
  canImportSales: boolean;
  canUseExports: boolean;
  section: SettingsSection;
  setSection: Dispatch<SetStateAction<SettingsSection>>;
  file: File | null;
  setFile: Dispatch<SetStateAction<File | null>>;
  salesReplaceConfirmed: boolean;
  setSalesReplaceConfirmed: Dispatch<SetStateAction<boolean>>;
  setPendingSalesGeneration: Dispatch<SetStateAction<ImportResponse | null>>;
  salesCutoff: string;
  setSalesCutoff: Dispatch<SetStateAction<string>>;
  uploading: boolean;
  handleUpload: () => Promise<void>;
  message: string;
  messageType: 'success' | 'warning' | 'error';
  pendingSalesGeneration: ImportResponse | null;
  salesOverrideReason: string;
  setSalesOverrideReason: Dispatch<SetStateAction<string>>;
  promotingSales: boolean;
  handleSalesPromotion: () => Promise<void>;
  history: ImportHistoryEntry[];
  erpReconciliationMonths: string[];
  erpReconciliationMonth: string;
  setErpReconciliationMonth: Dispatch<SetStateAction<string>>;
  erpReconciliationFile: File | null;
  setErpReconciliationFile: Dispatch<SetStateAction<File | null>>;
  setErpReconciliationError: Dispatch<SetStateAction<string>>;
  setErpReconciliationResult: Dispatch<SetStateAction<ErpReconciliationResponse | null>>;
  erpReconciliationBusy: boolean;
  handleErpReconciliation: () => Promise<void>;
  erpReconciliationError: string;
  erpReconciliationResult: ErpReconciliationResponse | null;
  promoActualsFile: File | null;
  setPromoActualsFile: Dispatch<SetStateAction<File | null>>;
  promoActualsMonth: string;
  setPromoActualsMonth: Dispatch<SetStateAction<string>>;
  promoActualsCutoff: string;
  setPromoActualsCutoff: Dispatch<SetStateAction<string>>;
  promoActualsUploading: boolean;
  handlePromoActualsUpload: () => Promise<void>;
  promoActualsMessage: string;
  availableYears: string[];
  selectedYears: string[];
  toggleYear: (year: string) => void;
  availableMonthNumbers: string[];
  selectedMonthNumbers: string[];
  toggleMonthNumber: (month: string) => void;
  selectedDays: number[];
  setSelectedDays: Dispatch<SetStateAction<number[]>>;
  toggleDay: (day: number) => void;
  exportMode: ExportMode;
  handleExportModeChange: (mode: ExportMode) => void;
  exportDataset: string;
  handleDatasetChange: (dataset: string) => void;
  catalog: SettingsCatalog | null;
  selectedDataset: SettingsDataset | null;
  exportMonths: string[];
  includeClosedStores: boolean;
  setIncludeClosedStores: Dispatch<SetStateAction<boolean>>;
  isIncentiveProductsExport: boolean;
  filterOptions: FilterOptions | null;
  exportFilters: ExportFilters;
  toggleFilter: (key: keyof ExportFilters, value: string) => void;
  exportDimensions: string[];
  setExportDimensions: Dispatch<SetStateAction<string[]>>;
  exportMetrics: string[];
  setExportMetrics: Dispatch<SetStateAction<string[]>>;
  monthlyMetrics: string[];
  setMonthlyMetrics: Dispatch<SetStateAction<string[]>>;
  dailyMetrics: string[];
  setDailyMetrics: Dispatch<SetStateAction<string[]>>;
  comparisonLevels: string[];
  setComparisonLevels: Dispatch<SetStateAction<string[]>>;
  exportStep: ExportStep;
  setExportStep: Dispatch<SetStateAction<ExportStep>>;
  exportBusy: boolean;
  handlePreviewExport: () => Promise<void>;
  handleDownloadExport: () => Promise<void>;
  exportMessage: string;
  preview: ExportPreview | null;
  setPreview: Dispatch<SetStateAction<ExportPreview | null>>;
}

function yesterdayInputValue(): string {
  return shiftIsoDate(formatIsoDateInput(), -1);
}

function SettingsView({
  theme,
  setTheme,
  canImportSales,
  canUseExports,
  section,
  setSection,
  file,
  setFile,
  salesReplaceConfirmed,
  setSalesReplaceConfirmed,
  setPendingSalesGeneration,
  salesCutoff,
  setSalesCutoff,
  uploading,
  handleUpload,
  message,
  messageType,
  pendingSalesGeneration,
  salesOverrideReason,
  setSalesOverrideReason,
  promotingSales,
  handleSalesPromotion,
  history,
  erpReconciliationMonths,
  erpReconciliationMonth,
  setErpReconciliationMonth,
  erpReconciliationFile,
  setErpReconciliationFile,
  setErpReconciliationError,
  setErpReconciliationResult,
  erpReconciliationBusy,
  handleErpReconciliation,
  erpReconciliationError,
  erpReconciliationResult,
  promoActualsFile,
  setPromoActualsFile,
  promoActualsMonth,
  setPromoActualsMonth,
  promoActualsCutoff,
  setPromoActualsCutoff,
  promoActualsUploading,
  handlePromoActualsUpload,
  promoActualsMessage,
  availableYears,
  selectedYears,
  toggleYear,
  availableMonthNumbers,
  selectedMonthNumbers,
  toggleMonthNumber,
  selectedDays,
  setSelectedDays,
  toggleDay,
  exportMode,
  handleExportModeChange,
  exportDataset,
  handleDatasetChange,
  catalog,
  selectedDataset,
  exportMonths,
  includeClosedStores,
  setIncludeClosedStores,
  isIncentiveProductsExport,
  filterOptions,
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
  handlePreviewExport,
  handleDownloadExport,
  exportMessage,
  preview,
  setPreview,
}: SettingsViewProps) {
  const toggleValue = (values: string[], value: string, minOne = false): string[] => {
    if (values.includes(value)) {
      if (minOne && values.length === 1) return values;
      return values.filter((item) => item !== value);
    }
    return [...values, value];
  };

  return (
    <div className="mx-auto max-w-6xl space-y-3 p-3 pb-24 pt-2 lg:max-w-none lg:space-y-4 lg:px-6 lg:py-3">
      <PageHeader className="lg:hidden" title="Setări" description="Administrare aplicație" />

      <SegmentedTabs<SettingsSection>
        ariaLabel="Secțiuni Setări"
        className="glass"
        options={[
          ...(canImportSales ? [{ value: 'imports' as const, label: 'Importuri' }] : []),
          ...(canUseExports ? [{ value: 'exports' as const, label: 'Exporturi' }] : []),
          { value: 'preferences' as const, label: 'Preferințe' },
        ]}
        value={section}
        onChange={setSection}
      />

      {section === 'preferences' ? (
        <div className="glass rounded-3xl p-4">
          <h3 className="mb-1 text-sm font-bold">Aspect aplicație</h3>
          <p className="mb-3 text-xs text-slate-500">Preferința se păstrează pe acest dispozitiv. Pe desktop, tema poate fi schimbată și din bara laterală.</p>
          <ThemeSwitcher theme={theme} setTheme={setTheme} />
          {!canImportSales && !canUseExports && (
            <p className="mt-3 text-xs text-slate-500">
              Importurile si exporturile server-side sunt disponibile doar rolurilor manageriale.
            </p>
          )}
        </div>
      ) : section === 'imports' ? (
        <>
          <div className="grid min-w-0 grid-cols-1 gap-3 xl:grid-cols-2">
          <div className="glass min-w-0 rounded-3xl p-4">
            <div className="mb-3 flex items-center gap-2">
              <Upload size={16} className="text-indigo-500" />
              <h3 className="text-sm font-bold">Import fișier vânzări</h3>
            </div>
            <label
              htmlFor="upload-sales-file"
              className={cn(
                'mb-3 flex cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed px-4 py-6 text-center transition-all',
                file
                  ? 'border-emerald-400 bg-emerald-50 dark:border-emerald-600 dark:bg-emerald-950/20'
                  : 'border-slate-300 bg-slate-50 hover:border-indigo-400 hover:bg-indigo-50/50 dark:border-slate-600 dark:bg-slate-800/60 dark:hover:border-indigo-500'
              )}
            >
              {file ? (
                <>
                  <FileSpreadsheet size={20} className="mb-1 text-emerald-500" />
                  <span className="text-xs font-semibold text-emerald-700 dark:text-emerald-300">
                    {file.name}
                  </span>
                  <span className="mt-0.5 text-[11px] text-slate-400">
                    {(file.size / 1024).toFixed(1)} KB · Click pentru a schimba
                  </span>
                </>
              ) : (
                <>
                  <Upload size={20} className="mb-1 text-slate-400" />
                  <span className="text-xs font-semibold text-slate-600 dark:text-slate-300">
                    Click sau drag & drop pentru a încărca
                  </span>
                  <span className="mt-0.5 text-[11px] text-slate-400">.xlsx, .xls</span>
                </>
              )}
              <input
                id="upload-sales-file"
                type="file"
                accept=".xlsx,.xls"
                onChange={(event) => {
                  setFile(event.target.files?.[0] ?? null);
                  setSalesReplaceConfirmed(false);
                  setPendingSalesGeneration(null);
                  setSalesOverrideReason('');
                }}
                className="hidden"
              />
            </label>
            {file && (
              <div className="mb-3 rounded-2xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-200">
                <div className="font-bold">Verificare înainte de import</div>
                <div className="mt-1">{file.name} · {(file.size / 1024 / 1024).toFixed(2)} MB · fișier Excel</div>
                <label className="mt-3 block font-semibold">
                  Cutoff declarat
                  <input
                    type="date"
                    value={salesCutoff}
                    onChange={(event) => setSalesCutoff(event.target.value)}
                    className="mt-1 w-full rounded-xl border border-amber-300 bg-white px-3 py-2 text-xs text-slate-800 dark:border-amber-800 dark:bg-slate-900 dark:text-slate-100"
                    required
                  />
                </label>
                <label className="mt-3 flex cursor-pointer items-start gap-2 font-semibold">
                  <input
                    type="checkbox"
                    checked={salesReplaceConfirmed}
                    onChange={(event) => setSalesReplaceConfirmed(event.target.checked)}
                    className="mt-0.5 h-4 w-4 rounded border-amber-300 text-indigo-600"
                  />
                  Confirm că fișierul și cutoff-ul sunt corecte. Validarea creează o generație staged; datele live se schimbă numai după promovarea explicită a manifestului.
                </label>
              </div>
            )}
            <button
              onClick={() => void handleUpload()}
              disabled={!file || !salesCutoff || !salesReplaceConfirmed || uploading}
              className="w-full rounded-2xl bg-indigo-600 px-4 py-3 text-xs font-bold text-white shadow-lg shadow-indigo-500/30 disabled:opacity-60"
            >
              {uploading ? 'Validare în desfășurare...' : 'Validează fișierul'}
            </button>
            {message && (
              <div className={`mt-3 rounded-2xl px-3 py-2 text-xs font-semibold ${
                messageType === 'error'
                  ? 'bg-rose-50 text-rose-700 dark:bg-rose-950/30 dark:text-rose-300'
                  : messageType === 'warning'
                    ? 'bg-amber-50 text-amber-800 dark:bg-amber-950/30 dark:text-amber-300'
                  : 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-300'
              }`}>
                {message}
              </div>
            )}
            {pendingSalesGeneration?.manifest && (
              <div className="mt-3 rounded-2xl border border-indigo-200 bg-indigo-50 p-3 text-xs text-slate-700 dark:border-indigo-900/70 dark:bg-indigo-950/30 dark:text-slate-200">
                <div className="font-bold text-indigo-800 dark:text-indigo-200">
                  Generație validată · datele live sunt neschimbate
                </div>
                <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1">
                  <dt className="text-slate-500">Lună / cutoff</dt>
                  <dd className="text-right font-semibold">{pendingSalesGeneration.import_month} / {pendingSalesGeneration.manifest.cutoff_date}</dd>
                  <dt className="text-slate-500">Rânduri / bonuri</dt>
                  <dd className="text-right font-semibold">{pendingSalesGeneration.rows_imported.toLocaleString('ro-RO')} / {(pendingSalesGeneration.manifest.receipt_count ?? 0).toLocaleString('ro-RO')}</dd>
                  <dt className="text-slate-500">Magazin-zile</dt>
                  <dd className="text-right font-semibold">{(pendingSalesGeneration.manifest.site_day_count ?? 0).toLocaleString('ro-RO')}</dd>
                  <dt className="text-slate-500">Valoare / cantitate</dt>
                  <dd className="text-right font-semibold">{Number(pendingSalesGeneration.manifest.total_value ?? 0).toLocaleString('ro-RO')} RON / {(pendingSalesGeneration.manifest.total_quantity ?? 0).toLocaleString('ro-RO')}</dd>
                  <dt className="text-slate-500">Hash business</dt>
                  <dd className="truncate text-right font-mono text-[10px]" title={pendingSalesGeneration.manifest.business_sha256 ?? undefined}>
                    {pendingSalesGeneration.manifest.business_sha256 ?? 'indisponibil'}
                  </dd>
                </dl>
                {pendingSalesGeneration.manifest.anomalies.length > 0 && (
                  <div className="mt-3 space-y-1">
                    {pendingSalesGeneration.manifest.anomalies.map((anomaly) => (
                      <div
                        key={`${anomaly.code}-${anomaly.message}`}
                        className={anomaly.blocking ? 'font-semibold text-rose-700 dark:text-rose-300' : 'text-amber-700 dark:text-amber-300'}
                      >
                        {anomaly.blocking ? 'Blocant' : 'Atenție'} · {anomaly.message}
                      </div>
                    ))}
                  </div>
                )}
                {pendingSalesGeneration.manifest.anomalies.some((item) => item.blocking) && (
                  <label className="mt-3 block font-semibold">
                    Motiv de override (minimum 10 caractere)
                    <textarea
                      value={salesOverrideReason}
                      onChange={(event) => setSalesOverrideReason(event.target.value)}
                      className="mt-1 min-h-20 w-full rounded-xl border border-rose-300 bg-white px-3 py-2 text-xs text-slate-800 dark:border-rose-800 dark:bg-slate-900 dark:text-slate-100"
                    />
                  </label>
                )}
                <button
                  onClick={() => void handleSalesPromotion()}
                  disabled={
                    promotingSales
                    || (pendingSalesGeneration.manifest.anomalies.some((item) => item.blocking) && salesOverrideReason.trim().length < 10)
                  }
                  className="mt-3 w-full rounded-xl bg-emerald-600 px-4 py-2.5 font-bold text-white disabled:opacity-60"
                >
                  {promotingSales ? 'Promovare în desfășurare...' : 'Promovează generația validată'}
                </button>
              </div>
            )}
          </div>

          <div className="glass min-w-0 rounded-3xl p-4">
            <div className="mb-1 flex items-center gap-2">
              <FileSpreadsheet size={16} className="text-sky-600" />
              <h3 className="text-sm font-bold">Verificare raport detaliat ERP</h3>
            </div>
            <p className="mb-3 text-xs text-slate-500">
              Reconciliere read-only cu luna Retail selectată și Focus, strict de la ziua 1 până la ultima zi din snapshotul Retail. Coloanele de zile din raport sunt ignorate; fișierul nu este păstrat pe server.
            </p>
            <div className="mb-3 grid gap-2 sm:grid-cols-[180px_1fr]">
              <label className="text-[11px] font-semibold text-slate-500">
                Luna verificată
                <select
                  value={erpReconciliationMonth}
                  onChange={(event) => {
                    setErpReconciliationMonth(event.target.value);
                    setErpReconciliationResult(null);
                  }}
                  className="mt-1 w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-800 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
                  disabled={erpReconciliationMonths.length === 0}
                >
                  {erpReconciliationMonths.length === 0 && (
                    <option value="">Niciun import Retail disponibil</option>
                  )}
                  {erpReconciliationMonths.map((month) => (
                    <option key={month} value={month}>
                      {formatMonthLabel(month, { month: 'long' })}
                    </option>
                  ))}
                </select>
              </label>
              <label
                htmlFor="upload-erp-reconciliation-file"
                className={cn(
                  'flex cursor-pointer items-center gap-3 self-end rounded-xl border border-dashed px-3 py-2 transition-colors',
                  erpReconciliationFile
                    ? 'border-sky-400 bg-sky-50 dark:border-sky-700 dark:bg-sky-950/20'
                    : 'border-slate-300 bg-slate-50 hover:border-sky-400 dark:border-slate-600 dark:bg-slate-800/60',
                )}
              >
                <Upload size={18} className={erpReconciliationFile ? 'text-sky-600' : 'text-slate-400'} />
                <span className="min-w-0 truncate text-xs font-semibold text-slate-600 dark:text-slate-300">
                  {erpReconciliationFile ? erpReconciliationFile.name : 'Selectează raportul ERP (.xls sau .xlsx)'}
                </span>
                <input
                  id="upload-erp-reconciliation-file"
                  type="file"
                  accept=".xlsx,.xls"
                  onChange={(event) => {
                    setErpReconciliationFile(event.target.files?.[0] ?? null);
                    setErpReconciliationResult(null);
                    setErpReconciliationError('');
                  }}
                  className="hidden"
                />
              </label>
            </div>
            <button
              type="button"
              onClick={() => void handleErpReconciliation()}
              disabled={!erpReconciliationFile || !erpReconciliationMonth || erpReconciliationBusy}
              className="w-full rounded-2xl bg-sky-600 px-4 py-3 text-xs font-bold text-white shadow-lg shadow-sky-500/25 disabled:opacity-60"
            >
              {erpReconciliationBusy ? 'Se validează și se compară...' : 'Verifică raportul fără import'}
            </button>
            {erpReconciliationError && (
              <div className="mt-3 rounded-2xl bg-rose-50 px-3 py-2 text-xs font-semibold text-rose-700 dark:bg-rose-950/30 dark:text-rose-300">
                {erpReconciliationError}
              </div>
            )}
            {erpReconciliationResult && (
              <ErpReconciliationResult result={erpReconciliationResult} />
            )}
          </div>

          <div className="glass rounded-3xl p-4">
            <div className="mb-3 flex items-center gap-2">
              <FileSpreadsheet size={16} className="text-emerald-600" />
              <h3 className="text-sm font-bold">Import tabel promo firmă</h3>
            </div>
            <div className="mb-3 grid gap-2 sm:grid-cols-2">
              <label className="text-[11px] font-semibold text-slate-500">
                Luna raportului
                <input
                  type="month"
                  value={promoActualsMonth}
                  onChange={(event) => setPromoActualsMonth(event.target.value)}
                  className="mt-1 w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-800 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
                />
              </label>
              <label className="text-[11px] font-semibold text-slate-500">
                Raport până la data
                <input
                  type="date"
                  value={promoActualsCutoff}
                  onChange={(event) => setPromoActualsCutoff(event.target.value)}
                  className="mt-1 w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-800 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
                />
              </label>
            </div>
            <label
              htmlFor="upload-promo-actuals-file"
              className={cn(
                'mb-3 flex cursor-pointer items-center gap-3 rounded-2xl border border-dashed px-3 py-3 transition-colors',
                promoActualsFile
                  ? 'border-emerald-400 bg-emerald-50 dark:border-emerald-700 dark:bg-emerald-950/20'
                  : 'border-slate-300 bg-slate-50 hover:border-emerald-400 dark:border-slate-600 dark:bg-slate-800/60',
              )}
            >
              <Upload size={18} className={promoActualsFile ? 'text-emerald-600' : 'text-slate-400'} />
              <span className="min-w-0 truncate text-xs font-semibold text-slate-600 dark:text-slate-300">
                {promoActualsFile ? promoActualsFile.name : 'Selectează raportul firmei (.xls sau .xlsx)'}
              </span>
              <input
                id="upload-promo-actuals-file"
                type="file"
                accept=".xlsx,.xls"
                onChange={(event) => setPromoActualsFile(event.target.files?.[0] ?? null)}
                className="hidden"
              />
            </label>
            <button
              type="button"
              onClick={() => void handlePromoActualsUpload()}
              disabled={!promoActualsFile || promoActualsUploading}
              className="w-full rounded-2xl bg-emerald-600 px-4 py-3 text-xs font-bold text-white shadow-lg shadow-emerald-500/25 disabled:opacity-60"
            >
              {promoActualsUploading ? 'Se validează și se aplică...' : 'Importă raport promo'}
            </button>
            {promoActualsMessage && (
              <div className="mt-3 rounded-2xl bg-emerald-50 px-3 py-2 text-xs font-semibold text-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-300">
                {promoActualsMessage}
              </div>
            )}
          </div>

          <div className="glass rounded-3xl p-4">
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-sm font-bold">Istoric importuri</h3>
              <span className="text-[11px] text-slate-500">{history.length} snapshot-uri</span>
            </div>
            <div className="max-h-40 space-y-2 overflow-y-auto">
              {history.slice(0, 8).map((entry) => (
                <div key={entry.id} className="rounded-2xl bg-slate-50 p-3 text-xs dark:bg-slate-800/60">
                  <div className="font-semibold">
                    {entry.import_month} · {entry.filename}
                  </div>
                  <div className="mt-1 text-slate-500">
                    {entry.rows_imported ?? 0} rânduri · {entry.status} ·{' '}
                    {entry.is_month_final ? '✓ Final' : 'Intermediar'} ·{' '}
                    {formatIsoDateTime(entry.created_at)}
                    {entry.duration_seconds != null && (
                      <> · {entry.duration_seconds < 60
                        ? `${entry.duration_seconds.toFixed(1)} s`
                        : `${(entry.duration_seconds / 60).toFixed(1)} min`}</>
                    )}
                  </div>
                  {entry.coverage_report?.active_store_coverage_pct != null && (
                    <div className="mt-1 text-slate-500">
                      Coverage magazine active {entry.coverage_report.active_store_coverage_pct}% ·{' '}
                      {entry.coverage_report.missing_active_store_count ?? 0} absente · 0 schimbări de stare
                    </div>
                  )}
                </div>
              ))}
              {history.length === 0 && (
                <div className="text-sm font-semibold text-slate-500">Nu există istoric încă.</div>
              )}
            </div>
          </div>
          </div>
        </>
      ) : (
        <div className="space-y-3">
          <ExportWorkflow step={exportStep} onChange={setExportStep} />
          <div className={cn('glass relative z-40 overflow-visible rounded-3xl p-4', exportStep === 4 && 'hidden')}>
            <div className="mb-3 flex items-center gap-2">
              <SlidersHorizontal size={16} className="text-indigo-500" />
              <h3 className="text-sm font-bold">Builder export Excel</h3>
            </div>

            <div className={cn('mb-4 grid gap-2 sm:grid-cols-2', exportStep !== 1 && 'hidden')}>
              <ModeButton
                active={exportMode === 'table'}
                icon={<Table2 size={16} />}
                title="Tabel detaliat"
                subtitle="Coloane si metrici selectate"
                onClick={() => handleExportModeChange('table')}
              />
              <ModeButton
                active={exportMode === 'daily_comparison'}
                icon={<LineChartIcon size={16} />}
                title="Evolutie zilnica"
                subtitle="Comparatie pe zile si niveluri"
                onClick={() => handleExportModeChange('daily_comparison')}
              />
            </div>

            <div className="grid gap-3 lg:grid-cols-4">
              <div className={cn(exportStep !== 1 && 'hidden')}>
              {exportMode === 'table' ? (
                <FieldBlock title="Dataset">
                  <select
                    value={exportDataset}
                    onChange={(event) => handleDatasetChange(event.target.value)}
                    className="w-full rounded-2xl border border-slate-200 bg-white px-3 py-2 text-xs font-semibold outline-none dark:border-slate-700 dark:bg-slate-900"
                  >
                    {catalog?.datasets.map((dataset) => (
                      <option key={dataset.key} value={dataset.key}>{dataset.label}</option>
                    ))}
                  </select>
                  {selectedDataset && (
                    <p className="mt-2 text-[11px] text-slate-500">{selectedDataset.description}</p>
                  )}
                </FieldBlock>
              ) : (
                <FieldBlock title="Analiza">
                  <div className="rounded-2xl border border-emerald-100 bg-emerald-50 px-3 py-2 text-xs font-semibold text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/30 dark:text-emerald-300">
                    Evolutie pe ziua lunii
                  </div>
                </FieldBlock>
              )}
              </div>

              <div className={cn('lg:col-span-2', exportStep !== 2 && 'hidden')}>
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
                      setPreview(null);
                    }}
                    onSelectFirstNineDays={() => {
                      setSelectedDays(ALL_DAYS.slice(0, 9));
                      setPreview(null);
                    }}
                    selectedMonthCount={exportMonths.length}
                  />
                </FieldBlock>
              </div>

              <div className={cn(exportStep !== 2 && 'hidden')}>
              <FieldBlock title="Optiuni">
                <div className="space-y-1 rounded-2xl border border-slate-200 bg-white p-2 dark:border-slate-700 dark:bg-slate-900">
                  {!isIncentiveProductsExport && (
                    <CheckRow
                      label="Include magazine inchise"
                      checked={includeClosedStores}
                      onChange={() => {
                        setIncludeClosedStores((value) => !value);
                        setPreview(null);
                      }}
                    />
                  )}
                  {exportMode === 'table' && !isIncentiveProductsExport && (
                    <CheckRow
                      label="Vanzare lunara pe perioada selectata"
                      checked={monthlyMetrics.includes('total_sales')}
                      onChange={() => {
                        setMonthlyMetrics((current) => toggleValue(current, 'total_sales'));
                        setPreview(null);
                      }}
                    />
                  )}
                </div>
              </FieldBlock>
              </div>
            </div>
          </div>

          <div className="relative z-0 grid gap-3 lg:grid-cols-2">
            <div className={cn('glass rounded-3xl p-4', exportStep !== 2 && 'hidden')}>
              <h3 className="mb-3 text-sm font-bold">Filtre</h3>
              <FilterBlock title="Firma" values={filterOptions?.firme ?? []} selected={exportFilters.firma} onToggle={(value) => toggleFilter('firma', value)} />
              <FilterBlock title="RM" values={filterOptions?.regionali ?? []} selected={exportFilters.regional} onToggle={(value) => toggleFilter('regional', value)} />
              <FilterBlock title="ASM" values={filterOptions?.asmi ?? []} selected={exportFilters.asm} onToggle={(value) => toggleFilter('asm', value)} />
              <FilterBlock title="Magazine" values={(filterOptions?.magazine ?? []).map((item) => ({ key: item.site_code, label: item.locatie }))} selected={exportFilters.site_code} onToggle={(value) => toggleFilter('site_code', value)} />
              <FilterBlock title="Agenti" values={(filterOptions?.agenti ?? []).map((item) => ({ key: `${item.agent}|${item.site_code}`, value: item.agent, label: `${item.agent} · ${item.locatie}` }))} selected={exportFilters.agent} onToggle={(value) => toggleFilter('agent', value)} />
            </div>

            <div className={cn('glass rounded-3xl p-4', exportStep !== 3 && 'hidden')}>
              <h3 className="mb-3 text-sm font-bold">
                {exportMode === 'table' ? 'Coloane' : 'Grafic si tabele'}
              </h3>
              {exportMode === 'table' ? (
                isIncentiveProductsExport ? (
                  <p className="rounded-2xl bg-amber-50 px-3 py-2 text-[11px] font-semibold text-amber-800 dark:bg-amber-950/30 dark:text-amber-200">
                    Coloane fixe: categorie, subcategorie, produs, vanzari, excluderi promo, unitati eligibile si plata. Vanzarile respecta zilele bifate; pragul de plata ramane lunar, ca in Focus.
                  </p>
                ) : (
                <>
                  <ColumnBlock
                    title="Identificare"
                    columns={selectedDataset?.dimensions ?? []}
                    selected={exportDimensions}
                    onToggle={(key) => {
                      setExportDimensions((current) => toggleValue(current, key, true));
                      setPreview(null);
                    }}
                  />
                  <ColumnBlock
                    title="Metrici total"
                    columns={catalog?.metrics ?? []}
                    selected={exportMetrics}
                    onToggle={(key) => {
                      setExportMetrics((current) => toggleValue(current, key, true));
                      setPreview(null);
                    }}
                  />
                  <ColumnBlock
                    title="Evolutie lunara"
                    columns={catalog?.monthly_metrics ?? []}
                    selected={monthlyMetrics}
                    onToggle={(key) => {
                      setMonthlyMetrics((current) => toggleValue(current, key));
                      setPreview(null);
                    }}
                  />
                  <ColumnBlock
                    title="Evolutie zilnica"
                    columns={catalog?.daily_metrics ?? []}
                    selected={dailyMetrics}
                    onToggle={(key) => {
                      setDailyMetrics((current) => toggleValue(current, key));
                      setPreview(null);
                    }}
                  />
                  {dailyMetrics.length > 0 && (
                    <p className="rounded-2xl bg-emerald-50 px-3 py-2 text-[11px] font-semibold text-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-300">
                      Exportul va include si sheet-ul „Evolutie zilnica”, aliniat pe ziua lunii, cu grafic automat pentru primul KPI selectat.
                    </p>
                  )}
                </>
                )
              ) : (
                <>
                  <ColumnBlock
                    title="Metrici zilnice"
                    columns={catalog?.daily_metrics ?? []}
                    selected={dailyMetrics.length > 0 ? dailyMetrics : DEFAULT_DAILY_COMPARISON_METRICS}
                    onToggle={(key) => {
                      setDailyMetrics((current) => toggleValue(
                        current.length > 0 ? current : DEFAULT_DAILY_COMPARISON_METRICS,
                        key,
                        true
                      ));
                      setPreview(null);
                    }}
                  />
                  <LevelBlock
                    levels={catalog?.comparison_levels ?? DEFAULT_COMPARISON_LEVELS.map((key) => ({ key, label: key }))}
                    selected={comparisonLevels}
                    onToggle={(key) => {
                      setComparisonLevels((current) => toggleValue(current, key, true));
                      setPreview(null);
                    }}
                  />
                </>
              )}
            </div>
          </div>

          <div className={cn('glass rounded-3xl p-4', exportStep !== 4 && 'hidden')}>
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <div>
                <h3 className="text-sm font-bold">Preview si export</h3>
                <p className="text-[11px] text-slate-500">
                  {preview
                    ? `${preview.total_rows} randuri${preview.truncated ? ' · preview limitat' : ''}`
                    : exportMode === 'daily_comparison' ? 'Preview pe nivelul General.' : 'Genereaza preview inainte de export.'}
                </p>
              </div>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => void handlePreviewExport()}
                  disabled={exportBusy || exportMonths.length === 0 || selectedDays.length === 0}
                  className="inline-flex items-center gap-2 rounded-2xl border border-slate-200 bg-white px-3 py-2 text-xs font-bold text-slate-600 shadow-sm disabled:opacity-60 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300"
                >
                  <Eye size={14} />
                  Preview
                </button>
                <button
                  type="button"
                  onClick={() => void handleDownloadExport()}
                  disabled={exportBusy || exportMonths.length === 0 || selectedDays.length === 0}
                  className="inline-flex items-center gap-2 rounded-2xl bg-indigo-600 px-3 py-2 text-xs font-bold text-white shadow-lg shadow-indigo-500/25 disabled:opacity-60"
                >
                  <Download size={14} />
                  Export Excel
                </button>
              </div>
            </div>
            {exportMessage && (
              <div className="mb-3 rounded-2xl bg-rose-50 px-3 py-2 text-xs font-semibold text-rose-700 dark:bg-rose-950/30 dark:text-rose-300">
                {exportMessage}
              </div>
            )}
            {preview && (
              <div className="overflow-auto rounded-2xl border border-slate-200 dark:border-slate-700">
                <table className="min-w-max border-collapse text-xs">
                  <thead className="bg-slate-50 dark:bg-slate-800">
                    <tr>
                      {preview.columns.map((column) => (
                        <TableHeaderCell key={column.key} className="whitespace-nowrap">{column.label}</TableHeaderCell>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {preview.rows.map((row, index) => (
                      <tr key={index} className={index % 2 === 0 ? 'bg-white dark:bg-slate-900/40' : 'bg-slate-50/60 dark:bg-slate-800/40'}>
                        {preview.columns.map((column) => (
                          <td key={column.key} className="whitespace-nowrap px-3 py-2">
                            {String(row[column.key] ?? '')}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
          <div className="export-mobile-actions sticky bottom-[calc(4.75rem+env(safe-area-inset-bottom))] z-30 flex items-center justify-between rounded-2xl border border-slate-200 bg-white/95 p-3 shadow-lg backdrop-blur-xl dark:border-slate-700 dark:bg-slate-900/95 lg:bottom-4 lg:static">
            <button
              type="button"
              onClick={() => setExportStep((Math.max(1, exportStep - 1)) as ExportStep)}
              disabled={exportStep === 1}
              className="rounded-xl border border-slate-200 px-4 py-2 text-xs font-bold text-slate-600 disabled:opacity-40 dark:border-slate-700 dark:text-slate-300"
            >
              Înapoi
            </button>
            <span className="text-xs font-semibold text-slate-500">Pasul {exportStep} din 4</span>
            <button
              type="button"
              onClick={() => setExportStep((Math.min(4, exportStep + 1)) as ExportStep)}
              disabled={exportStep === 4 || (exportStep === 2 && exportMonths.length === 0)}
              className="rounded-xl bg-indigo-600 px-4 py-2 text-xs font-bold text-white disabled:opacity-40"
            >
              Continuă
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export function Settings({
  theme,
  setTheme,
  onImportCompleted,
}: SettingsProps) {
  const { user } = useAuth();
  const canImportSales = canAdministerImports(user?.profile);
  const canUseExports = canExportReports(user?.profile);
  const [history, setHistory] = useState<ImportHistoryEntry[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [salesReplaceConfirmed, setSalesReplaceConfirmed] = useState(false);
  const [salesCutoff, setSalesCutoff] = useState(yesterdayInputValue);
  const [pendingSalesGeneration, setPendingSalesGeneration] = useState<ImportResponse | null>(null);
  const [salesOverrideReason, setSalesOverrideReason] = useState('');
  const [promotingSales, setPromotingSales] = useState(false);
  const [promoActualsFile, setPromoActualsFile] = useState<File | null>(null);
  const [promoActualsMonth, setPromoActualsMonth] = useState(getCurrentYearMonth);
  const [promoActualsCutoff, setPromoActualsCutoff] = useState(yesterdayInputValue);
  const [promoActualsUploading, setPromoActualsUploading] = useState(false);
  const [promoActualsMessage, setPromoActualsMessage] = useState('');
  const [erpReconciliationFile, setErpReconciliationFile] = useState<File | null>(null);
  const [erpReconciliationMonth, setErpReconciliationMonth] = useState('');
  const [erpReconciliationBusy, setErpReconciliationBusy] = useState(false);
  const [erpReconciliationError, setErpReconciliationError] = useState('');
  const [erpReconciliationResult, setErpReconciliationResult] = useState<ErpReconciliationResponse | null>(null);
  const [uploading, setUploading] = useState(false);
  const [message, setMessage] = useState('');
  const [messageType, setMessageType] = useState<'success' | 'warning' | 'error'>('success');
  const [section, setSection] = useState<SettingsSection>(
    canImportSales ? 'imports' : canUseExports ? 'exports' : 'preferences',
  );
  const [exportMode, setExportMode] = useState<ExportMode>('table');
  const [exportDataset, setExportDataset] = useState('agents');
  const [selectedYears, setSelectedYears] = useState<string[]>([]);
  const [selectedMonthNumbers, setSelectedMonthNumbers] = useState<string[]>([]);
  const [selectedDays, setSelectedDays] = useState<number[]>(ALL_DAYS);
  const [exportDimensions, setExportDimensions] = useState<string[]>([]);
  const [exportMetrics, setExportMetrics] = useState<string[]>(DEFAULT_EXPORT_METRICS);
  const [monthlyMetrics, setMonthlyMetrics] = useState<string[]>([]);
  const [dailyMetrics, setDailyMetrics] = useState<string[]>([]);
  const [comparisonLevels, setComparisonLevels] = useState<string[]>(DEFAULT_COMPARISON_LEVELS);
  const [exportFilters, setExportFilters] = useState<ExportFilters>(EMPTY_EXPORT_FILTERS);
  const [includeClosedStores, setIncludeClosedStores] = useState(false);
  const [preview, setPreview] = useState<ExportPreview | null>(null);
  const [exportMessage, setExportMessage] = useState('');
  const [exportBusy, setExportBusy] = useState(false);
  const [exportStep, setExportStep] = useState<ExportStep>(1);

  useEffect(() => {
    if (!canImportSales && section === 'imports') {
      setSection(canUseExports ? 'exports' : 'preferences');
    }
    if (!canUseExports && section === 'exports') {
      setSection(canImportSales ? 'imports' : 'preferences');
    }
  }, [canImportSales, canUseExports, section]);

  useEffect(() => {
    if (!canImportSales) return;
    const cached = getCachedView<{ history: ImportHistoryEntry[] }>(CACHE_KEY, SETTINGS_CACHE_TTL_MS);
    if (cached.value) {
      setHistory(cached.value.history);
    }

    getImportHistory()
      .then((historyData) => {
        setHistory(historyData);
        setCachedView(CACHE_KEY, { history: historyData });
      })
      .catch(() => {
        setHistory([]);
        setMessage('Nu am putut încărca istoricul importurilor.');
        setMessageType('error');
      });
  }, [canImportSales]);

  const erpReconciliationMonths = useMemo(
    () => Array.from(new Set(
      history
        .filter((entry) => entry.status === 'completed')
        .map((entry) => entry.import_month),
    )).sort((left, right) => right.localeCompare(left)),
    [history],
  );

  useEffect(() => {
    if (erpReconciliationMonths.length === 0) {
      setErpReconciliationMonth('');
      return;
    }
    setErpReconciliationMonth((current) => (
      erpReconciliationMonths.includes(current)
        ? current
        : erpReconciliationMonths[0] ?? ''
    ));
  }, [erpReconciliationMonths]);

  const canLoadExportData = section === 'exports' && canUseExports;
  const availableMonthsQuery = useAvailableMonths(Boolean(user) && canLoadExportData);
  const months = availableMonthsQuery.months;
  const catalogQuery = useQuery({
    queryKey: ['settings', 'export-catalog', canUseExports],
    enabled: canLoadExportData,
    queryFn: ({ signal }) => getExportCatalog(signal),
    staleTime: 5 * 60_000,
    retry: 1,
  });
  const catalog = catalogQuery.data ?? null;

  const selectedMonthForFilters = months
    .filter((month) => selectedYears.includes(month.slice(0, 4)) && selectedMonthNumbers.includes(month.slice(5, 7)))
    .sort()
    .at(0) ?? months[0] ?? '';
  const filterOptionsQuery = useQuery({
    queryKey: ['settings', 'filter-options', selectedMonthForFilters],
    enabled: canLoadExportData && Boolean(selectedMonthForFilters),
    queryFn: ({ signal }) => getFilterOptions(selectedMonthForFilters, signal),
    staleTime: 5 * 60_000,
    retry: 1,
  });
  const filterOptions: FilterOptions | null = filterOptionsQuery.data ?? null;

  useEffect(() => {
    if (!catalogQuery.data) return;
    const defaultDataset = catalogQuery.data.datasets.find((item) => item.key === exportDataset) ?? catalogQuery.data.datasets[0];
    if (!defaultDataset) return;
    setExportDataset((current) => catalogQuery.data?.datasets.some((item) => item.key === current) ? current : defaultDataset.key);
    setExportDimensions((current) => current.length > 0 ? current : defaultDataset.dimensions.map((item) => item.key));
  }, [catalogQuery.data, exportDataset]);

  useEffect(() => {
    const firstMonth = months[0];
    if (!firstMonth) return;
    setSelectedYears((current) => current.length > 0 ? current : [firstMonth.slice(0, 4)]);
    setSelectedMonthNumbers((current) => current.length > 0 ? current : [firstMonth.slice(5, 7)]);
  }, [months]);

  const selectedDataset = useMemo(
    () => catalog?.datasets.find((item) => item.key === exportDataset) ?? null,
    [catalog, exportDataset]
  );
  const isIncentiveProductsExport = exportMode === 'table' && exportDataset === INCENTIVE_PRODUCTS_DATASET;

  const availableYears = useMemo(
    () => Array.from(new Set(months.map((month) => month.slice(0, 4)))).sort((a, b) => Number(b) - Number(a)),
    [months],
  );

  const availableMonthNumbers = useMemo(
    () => Array.from(new Set(
      months
        .filter((month) => selectedYears.includes(month.slice(0, 4)))
        .map((month) => month.slice(5, 7)),
    )).sort(),
    [months, selectedYears],
  );

  useEffect(() => {
    if (availableMonthNumbers.length === 0) return;
    setSelectedMonthNumbers((current) => {
      const valid = current.filter((month) => availableMonthNumbers.includes(month));
      const firstMonthNumber = availableMonthNumbers[0];
      return valid.length > 0 ? valid : firstMonthNumber ? [firstMonthNumber] : [];
    });
  }, [availableMonthNumbers]);

  const exportMonths = useMemo(
    () => months.filter((month) => (
      selectedYears.includes(month.slice(0, 4))
      && selectedMonthNumbers.includes(month.slice(5, 7))
    )).sort(),
    [months, selectedMonthNumbers, selectedYears],
  );

  const exportRequest = useMemo<ExportRequest>(() => {
    const effectiveDailyMetrics = exportMode === 'daily_comparison'
      ? (dailyMetrics.length > 0 ? dailyMetrics : DEFAULT_DAILY_COMPARISON_METRICS)
      : dailyMetrics;
    return {
      export_mode: exportMode,
      dataset: exportDataset,
      months: exportMonths,
      dimensions: exportMode === 'table' ? exportDimensions : [],
      metrics: exportMode === 'table' ? exportMetrics : [],
      monthly_metrics: exportMode === 'table' ? monthlyMetrics : [],
      daily_metrics: effectiveDailyMetrics,
      comparison_levels: exportMode === 'daily_comparison' ? comparisonLevels : [],
      selected_days: selectedDays,
      filters: exportFilters,
      include_closed_stores: includeClosedStores,
      preview_limit: 100,
      filename: settingsPresenters.formatExportFilename(exportMode, exportDataset, exportMonths, selectedDays),
    };
  }, [
    comparisonLevels,
    dailyMetrics,
    exportDataset,
    exportDimensions,
    exportFilters,
    exportMetrics,
    exportMode,
    exportMonths,
    includeClosedStores,
    monthlyMetrics,
    selectedDays,
  ]);

  const handleUpload = async () => {
    if (!file || !salesReplaceConfirmed) return;
    let uploadAccepted = false;
    try {
      setUploading(true);
      setMessage('');
      setMessageType('success');
      const initialJob = await uploadSalesFile(file, salesCutoff);
      uploadAccepted = true;
      setMessage('Fișier încărcat. Importul rulează în worker.');
      const outcome = await pollImportJob(initialJob, {
        intervalMs: IMPORT_POLL_INTERVAL_MS,
        maxAttempts: IMPORT_POLL_LIMIT,
        maxConsecutiveErrors: IMPORT_POLL_MAX_CONSECUTIVE_ERRORS,
        getStatus: getImportJobStatus,
        onConnectionIssue: () => {
          setMessageType('warning');
          setMessage('Conexiune întreruptă temporar. Importul continuă în worker; reconectez automat.');
        },
        onConnectionRestored: () => {
          setMessageType('success');
          setMessage('Conexiune restabilită. Importul rulează în worker.');
        },
      });
      if (outcome.kind === 'unconfirmed') {
        setMessageType('warning');
        setMessage(
          'Fișierul a fost încărcat, dar statusul final nu poate fi confirmat momentan. '
          + 'Importul poate continua în worker; reîncarcă pagina și verifică istoricul înainte de a retrimite fișierul.',
        );
        return;
      }
      const job = outcome.job;
      if (job.error || !job.result) {
        if (job.error) throw new Error(job.error);
        setMessageType('warning');
        setMessage('Workerul a încheiat jobul, dar rezultatul nu poate fi confirmat. Verifică istoricul importurilor.');
        return;
      }
      const response = job.result;
      if (response.generation_state === 'validated') {
        if (!response.generation_token || !response.manifest_sha256 || !response.manifest) {
          throw new Error('Manifestul generației validate este incomplet.');
        }
        setPendingSalesGeneration(response);
        setSalesOverrideReason('');
        setMessageType('warning');
        setMessage(
          `Generația ${response.import_month} a fost validată; datele live nu s-au schimbat. `
          + 'Verifică manifestul și promovează explicit.',
        );
        setFile(null);
        setSalesReplaceConfirmed(false);
        return;
      }
      try {
        const historyData = await getImportHistory();
        setHistory(historyData);
        setCachedView(CACHE_KEY, { history: historyData });
      } catch {
        // Importul este deja confirmat de worker. Un refresh de istoric esuat
        // nu trebuie reclasificat drept esec al importului.
      }
      onImportCompleted(response.import_month);
      setErpReconciliationMonth(response.import_month);
      const parts = [
        `Import ${response.import_month}: ${response.rows_imported} rânduri importate`,
      ];
      if (response.rows_filtered > 0) {
        parts.push(`${response.rows_filtered} rânduri non-ASM filtrate`);
      }
      const coverage = response.coverage_report;
      if (coverage.active_store_coverage_pct != null) {
        parts.push(`coverage magazine active ${coverage.active_store_coverage_pct}%`);
      }
      if ((coverage.missing_active_store_count ?? 0) > 0) {
        parts.push(`${coverage.missing_active_store_count} magazine active absente, fără schimbare de stare`);
      }
      if (response.is_month_final) {
        parts.push('Luna a fost marcată ca FINALĂ');
      } else {
        parts.push('Import intermediar (lună în curs)');
      }
      setMessage(parts.join(' · '));
      setFile(null);
      setSalesReplaceConfirmed(false);
    } catch (error) {
      const isConfirmedRejection = uploadAccepted || (error instanceof ApiError && error.status < 500);
      if (!isConfirmedRejection) {
        setMessage(
          'Conexiunea s-a întrerupt înainte de confirmare. Fișierul poate fi deja în procesare; '
          + 'reîncarcă pagina și verifică istoricul înainte de a retrimite.',
        );
        setMessageType('warning');
        return;
      }
      const detail = error instanceof Error ? error.message : '';
      setMessage(
        detail && !detail.startsWith('API error')
          ? `Importul a eșuat: ${detail}`
          : 'Importul a eșuat. Verifică fișierul și încearcă din nou.',
      );
      setMessageType('error');
    } finally {
      setUploading(false);
    }
  };

  const handleSalesPromotion = async () => {
    const pending = pendingSalesGeneration;
    if (!pending?.generation_token || !pending.manifest_sha256 || !pending.manifest) return;
    const hasBlockingAnomaly = pending.manifest.anomalies.some((item) => item.blocking);
    if (hasBlockingAnomaly && salesOverrideReason.trim().length < 10) {
      setMessageType('error');
      setMessage('Anomaliile blocante necesită un motiv explicit de minimum 10 caractere.');
      return;
    }
    try {
      setPromotingSales(true);
      setMessageType('success');
      setMessage('Promovarea generației rulează în worker.');
      const initialJob = await promoteSalesGeneration(
        pending.snapshot_id,
        pending.generation_token,
        pending.manifest_sha256,
        hasBlockingAnomaly ? salesOverrideReason.trim() : undefined,
      );
      const outcome = await pollImportJob(initialJob, {
        intervalMs: IMPORT_POLL_INTERVAL_MS,
        maxAttempts: IMPORT_POLL_LIMIT,
        maxConsecutiveErrors: IMPORT_POLL_MAX_CONSECUTIVE_ERRORS,
        getStatus: getImportJobStatus,
      });
      if (outcome.kind === 'unconfirmed') {
        setMessageType('warning');
        setMessage('Promovarea nu poate fi confirmată momentan; verifică istoricul înainte de retry.');
        return;
      }
      const job = outcome.job;
      if (job.error || !job.result || job.result.generation_state !== 'promoted') {
        throw new Error(job.error || 'Promovarea nu are un rezultat terminal verificat.');
      }
      const response = job.result;
      try {
        const historyData = await getImportHistory();
        setHistory(historyData);
        setCachedView(CACHE_KEY, { history: historyData });
      } catch {
        // Promovarea este deja confirmată de worker.
      }
      onImportCompleted(response.import_month);
      setErpReconciliationMonth(response.import_month);
      setPendingSalesGeneration(null);
      setSalesOverrideReason('');
      setMessageType('success');
      setMessage(
        `Import ${response.import_month} promovat: ${response.rows_imported} rânduri · `
        + `hash business ${response.manifest?.business_sha256?.slice(0, 12) ?? 'indisponibil'}.`,
      );
    } catch (error) {
      setMessageType('error');
      setMessage(settingsPresenters.formatExportError(error, 'Promovarea generației de vânzări a eșuat.'));
    } finally {
      setPromotingSales(false);
    }
  };

  const handlePromoActualsUpload = async () => {
    if (!promoActualsFile) return;
    try {
      setPromoActualsUploading(true);
      setPromoActualsMessage('');
      const result = await uploadPromoActualsFile(
        promoActualsFile,
        promoActualsMonth,
        promoActualsCutoff,
      );
      setPromoActualsMessage(
        `Raport aplicat: ${result.promo_units.toLocaleString('ro-RO')} unități promo, `
        + `cutoff ${result.cutoff_date}, ${result.updated_promotions} promoții actualizate. `
        + `Generație ${result.generation_id.slice(0, 12)}.`,
      );
      setPromoActualsFile(null);
    } catch (error) {
      setPromoActualsMessage(settingsPresenters.formatExportError(error, 'Importul raportului promo a eșuat.'));
    } finally {
      setPromoActualsUploading(false);
    }
  };

  const handleErpReconciliation = async () => {
    if (!erpReconciliationFile) return;
    try {
      setErpReconciliationBusy(true);
      setErpReconciliationError('');
      setErpReconciliationResult(null);
      const result = await uploadErpReconciliationFile(
        erpReconciliationFile,
        erpReconciliationMonth,
      );
      setErpReconciliationResult(result);
    } catch (error) {
      setErpReconciliationError(
        settingsPresenters.formatExportError(error, 'Verificarea raportului ERP a eșuat.'),
      );
    } finally {
      setErpReconciliationBusy(false);
    }
  };

  const handleDatasetChange = (dataset: string) => {
    const nextDataset = catalog?.datasets.find((item) => item.key === dataset);
    setExportDataset(dataset);
    setPreview(null);
    if (nextDataset) {
      setExportDimensions(nextDataset.dimensions.map((item) => item.key));
    }
  };

  const handleExportModeChange = (mode: ExportMode) => {
    setExportMode(mode);
    setPreview(null);
    if (mode === 'daily_comparison') {
      setDailyMetrics((current) => current.length > 0 && current.length <= 4 ? current : DEFAULT_DAILY_COMPARISON_METRICS);
      setComparisonLevels((current) => current.length > 0 ? current : DEFAULT_COMPARISON_LEVELS);
    }
  };

  const toggleValue = (values: string[], value: string, minOne = false): string[] => {
    if (values.includes(value)) {
      if (minOne && values.length === 1) return values;
      return values.filter((item) => item !== value);
    }
    return [...values, value];
  };

  const toggleFilter = (key: keyof ExportFilters, value: string) => {
    setExportFilters((current) => ({
      ...current,
      [key]: toggleValue(current[key], value),
    }));
    setPreview(null);
  };

  const toggleYear = (year: string) => {
    setSelectedYears((current) => toggleValue(current, year, true).sort());
    setPreview(null);
  };

  const toggleMonthNumber = (month: string) => {
    setSelectedMonthNumbers((current) => toggleValue(current, month, true).sort());
    setPreview(null);
  };

  const toggleDay = (day: number) => {
    setSelectedDays((current) => toggleValue(
      current.map(String),
      String(day),
      true,
    ).map(Number).sort((left, right) => left - right));
    setPreview(null);
  };

  const handlePreviewExport = async () => {
    try {
      setExportBusy(true);
      setExportMessage('');
      const data = await previewExport(exportRequest);
      setPreview(data);
    } catch (error) {
      setExportMessage(settingsPresenters.formatExportError(error, 'Preview-ul nu a putut fi generat. Verifica selectia.'));
    } finally {
      setExportBusy(false);
    }
  };

  const handleDownloadExport = async () => {
    try {
      setExportBusy(true);
      setExportMessage('');
      const blob = await downloadExport(exportRequest);
      downloadBlob(blob, `${exportRequest.filename || 'export_retail'}.xlsx`);
    } catch (error) {
      setExportMessage(settingsPresenters.formatExportError(error, 'Exportul nu a putut fi generat. Verifica selectia.'));
    } finally {
      setExportBusy(false);
    }
  };

  return (
    <SettingsView
      theme={theme}
      setTheme={setTheme}
      canImportSales={canImportSales}
      canUseExports={canUseExports}
      section={section}
      setSection={setSection}
      file={file}
      setFile={setFile}
      salesReplaceConfirmed={salesReplaceConfirmed}
      setSalesReplaceConfirmed={setSalesReplaceConfirmed}
      setPendingSalesGeneration={setPendingSalesGeneration}
      salesCutoff={salesCutoff}
      setSalesCutoff={setSalesCutoff}
      uploading={uploading}
      handleUpload={handleUpload}
      message={message}
      messageType={messageType}
      pendingSalesGeneration={pendingSalesGeneration}
      salesOverrideReason={salesOverrideReason}
      setSalesOverrideReason={setSalesOverrideReason}
      promotingSales={promotingSales}
      handleSalesPromotion={handleSalesPromotion}
      history={history}
      erpReconciliationMonths={erpReconciliationMonths}
      erpReconciliationMonth={erpReconciliationMonth}
      setErpReconciliationMonth={setErpReconciliationMonth}
      erpReconciliationFile={erpReconciliationFile}
      setErpReconciliationFile={setErpReconciliationFile}
      setErpReconciliationError={setErpReconciliationError}
      setErpReconciliationResult={setErpReconciliationResult}
      erpReconciliationBusy={erpReconciliationBusy}
      handleErpReconciliation={handleErpReconciliation}
      erpReconciliationError={erpReconciliationError}
      erpReconciliationResult={erpReconciliationResult}
      promoActualsFile={promoActualsFile}
      setPromoActualsFile={setPromoActualsFile}
      promoActualsMonth={promoActualsMonth}
      setPromoActualsMonth={setPromoActualsMonth}
      promoActualsCutoff={promoActualsCutoff}
      setPromoActualsCutoff={setPromoActualsCutoff}
      promoActualsUploading={promoActualsUploading}
      handlePromoActualsUpload={handlePromoActualsUpload}
      promoActualsMessage={promoActualsMessage}
      availableYears={availableYears}
      selectedYears={selectedYears}
      toggleYear={toggleYear}
      availableMonthNumbers={availableMonthNumbers}
      selectedMonthNumbers={selectedMonthNumbers}
      toggleMonthNumber={toggleMonthNumber}
      selectedDays={selectedDays}
      setSelectedDays={setSelectedDays}
      toggleDay={toggleDay}
      exportMode={exportMode}
      handleExportModeChange={handleExportModeChange}
      exportDataset={exportDataset}
      handleDatasetChange={handleDatasetChange}
      catalog={catalog}
      selectedDataset={selectedDataset}
      exportMonths={exportMonths}
      includeClosedStores={includeClosedStores}
      setIncludeClosedStores={setIncludeClosedStores}
      isIncentiveProductsExport={isIncentiveProductsExport}
      filterOptions={filterOptions}
      exportFilters={exportFilters}
      toggleFilter={toggleFilter}
      exportDimensions={exportDimensions}
      setExportDimensions={setExportDimensions}
      exportMetrics={exportMetrics}
      setExportMetrics={setExportMetrics}
      monthlyMetrics={monthlyMetrics}
      setMonthlyMetrics={setMonthlyMetrics}
      dailyMetrics={dailyMetrics}
      setDailyMetrics={setDailyMetrics}
      comparisonLevels={comparisonLevels}
      setComparisonLevels={setComparisonLevels}
      exportStep={exportStep}
      setExportStep={setExportStep}
      exportBusy={exportBusy}
      handlePreviewExport={handlePreviewExport}
      handleDownloadExport={handleDownloadExport}
      exportMessage={exportMessage}
      preview={preview}
      setPreview={setPreview}
    />
  );
}
