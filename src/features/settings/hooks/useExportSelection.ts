import { useCallback, useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { getExportCatalog } from "../../../api/exports";
import type { ExportFilters, ExportPreview, ExportRequest } from "../../../api/exports";
import { getFilterOptions } from "../../../api/filters";
import { useAvailableMonths } from "../../../hooks/useAvailableMonths";
import { queryKeys } from "../../../lib/queryKeys";
import * as presenters from "../presenters";
import { ALL_DAYS, type ExportStep } from "../exports/controls";
import type { ExportMode } from "../types";

const EMPTY_FILTERS: ExportFilters = { firma: [], regional: [], asm: [], site_code: [], agent: [] };
const DEFAULT_METRICS = ["total_sales", "total_quantity", "total_receipts", "target", "target_progress_pct", "proc_bon2acc", "prc_focus_acc_qty", "daily_average"];
const DEFAULT_DAILY_METRICS = ["total_sales"];
const DEFAULT_COMPARISON_LEVELS = ["general", "asms", "stores", "agents"];
const toggleValue = (values: string[], value: string, minOne = false) =>
  values.includes(value) ? (minOne && values.length === 1 ? values : values.filter((item) => item !== value)) : [...values, value];

function useExportPeriodSelection(enabled: boolean, identityKey: string, resetPreview: () => void) {
  const months = useAvailableMonths(enabled, identityKey).months;
  const [selectedYears, setSelectedYears] = useState<string[]>([]);
  const [selectedMonthNumbers, setSelectedMonthNumbers] = useState<string[]>([]);
  const [selectedDays, setSelectedDays] = useState<number[]>(ALL_DAYS);
  useEffect(() => {
    const first = months[0];
    if (!first) return;
    setSelectedYears((current) => current.length > 0 ? current : [first.slice(0, 4)]);
    setSelectedMonthNumbers((current) => current.length > 0 ? current : [first.slice(5, 7)]);
  }, [months]);
  const availableYears = useMemo(
    () => Array.from(new Set(months.map((month) => month.slice(0, 4)))).sort((a, b) => Number(b) - Number(a)),
    [months],
  );
  const availableMonthNumbers = useMemo(
    () => Array.from(new Set(months.filter((month) => selectedYears.includes(month.slice(0, 4))).map((month) => month.slice(5, 7)))).sort(),
    [months, selectedYears],
  );
  useEffect(() => {
    const first = availableMonthNumbers[0];
    if (!first) return;
    setSelectedMonthNumbers((current) => {
      const valid = current.filter((month) => availableMonthNumbers.includes(month));
      return valid.length > 0 ? valid : [first];
    });
  }, [availableMonthNumbers]);
  const exportMonths = useMemo(
    () => months.filter((month) => selectedYears.includes(month.slice(0, 4)) && selectedMonthNumbers.includes(month.slice(5, 7))).sort(),
    [months, selectedMonthNumbers, selectedYears],
  );
  const toggleYear = (year: string) => { setSelectedYears((current) => toggleValue(current, year, true).sort()); resetPreview(); };
  const toggleMonthNumber = (month: string) => { setSelectedMonthNumbers((current) => toggleValue(current, month, true).sort()); resetPreview(); };
  const toggleDay = (day: number) => {
    setSelectedDays((current) => toggleValue(current.map(String), String(day), true).map(Number).sort((a, b) => a - b));
    resetPreview();
  };
  return {
    availableYears, selectedYears, toggleYear, availableMonthNumbers,
    selectedMonthNumbers, toggleMonthNumber, selectedDays, setSelectedDays,
    toggleDay, exportMonths,
  };
}

function useExportDataSelection(
  enabled: boolean,
  identityKey: string,
  authorized: boolean,
  selectedMonth: string,
  resetPreview: () => void,
) {
  const queryClient = useQueryClient();
  const [exportDataset, setExportDataset] = useState("agents");
  const [exportDimensions, setExportDimensions] = useState<string[]>([]);
  const [exportFilters, setExportFilters] = useState<ExportFilters>(EMPTY_FILTERS);
  const catalogQuery = useQuery({
    queryKey: queryKeys.settings.exportCatalog(identityKey), enabled,
    queryFn: ({ signal }) => getExportCatalog(signal), staleTime: 5 * 60_000, retry: 1,
  });
  const filterOptionsQuery = useQuery({
    queryKey: queryKeys.settings.exportFilters(identityKey, selectedMonth),
    enabled: enabled && Boolean(selectedMonth),
    queryFn: ({ signal }) => getFilterOptions(selectedMonth, signal),
    staleTime: 5 * 60_000, retry: 1,
  });
  const catalog = catalogQuery.data ?? null;
  useEffect(() => {
    if (!authorized) void queryClient.removeQueries({ queryKey: queryKeys.settings.identity(identityKey) });
  }, [authorized, identityKey, queryClient]);
  useEffect(() => {
    if (!catalogQuery.data) return;
    const next = catalogQuery.data.datasets.find((item) => item.key === exportDataset) ?? catalogQuery.data.datasets[0];
    if (!next) return;
    setExportDataset((current) => catalogQuery.data?.datasets.some((item) => item.key === current) ? current : next.key);
    setExportDimensions((current) => current.length > 0 ? current : next.dimensions.map((item) => item.key));
  }, [catalogQuery.data, exportDataset]);
  const selectedDataset = useMemo(
    () => catalog?.datasets.find((item) => item.key === exportDataset) ?? null,
    [catalog, exportDataset],
  );
  const handleDatasetChange = (dataset: string) => {
    const next = catalog?.datasets.find((item) => item.key === dataset);
    setExportDataset(dataset); resetPreview();
    if (next) setExportDimensions(next.dimensions.map((item) => item.key));
  };
  const toggleFilter = (key: keyof ExportFilters, value: string) => {
    setExportFilters((current) => ({ ...current, [key]: toggleValue(current[key], value) }));
    resetPreview();
  };
  return {
    catalog, filterOptions: filterOptionsQuery.data ?? null, exportDataset,
    handleDatasetChange, selectedDataset, exportFilters, toggleFilter,
    exportDimensions, setExportDimensions,
  };
}

function useExportMetricSelection() {
  const [exportMetrics, setExportMetrics] = useState<string[]>(DEFAULT_METRICS);
  const [monthlyMetrics, setMonthlyMetrics] = useState<string[]>([]);
  const [dailyMetrics, setDailyMetrics] = useState<string[]>([]);
  const [comparisonLevels, setComparisonLevels] = useState<string[]>(DEFAULT_COMPARISON_LEVELS);
  return {
    exportMetrics, setExportMetrics, monthlyMetrics, setMonthlyMetrics,
    dailyMetrics, setDailyMetrics, comparisonLevels, setComparisonLevels,
  };
}

export function useExportSelection(enabled: boolean, identityKey: string, authorized: boolean) {
  const [preview, setPreview] = useState<ExportPreview | null>(null);
  const [exportMode, setExportMode] = useState<ExportMode>("table");
  const [includeClosedStores, setIncludeClosedStores] = useState(false);
  const [exportStep, setExportStep] = useState<ExportStep>(1);
  const resetPreview = useCallback(() => setPreview(null), []);
  const period = useExportPeriodSelection(enabled, identityKey, resetPreview);
  const selectedMonth = period.exportMonths[0] ?? "";
  const data = useExportDataSelection(enabled, identityKey, authorized, selectedMonth, resetPreview);
  const metrics = useExportMetricSelection();
  const handleExportModeChange = (mode: ExportMode) => {
    setExportMode(mode); resetPreview();
    if (mode === "daily_comparison") {
      metrics.setDailyMetrics((current) => current.length > 0 && current.length <= 4 ? current : DEFAULT_DAILY_METRICS);
      metrics.setComparisonLevels((current) => current.length > 0 ? current : DEFAULT_COMPARISON_LEVELS);
    }
  };
  return {
    ...data, ...period, ...metrics, exportMode, handleExportModeChange,
    includeClosedStores, setIncludeClosedStores, exportStep, setExportStep,
    preview, setPreview, resetPreview,
  };
}

export function useExportRequest(selection: ReturnType<typeof useExportSelection>): ExportRequest {
  return useMemo(() => ({
    export_mode: selection.exportMode,
    dataset: selection.exportDataset,
    months: selection.exportMonths,
    dimensions: selection.exportMode === "table" ? selection.exportDimensions : [],
    metrics: selection.exportMode === "table" ? selection.exportMetrics : [],
    monthly_metrics: selection.exportMode === "table" ? selection.monthlyMetrics : [],
    daily_metrics: selection.exportMode === "daily_comparison" && selection.dailyMetrics.length === 0 ? DEFAULT_DAILY_METRICS : selection.dailyMetrics,
    comparison_levels: selection.exportMode === "daily_comparison" ? selection.comparisonLevels : [],
    selected_days: selection.selectedDays,
    filters: selection.exportFilters,
    include_closed_stores: selection.includeClosedStores,
    preview_limit: 100,
    filename: presenters.formatExportFilename(selection.exportMode, selection.exportDataset, selection.exportMonths, selection.selectedDays),
  }), [selection]);
}

