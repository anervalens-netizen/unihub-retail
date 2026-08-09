import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import {
  cancelExportOperation,
  createExportOperation,
  downloadExport,
  downloadExportOperation,
  getResumableExportOperation,
  getExportCatalog,
  getExportOperation,
  previewExport,
  uncertainExportOperationId,
} from "../../../api/exports";
import type {
  ExportFilters,
  ExportOperation,
  ExportPreview,
  ExportRequest,
} from "../../../api/exports";
import { getFilterOptions } from "../../../api/filters";
import { downloadBlob } from "../../../lib/download";
import { pollExportOperation } from "../../../lib/exportOperationPolling";
import { queryKeys } from "../../../lib/queryKeys";
import { useAvailableMonths } from "../../../hooks/useAvailableMonths";
import * as presenters from "../presenters";
import { ALL_DAYS, type ExportStep } from "../exports/controls";
import type { ExportMode, ExportsModel } from "../types";

const EMPTY_FILTERS: ExportFilters = {
  firma: [],
  regional: [],
  asm: [],
  site_code: [],
  agent: [],
};
const DEFAULT_METRICS = [
  "total_sales",
  "total_quantity",
  "total_receipts",
  "target",
  "target_progress_pct",
  "proc_bon2acc",
  "prc_focus_acc_qty",
  "daily_average",
];
const DEFAULT_DAILY_METRICS = ["total_sales"];
const DEFAULT_COMPARISON_LEVELS = ["general", "asms", "stores", "agents"];
const INCENTIVE_PRODUCTS_DATASET = "incentive_products";
const EXPORT_POLL_OPTIONS = {
  intervalMs: 1_500,
  maxAttempts: 1_200,
  maxConsecutiveErrors: 20,
};

const exportOperationStorageKey = (identityKey: string) =>
  `unihub:settings:export-operation:${identityKey}`;

const readStoredExportOperationId = (identityKey: string): number | null => {
  if (typeof window === "undefined") return null;
  const value = Number(window.sessionStorage.getItem(exportOperationStorageKey(identityKey)));
  return Number.isInteger(value) && value > 0 ? value : null;
};

const storeExportOperationId = (identityKey: string, operationId: number) => {
  if (typeof window !== "undefined") {
    window.sessionStorage.setItem(exportOperationStorageKey(identityKey), String(operationId));
  }
};

const clearStoredExportOperationId = (identityKey: string) => {
  if (typeof window !== "undefined") {
    window.sessionStorage.removeItem(exportOperationStorageKey(identityKey));
  }
};

const toggleValue = (values: string[], value: string, minOne = false) =>
  values.includes(value)
    ? minOne && values.length === 1
      ? values
      : values.filter((item) => item !== value)
    : [...values, value];

export function useSettingsExports(
  enabled: boolean,
  identityKey = "anonymous",
  authorized = enabled,
): ExportsModel {
  const queryClient = useQueryClient();
  const [exportMode, setExportMode] = useState<ExportMode>("table");
  const [exportDataset, setExportDataset] = useState("agents");
  const [selectedYears, setSelectedYears] = useState<string[]>([]);
  const [selectedMonthNumbers, setSelectedMonthNumbers] = useState<string[]>(
    [],
  );
  const [selectedDays, setSelectedDays] = useState<number[]>(ALL_DAYS);
  const [exportDimensions, setExportDimensions] = useState<string[]>([]);
  const [exportMetrics, setExportMetrics] = useState<string[]>(DEFAULT_METRICS);
  const [monthlyMetrics, setMonthlyMetrics] = useState<string[]>([]);
  const [dailyMetrics, setDailyMetrics] = useState<string[]>([]);
  const [comparisonLevels, setComparisonLevels] = useState<string[]>(
    DEFAULT_COMPARISON_LEVELS,
  );
  const [exportFilters, setExportFilters] =
    useState<ExportFilters>(EMPTY_FILTERS);
  const [includeClosedStores, setIncludeClosedStores] = useState(false);
  const [preview, setPreview] = useState<ExportPreview | null>(null);
  const [exportMessage, setExportMessage] = useState("");
  const [exportOperation, setExportOperation] =
    useState<ExportOperation | null>(null);
  const [exportBusy, setExportBusy] = useState(false);
  const [exportCancelling, setExportCancelling] = useState(false);
  const [exportStep, setExportStep] = useState<ExportStep>(1);
  const exportPollController = useRef<AbortController | null>(null);
  const availableMonths = useAvailableMonths(enabled, identityKey);
  const months = availableMonths.months;
  const catalogQuery = useQuery({
    queryKey: queryKeys.settings.exportCatalog(identityKey),
    enabled,
    queryFn: ({ signal }) => getExportCatalog(signal),
    staleTime: 5 * 60_000,
    retry: 1,
  });
  const catalog = catalogQuery.data ?? null;
  const selectedMonthForFilters =
    months
      .filter(
        (month) =>
          selectedYears.includes(month.slice(0, 4)) &&
          selectedMonthNumbers.includes(month.slice(5, 7)),
      )
      .sort()
      .at(0) ??
    months[0] ??
    "";
  const filterOptionsQuery = useQuery({
    queryKey: queryKeys.settings.exportFilters(identityKey, selectedMonthForFilters),
    enabled: enabled && Boolean(selectedMonthForFilters),
    queryFn: ({ signal }) => getFilterOptions(selectedMonthForFilters, signal),
    staleTime: 5 * 60_000,
    retry: 1,
  });
  const filterOptions = filterOptionsQuery.data ?? null;

  useEffect(() => {
    if (authorized) return;
    void queryClient.removeQueries({ queryKey: queryKeys.settings.identity(identityKey) });
  }, [authorized, identityKey, queryClient]);

  useEffect(() => {
    if (!catalogQuery.data) return;
    const defaultDataset =
      catalogQuery.data.datasets.find((item) => item.key === exportDataset) ??
      catalogQuery.data.datasets[0];
    if (!defaultDataset) return;
    setExportDataset((current) =>
      catalogQuery.data?.datasets.some((item) => item.key === current)
        ? current
        : defaultDataset.key,
    );
    setExportDimensions((current) =>
      current.length > 0
        ? current
        : defaultDataset.dimensions.map((item) => item.key),
    );
  }, [catalogQuery.data, exportDataset]);

  const followExportOperation = useCallback(
    async (initial: ExportOperation, controller: AbortController) => {
      setExportOperation(initial);
      const outcome = await pollExportOperation(
        initial,
        async (operationId, signal) =>
          queryClient.fetchQuery({
            queryKey: queryKeys.settings.exportOperation(identityKey, operationId),
            queryFn: () => getExportOperation(operationId, signal),
            staleTime: 0,
          }),
        {
          ...EXPORT_POLL_OPTIONS,
          signal: controller.signal,
          onUpdate: setExportOperation,
        },
      );
      if (outcome.kind === "aborted") return;
      setExportOperation(outcome.operation);
      if (outcome.kind === "unconfirmed") {
        setExportMessage(
          `Exportul #${initial.id} continuă în worker, dar statusul nu poate fi confirmat. Nu retrimite cererea.`,
        );
        return;
      }
      if (
        outcome.operation.status !== "completed" ||
        !outcome.operation.can_download
      ) {
        clearStoredExportOperationId(identityKey);
        throw new Error(
          `Exportul #${initial.id} s-a încheiat cu status ${outcome.operation.status}.`,
        );
      }
      downloadBlob(
        await downloadExportOperation(initial.id, controller.signal),
        outcome.operation.filename || "export_retail.xlsx",
      );
      clearStoredExportOperationId(identityKey);
      void queryClient.removeQueries({
        queryKey: queryKeys.settings.exportOperation(identityKey, initial.id),
        exact: true,
      });
    },
    [identityKey, queryClient],
  );

  useEffect(() => {
    if (!enabled || !authorized) return;
    const controller = new AbortController();
    exportPollController.current = controller;
    setExportBusy(true);
    void (async () => {
      try {
        const storedOperationId = readStoredExportOperationId(identityKey);
        let resumable: ExportOperation | null = null;
        if (storedOperationId !== null) {
          try {
            const storedOperation = await queryClient.fetchQuery({
              queryKey: queryKeys.settings.exportOperation(identityKey, storedOperationId),
              queryFn: () => getExportOperation(storedOperationId, controller.signal),
              staleTime: 0,
            });
            resumable = storedOperation;
            if (
              storedOperation.status === "failed" ||
              storedOperation.status === "cancelled" ||
              storedOperation.status === "expired"
            ) {
              clearStoredExportOperationId(identityKey);
              setExportOperation(storedOperation);
              return;
            }
          } catch (error) {
            if (!controller.signal.aborted) {
              setExportMessage(
                presenters.formatExportError(
                  error,
                  `Statusul exportului #${storedOperationId} nu poate fi confirmat. ID-ul a fost păstrat pentru retry.`,
                ),
              );
            }
            return;
          }
        } else {
          resumable = await queryClient.fetchQuery({
            queryKey: queryKeys.settings.exportResumable(identityKey),
            queryFn: () => getResumableExportOperation(controller.signal),
            staleTime: 0,
          });
          if (resumable) {
            storeExportOperationId(identityKey, resumable.id);
          }
        }
        if (resumable && !controller.signal.aborted) {
          await followExportOperation(resumable, controller);
        }
      } catch (error) {
        if (!controller.signal.aborted) {
          setExportMessage(
            presenters.formatExportError(
              error,
              "Statusul exportului activ nu a putut fi verificat.",
            ),
          );
        }
      } finally {
        if (exportPollController.current === controller) {
          exportPollController.current = null;
          setExportBusy(false);
        }
      }
    })();
    return () => {
      controller.abort();
      if (exportPollController.current === controller) {
        exportPollController.current = null;
      }
    };
  }, [authorized, enabled, followExportOperation, identityKey, queryClient]);

  useEffect(
    () => () => {
      exportPollController.current?.abort();
      exportPollController.current = null;
    },
    [],
  );

  useEffect(() => {
    const first = months[0];
    if (!first) return;
    setSelectedYears((current) =>
      current.length > 0 ? current : [first.slice(0, 4)],
    );
    setSelectedMonthNumbers((current) =>
      current.length > 0 ? current : [first.slice(5, 7)],
    );
  }, [months]);

  const selectedDataset = useMemo(
    () => catalog?.datasets.find((item) => item.key === exportDataset) ?? null,
    [catalog, exportDataset],
  );
  const availableYears = useMemo(
    () =>
      Array.from(new Set(months.map((month) => month.slice(0, 4)))).sort(
        (a, b) => Number(b) - Number(a),
      ),
    [months],
  );
  const availableMonthNumbers = useMemo(
    () =>
      Array.from(
        new Set(
          months
            .filter((month) => selectedYears.includes(month.slice(0, 4)))
            .map((month) => month.slice(5, 7)),
        ),
      ).sort(),
    [months, selectedYears],
  );
  useEffect(() => {
    if (availableMonthNumbers.length === 0) return;
    const [firstMonthNumber] = availableMonthNumbers;
    if (!firstMonthNumber) return;
    setSelectedMonthNumbers((current) => {
      const valid = current.filter((month) =>
        availableMonthNumbers.includes(month),
      );
      return valid.length > 0 ? valid : [firstMonthNumber];
    });
  }, [availableMonthNumbers]);
  const exportMonths = useMemo(
    () =>
      months
        .filter(
          (month) =>
            selectedYears.includes(month.slice(0, 4)) &&
            selectedMonthNumbers.includes(month.slice(5, 7)),
        )
        .sort(),
    [months, selectedMonthNumbers, selectedYears],
  );
  const exportRequest = useMemo<ExportRequest>(
    () => ({
      export_mode: exportMode,
      dataset: exportDataset,
      months: exportMonths,
      dimensions: exportMode === "table" ? exportDimensions : [],
      metrics: exportMode === "table" ? exportMetrics : [],
      monthly_metrics: exportMode === "table" ? monthlyMetrics : [],
      daily_metrics:
        exportMode === "daily_comparison"
          ? dailyMetrics.length > 0
            ? dailyMetrics
            : DEFAULT_DAILY_METRICS
          : dailyMetrics,
      comparison_levels:
        exportMode === "daily_comparison" ? comparisonLevels : [],
      selected_days: selectedDays,
      filters: exportFilters,
      include_closed_stores: includeClosedStores,
      preview_limit: 100,
      filename: presenters.formatExportFilename(
        exportMode,
        exportDataset,
        exportMonths,
        selectedDays,
      ),
    }),
    [
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
    ],
  );

  const resetPreview = () => setPreview(null);
  const handleDatasetChange = (dataset: string) => {
    const next = catalog?.datasets.find((item) => item.key === dataset);
    setExportDataset(dataset);
    resetPreview();
    if (next) setExportDimensions(next.dimensions.map((item) => item.key));
  };
  const handleExportModeChange = (mode: ExportMode) => {
    setExportMode(mode);
    resetPreview();
    if (mode === "daily_comparison") {
      setDailyMetrics((current) =>
        current.length > 0 && current.length <= 4
          ? current
          : DEFAULT_DAILY_METRICS,
      );
      setComparisonLevels((current) =>
        current.length > 0 ? current : DEFAULT_COMPARISON_LEVELS,
      );
    }
  };
  const toggleFilter = (key: keyof ExportFilters, value: string) => {
    setExportFilters((current) => ({
      ...current,
      [key]: toggleValue(current[key], value),
    }));
    resetPreview();
  };
  const toggleYear = (year: string) => {
    setSelectedYears((current) => toggleValue(current, year, true).sort());
    resetPreview();
  };
  const toggleMonthNumber = (month: string) => {
    setSelectedMonthNumbers((current) =>
      toggleValue(current, month, true).sort(),
    );
    resetPreview();
  };
  const toggleDay = (day: number) => {
    setSelectedDays((current) =>
      toggleValue(current.map(String), String(day), true)
        .map(Number)
        .sort((a, b) => a - b),
    );
    resetPreview();
  };
  const handlePreviewExport = async () => {
    try {
      setExportBusy(true);
      setExportMessage("");
      setPreview(await previewExport(exportRequest));
    } catch (error) {
      setExportMessage(
        presenters.formatExportError(
          error,
          "Preview-ul nu a putut fi generat. Verifica selectia.",
        ),
      );
    } finally {
      setExportBusy(false);
    }
  };
  const handleDownloadExport = async () => {
    const controller = new AbortController();
    try {
      setExportBusy(true);
      setExportMessage("");
      setExportOperation(null);
      const complex =
        exportRequest.export_mode === "daily_comparison" ||
        (exportRequest.daily_metrics?.length ?? 0) > 0;
      if (complex) {
        exportPollController.current?.abort();
        exportPollController.current = controller;
        let initial: ExportOperation;
        try {
          initial = await createExportOperation(exportRequest);
          storeExportOperationId(identityKey, initial.id);
        } catch (error) {
          const operationId = uncertainExportOperationId(error);
          if (operationId === null) throw error;
          storeExportOperationId(identityKey, operationId);
          try {
            initial = await queryClient.fetchQuery({
              queryKey: queryKeys.settings.exportOperation(identityKey, operationId),
              queryFn: () => getExportOperation(operationId, controller.signal),
              staleTime: 0,
            });
          } catch {
            setExportMessage(
              `Exportul #${operationId} a fost rezervat, dar publicarea și statusul nu pot fi confirmate. Nu retrimite cererea.`,
            );
            return;
          }
        }
        await followExportOperation(initial, controller);
        return;
      }
      downloadBlob(
        await downloadExport(exportRequest),
        `${exportRequest.filename || "export_retail"}.xlsx`,
      );
    } catch (error) {
      setExportMessage(
        presenters.formatExportError(
          error,
          "Exportul nu a putut fi generat. Verifica selectia.",
        ),
      );
    } finally {
      if (exportPollController.current === controller) {
        exportPollController.current = null;
      }
      if (!controller.signal.aborted || exportPollController.current === null) {
        setExportBusy(false);
      }
    }
  };

  const handleCancelExport = async () => {
    const operation = exportOperation;
    if (!operation || !["queued", "running"].includes(operation.status)) return;
    setExportCancelling(true);
    setExportMessage("");
    exportPollController.current?.abort();
    exportPollController.current = null;
    try {
      const cancelled = await cancelExportOperation(operation.id);
      setExportOperation(cancelled);
      if (cancelled.status === "cancelled") {
        clearStoredExportOperationId(identityKey);
      }
      setExportMessage(
        cancelled.status === "cancelled"
          ? `Exportul #${operation.id} a fost anulat.`
          : `Exportul #${operation.id} nu mai poate fi anulat; status ${cancelled.status}.`,
      );
    } catch (error) {
      setExportMessage(
        presenters.formatExportError(error, "Exportul nu a putut fi anulat."),
      );
    } finally {
      setExportCancelling(false);
      setExportBusy(false);
    }
  };

  const handleRetryExportDownload = async () => {
    const operation = exportOperation;
    if (!operation || operation.status !== "completed" || !operation.can_download) return;
    const controller = new AbortController();
    exportPollController.current?.abort();
    exportPollController.current = controller;
    storeExportOperationId(identityKey, operation.id);
    setExportBusy(true);
    setExportMessage("");
    try {
      await followExportOperation(operation, controller);
    } catch (error) {
      if (!controller.signal.aborted) {
        setExportMessage(
          presenters.formatExportError(
            error,
            `Descărcarea exportului #${operation.id} a eșuat. Poți reîncerca până la expirare.`,
          ),
        );
      }
    } finally {
      if (exportPollController.current === controller) {
        exportPollController.current = null;
      }
      setExportBusy(false);
    }
  };

  return {
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
    isIncentiveProductsExport:
      exportMode === "table" && exportDataset === INCENTIVE_PRODUCTS_DATASET,
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
  };
}
