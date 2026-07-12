import { useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';

import { ThemeSwitcher } from './ThemeSwitcher';
import { Download, Eye, FileSpreadsheet, LineChart as LineChartIcon, SlidersHorizontal, Table2, Upload } from 'lucide-react';
import { downloadExport, getExportCatalog, previewExport } from '../api/exports';
import type { ExportCatalog, ExportColumnDef, ExportFilters, ExportPreview, ExportRequest } from '../api/exports';
import { getAvailableMonths, getFilterOptions } from '../api/filters';
import { getImportHistory, getImportJobStatus, uploadPromoActualsFile, uploadSalesFile } from '../api/imports';
import type { FilterOptions, ImportHistoryEntry } from '../api/types';
import { cn } from '../lib/utils';
import { getCachedView, setCachedView } from '../lib/viewCache';
import { downloadBlob } from '../lib/download';
import { useAuth } from '../auth/AuthContext';
import { canAdministerImports, canExportReports } from '../auth/permissions';

interface SettingsProps {
  theme: string;
  setTheme: (theme: string) => void;
  onImportCompleted: (month: string) => void;
}

const SETTINGS_CACHE_TTL_MS = 5 * 60 * 1000;
const IMPORT_POLL_INTERVAL_MS = 1500;
const IMPORT_POLL_LIMIT = 1200;
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
const MONTH_LABELS = [
  'Ianuarie',
  'Februarie',
  'Martie',
  'Aprilie',
  'Mai',
  'Iunie',
  'Iulie',
  'August',
  'Septembrie',
  'Octombrie',
  'Noiembrie',
  'Decembrie',
];
const ALL_DAYS = Array.from({ length: 31 }, (_, index) => index + 1);
type ExportMode = 'table' | 'daily_comparison';
type SettingsSection = 'imports' | 'exports' | 'preferences';
const INCENTIVE_PRODUCTS_DATASET = 'incentive_products';

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
  const [promoActualsFile, setPromoActualsFile] = useState<File | null>(null);
  const [promoActualsMonth, setPromoActualsMonth] = useState(() => new Date().toISOString().slice(0, 7));
  const [promoActualsCutoff, setPromoActualsCutoff] = useState(() => new Date().toISOString().slice(0, 10));
  const [promoActualsUploading, setPromoActualsUploading] = useState(false);
  const [promoActualsMessage, setPromoActualsMessage] = useState('');
  const [uploading, setUploading] = useState(false);
  const [message, setMessage] = useState('');
  const [messageType, setMessageType] = useState<'success' | 'error'>('success');
  const [section, setSection] = useState<SettingsSection>(
    canImportSales ? 'imports' : canUseExports ? 'exports' : 'preferences',
  );
  const [catalog, setCatalog] = useState<ExportCatalog | null>(null);
  const [months, setMonths] = useState<string[]>([]);
  const [filterOptions, setFilterOptions] = useState<FilterOptions | null>(null);
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
      if (cached.isFresh) {
        return;
      }
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

  useEffect(() => {
    if (section !== 'exports' || !canUseExports) return;
    let cancelled = false;
    Promise.all([getExportCatalog(), getAvailableMonths()])
      .then(async ([catalogData, monthData]) => {
        if (cancelled) return;
        setCatalog(catalogData);
        setMonths(monthData);
        if (monthData[0]) {
          setSelectedYears((current) => current.length > 0 ? current : [monthData[0].slice(0, 4)]);
          setSelectedMonthNumbers((current) => current.length > 0 ? current : [monthData[0].slice(5, 7)]);
        }
        const defaultDataset = catalogData.datasets.find((item) => item.key === exportDataset) ?? catalogData.datasets[0];
        if (defaultDataset) {
          setExportDataset(defaultDataset.key);
          setExportDimensions((current) => current.length > 0 ? current : defaultDataset.dimensions.map((item) => item.key));
        }
        if (monthData[0]) {
          const options = await getFilterOptions(monthData[0]);
          if (!cancelled) setFilterOptions(options);
        }
      })
      .catch(() => setExportMessage('Nu am putut incarca configuratia exporturilor.'));
    return () => {
      cancelled = true;
    };
  }, [section, canUseExports, exportDataset]);

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
      return valid.length > 0 ? valid : [availableMonthNumbers[0]];
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
      filename: formatExportFilename(exportMode, exportDataset, exportMonths, selectedDays),
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
    if (!file) return;
    try {
      setUploading(true);
      setMessage('');
      setMessageType('success');
      let job = await uploadSalesFile(file);
      setMessage('Fișier încărcat. Importul rulează în worker.');
      for (let attempt = 0; attempt < IMPORT_POLL_LIMIT; attempt += 1) {
        if (job.status === 'complete' || job.status === 'not_found') break;
        await new Promise((resolve) => window.setTimeout(resolve, IMPORT_POLL_INTERVAL_MS));
        job = await getImportJobStatus(job.job_id);
      }
      if (job.status !== 'complete') {
        throw new Error('Import job timeout');
      }
      if (job.error || !job.result) {
        throw new Error(job.error || 'Importul nu a returnat un rezultat');
      }
      const response = job.result;
      const historyData = await getImportHistory();
      setHistory(historyData);
      setCachedView(CACHE_KEY, { history: historyData });
      onImportCompleted(response.import_month);
      const parts = [
        `Import ${response.import_month}: ${response.rows_imported} rânduri importate`,
      ];
      if (response.rows_filtered > 0) {
        parts.push(`${response.rows_filtered} rânduri non-ASM filtrate`);
      }
      if (response.is_month_final) {
        parts.push('Luna a fost marcată ca FINALĂ');
      } else {
        parts.push('Import intermediar (lună în curs)');
      }
      setMessage(parts.join(' · '));
      setFile(null);
    } catch (error) {
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
        + `cutoff ${result.cutoff_date}, ${result.updated_promotions} promoții actualizate.`,
      );
      setPromoActualsFile(null);
    } catch (error) {
      setPromoActualsMessage(formatExportError(error, 'Importul raportului promo a eșuat.'));
    } finally {
      setPromoActualsUploading(false);
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
      setExportMessage(formatExportError(error, 'Preview-ul nu a putut fi generat. Verifica selectia.'));
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
      setExportMessage(formatExportError(error, 'Exportul nu a putut fi generat. Verifica selectia.'));
    } finally {
      setExportBusy(false);
    }
  };

  return (
    <div className="mx-auto max-w-6xl space-y-3 p-3 pb-24 pt-2">
      <div>
        <h1 className="text-xl font-bold tracking-tight">Setări</h1>
        <p className="text-xs text-slate-500 dark:text-slate-400">Administrare aplicație</p>
      </div>

      <div className="glass flex gap-1 rounded-2xl p-1">
        {[
          ...(canImportSales ? [{ key: 'imports', label: 'Importuri' }] : []),
          ...(canUseExports ? [{ key: 'exports', label: 'Exporturi' }] : []),
          { key: 'preferences', label: 'General' },
        ].map((item) => (
          <button
            key={item.key}
            type="button"
            onClick={() => setSection(item.key as SettingsSection)}
            className={`flex-1 rounded-xl px-3 py-2 text-xs font-bold transition-colors ${
              section === item.key
                ? 'bg-indigo-600 text-white shadow-sm'
                : 'text-slate-500 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800'
            }`}
          >
            {item.label}
          </button>
        ))}
      </div>

      {section === 'preferences' ? (
        <div className="glass rounded-3xl p-4">
          <h3 className="mb-3 text-sm font-bold">Temă</h3>
          <ThemeSwitcher theme={theme} setTheme={setTheme} />
          {!canImportSales && !canUseExports && (
            <p className="mt-3 text-xs text-slate-500">
              Importurile si exporturile server-side sunt disponibile doar rolurilor manageriale.
            </p>
          )}
        </div>
      ) : section === 'imports' ? (
        <>
          <div className="glass rounded-3xl p-4 lg:hidden">
            <h3 className="mb-3 text-sm font-bold">Temă</h3>
            <ThemeSwitcher theme={theme} setTheme={setTheme} />
          </div>

          <div className="glass rounded-3xl p-4">
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
                onChange={(event) => setFile(event.target.files?.[0] ?? null)}
                className="hidden"
              />
            </label>
            <button
              onClick={() => void handleUpload()}
              disabled={!file || uploading}
              className="w-full rounded-2xl bg-indigo-600 px-4 py-3 text-xs font-bold text-white shadow-lg shadow-indigo-500/30 disabled:opacity-60"
            >
              {uploading ? 'Import în desfășurare...' : 'Importă fișier'}
            </button>
            {message && (
              <div className={`mt-3 rounded-2xl px-3 py-2 text-xs font-semibold ${
                messageType === 'error'
                  ? 'bg-rose-50 text-rose-700 dark:bg-rose-950/30 dark:text-rose-300'
                  : 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-300'
              }`}>
                {message}
              </div>
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
                    {entry.created_at.slice(0, 16).replace('T', ' ')}
                  </div>
                </div>
              ))}
              {history.length === 0 && (
                <div className="text-sm font-semibold text-slate-500">Nu există istoric încă.</div>
              )}
            </div>
          </div>
        </>
      ) : (
        <div className="space-y-3">
          <div className="glass relative z-40 overflow-visible rounded-3xl p-4">
            <div className="mb-3 flex items-center gap-2">
              <SlidersHorizontal size={16} className="text-indigo-500" />
              <h3 className="text-sm font-bold">Builder export Excel</h3>
            </div>

            <div className="mb-4 grid gap-2 sm:grid-cols-2">
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

              <div className="lg:col-span-2">
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

          <div className="relative z-0 grid gap-3 lg:grid-cols-2">
            <div className="glass rounded-3xl p-4">
              <h3 className="mb-3 text-sm font-bold">Filtre</h3>
              <FilterBlock title="Firma" values={filterOptions?.firme ?? []} selected={exportFilters.firma} onToggle={(value) => toggleFilter('firma', value)} />
              <FilterBlock title="RM" values={filterOptions?.regionali ?? []} selected={exportFilters.regional} onToggle={(value) => toggleFilter('regional', value)} />
              <FilterBlock title="ASM" values={filterOptions?.asmi ?? []} selected={exportFilters.asm} onToggle={(value) => toggleFilter('asm', value)} />
              <FilterBlock title="Magazine" values={(filterOptions?.magazine ?? []).map((item) => ({ key: item.site_code, label: item.locatie }))} selected={exportFilters.site_code} onToggle={(value) => toggleFilter('site_code', value)} />
              <FilterBlock title="Agenti" values={(filterOptions?.agenti ?? []).map((item) => ({ key: `${item.agent}|${item.site_code}`, value: item.agent, label: `${item.agent} · ${item.locatie}` }))} selected={exportFilters.agent} onToggle={(value) => toggleFilter('agent', value)} />
            </div>

            <div className="glass rounded-3xl p-4">
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

          <div className="glass rounded-3xl p-4">
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
                        <th key={column.key} className="whitespace-nowrap px-3 py-2 text-left text-[10px] font-bold uppercase text-slate-500">
                          {column.label}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {preview.rows.map((row, index) => (
                      <tr key={index} className={index % 2 === 0 ? 'bg-white dark:bg-slate-900/40' : 'bg-slate-50/60 dark:bg-slate-800/40'}>
                        {preview.columns.map((column) => (
                          <td key={column.key} className="whitespace-nowrap px-3 py-2">
                            {row[column.key] ?? ''}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function PeriodSelector({
  years,
  selectedYears,
  onYearToggle,
  monthNumbers,
  selectedMonthNumbers,
  onMonthToggle,
  selectedDays,
  onDayToggle,
  onSelectAllDays,
  onSelectFirstNineDays,
  selectedMonthCount,
}: {
  years: string[];
  selectedYears: string[];
  onYearToggle: (year: string) => void;
  monthNumbers: string[];
  selectedMonthNumbers: string[];
  onMonthToggle: (month: string) => void;
  selectedDays: number[];
  onDayToggle: (day: number) => void;
  onSelectAllDays: () => void;
  onSelectFirstNineDays: () => void;
  selectedMonthCount: number;
}) {
  return (
    <div className="space-y-2 rounded-2xl border border-slate-200 bg-white p-2 dark:border-slate-700 dark:bg-slate-900">
      <div className="grid gap-2 sm:grid-cols-3">
        <PeriodDropdown label="Ani" summary={selectedYears.join(', ')}>
          {years.map((year) => (
            <CheckRow key={year} label={year} checked={selectedYears.includes(year)} onChange={() => onYearToggle(year)} />
          ))}
        </PeriodDropdown>
        <PeriodDropdown
          label="Luni"
          summary={selectedMonthNumbers.length <= 2
            ? selectedMonthNumbers.map((month) => MONTH_LABELS[Number(month) - 1] ?? month).join(', ')
            : `${selectedMonthNumbers.length} selectate`}
        >
          {monthNumbers.map((month) => (
            <CheckRow
              key={month}
              label={MONTH_LABELS[Number(month) - 1] ?? month}
              checked={selectedMonthNumbers.includes(month)}
              onChange={() => onMonthToggle(month)}
            />
          ))}
        </PeriodDropdown>
        <PeriodDropdown label="Zile" summary={selectedDays.length === 31 ? 'Toata luna' : `${selectedDays.length} selectate`}>
          <div className="mb-2 flex gap-1">
            <button type="button" onClick={onSelectAllDays} className="rounded-lg border border-slate-200 px-2 py-1 text-[10px] font-bold dark:border-slate-700">
              Toate
            </button>
            <button type="button" onClick={onSelectFirstNineDays} className="rounded-lg border border-slate-200 px-2 py-1 text-[10px] font-bold dark:border-slate-700">
              Primele 9
            </button>
          </div>
          <div className="grid grid-cols-4 gap-1">
            {ALL_DAYS.map((day) => (
              <CheckRow key={day} label={String(day)} checked={selectedDays.includes(day)} onChange={() => onDayToggle(day)} />
            ))}
          </div>
        </PeriodDropdown>
      </div>
      <div className="text-[11px] font-semibold text-slate-500">
        {selectedMonthCount} luni rezultate · {selectedDays.length === 31 ? 'toate zilele' : `zilele ${selectedDays.join(', ')}`}
      </div>
    </div>
  );
}

function PeriodDropdown({ label, summary, children }: { label: string; summary: string; children: ReactNode }) {
  return (
    <details className="relative open:z-50 rounded-xl border border-slate-200 bg-slate-50 dark:border-slate-700 dark:bg-slate-800">
      <summary className="cursor-pointer list-none px-2 py-2 text-xs font-bold text-slate-600 dark:text-slate-200">
        <span className="block text-[10px] uppercase text-slate-400">{label}</span>
        <span>{summary}</span>
      </summary>
      <div className="absolute left-0 z-[60] mt-1 max-h-72 min-w-full overflow-auto rounded-xl border border-slate-200 bg-white p-2 shadow-xl dark:border-slate-700 dark:bg-slate-900">
        {children}
      </div>
    </details>
  );
}

function formatExportFilename(mode: ExportMode, dataset: string, months: string[], days: number[]): string {
  const sortedMonths = [...months].sort();
  const suffix = sortedMonths.length <= 4
    ? sortedMonths.join('_')
    : `${sortedMonths[0]}_${sortedMonths[sortedMonths.length - 1]}_${sortedMonths.length}luni`;
  const daySuffix = days.length === 31
    ? ''
    : `_zile_${days.length <= 10 ? days.join('-') : `${days.length}selectate`}`;
  return mode === 'daily_comparison'
    ? `export_retail_evolutie_zilnica_${suffix}${daySuffix}`
    : `export_retail_${dataset}_${suffix}${daySuffix}`;
}

function formatExportError(error: unknown, fallback: string): string {
  if (!(error instanceof Error)) return fallback;
  const detail = error.message.replace(/^API error: \d+\s*-?\s*/i, '').trim();
  return detail || fallback;
}

function ModeButton({
  active,
  icon,
  title,
  subtitle,
  onClick,
}: {
  active: boolean;
  icon: ReactNode;
  title: string;
  subtitle: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'flex items-center gap-3 rounded-2xl border px-3 py-3 text-left transition-colors',
        active
          ? 'border-indigo-500 bg-indigo-50 text-indigo-700 dark:border-indigo-400 dark:bg-indigo-950/30 dark:text-indigo-200'
          : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800'
      )}
    >
      <span className={cn(
        'grid h-8 w-8 place-items-center rounded-xl',
        active ? 'bg-indigo-600 text-white' : 'bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-300'
      )}>
        {icon}
      </span>
      <span className="min-w-0">
        <span className="block text-xs font-bold">{title}</span>
        <span className="block truncate text-[11px] opacity-75">{subtitle}</span>
      </span>
    </button>
  );
}

function FieldBlock({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div>
      <div className="mb-1.5 text-[11px] font-bold uppercase tracking-wide text-slate-400">{title}</div>
      {children}
    </div>
  );
}

function CheckRow({ label, checked, onChange }: { label: string; checked: boolean; onChange: () => void }) {
  return (
    <label className="flex cursor-pointer items-center gap-2 rounded-xl px-2 py-1.5 text-xs font-semibold text-slate-600 hover:bg-slate-50 dark:text-slate-300 dark:hover:bg-slate-800">
      <input
        type="checkbox"
        checked={checked}
        onChange={onChange}
        className="h-3.5 w-3.5 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
      />
      <span className="truncate">{label}</span>
    </label>
  );
}

function ColumnBlock({
  title,
  columns,
  selected,
  onToggle,
}: {
  title: string;
  columns: ExportColumnDef[];
  selected: string[];
  onToggle: (key: string) => void;
}) {
  return (
    <details className="mb-2 rounded-2xl border border-slate-200 bg-white p-2 dark:border-slate-700 dark:bg-slate-900">
      <summary className="cursor-pointer text-xs font-bold text-slate-600 dark:text-slate-300">
        {title} · {selected.filter((key) => columns.some((column) => column.key === key)).length}
      </summary>
      <div className="mt-2 grid gap-1 sm:grid-cols-2">
        {columns.map((column) => (
          <CheckRow
            key={column.key}
            label={column.label}
            checked={selected.includes(column.key)}
            onChange={() => onToggle(column.key)}
          />
        ))}
      </div>
    </details>
  );
}

function LevelBlock({
  levels,
  selected,
  onToggle,
}: {
  levels: Array<{ key: string; label: string }>;
  selected: string[];
  onToggle: (key: string) => void;
}) {
  return (
    <details open className="mb-2 rounded-2xl border border-slate-200 bg-white p-2 dark:border-slate-700 dark:bg-slate-900">
      <summary className="cursor-pointer text-xs font-bold text-slate-600 dark:text-slate-300">
        Niveluri exportate · {selected.length}
      </summary>
      <div className="mt-2 grid gap-1 sm:grid-cols-2">
        {levels.map((level) => (
          <CheckRow
            key={level.key}
            label={level.label}
            checked={selected.includes(level.key)}
            onChange={() => onToggle(level.key)}
          />
        ))}
      </div>
    </details>
  );
}

function FilterBlock({
  title,
  values,
  selected,
  onToggle,
}: {
  title: string;
  values: Array<string | { key: string; value?: string; label: string }>;
  selected: string[];
  onToggle: (value: string) => void;
}) {
  const [query, setQuery] = useState('');
  const normalized = query.trim().toLowerCase();
  const items = values
    .map((item) => typeof item === 'string' ? { key: item, value: item, label: item } : { ...item, value: item.value ?? item.key })
    .filter((item) => !normalized || item.label.toLowerCase().includes(normalized))
    .slice(0, 80);

  return (
    <details className="mb-2 rounded-2xl border border-slate-200 bg-white p-2 dark:border-slate-700 dark:bg-slate-900">
      <summary className="cursor-pointer text-xs font-bold text-slate-600 dark:text-slate-300">
        {title} · {selected.length}
      </summary>
      <input
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        placeholder="Cauta..."
        className="mt-2 w-full rounded-xl border border-slate-200 bg-slate-50 px-2 py-1.5 text-xs outline-none dark:border-slate-700 dark:bg-slate-800"
      />
      <div className="mt-2 max-h-44 overflow-auto">
        {items.map((item) => (
          <CheckRow
            key={item.key}
            label={item.label}
            checked={selected.includes(item.value)}
            onChange={() => onToggle(item.value)}
          />
        ))}
      </div>
    </details>
  );
}
