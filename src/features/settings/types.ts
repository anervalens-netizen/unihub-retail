import type { Dispatch, SetStateAction } from "react";

import type {
  ExportFilters,
  ExportOperation,
  ExportPreview,
} from "../../api/exports";
import type { ErpReconciliationResponse } from "../../api/imports";
import type {
  FilterOptions,
  ImportHistoryEntry,
  ImportResponse,
} from "../../api/generated/runtime-types";
import type { ExportStep } from "./exports/controls";

export type SettingsSection = "imports" | "exports" | "preferences";
export type ExportMode = "table" | "daily_comparison";
export type SetState<T> = Dispatch<SetStateAction<T>>;
type SettingsCatalog = Awaited<
  ReturnType<typeof import("../../api/exports").getExportCatalog>
>;

export type ImportsModel = {
  history: ImportHistoryEntry[];
  file: File | null;
  setFile: SetState<File | null>;
  salesReplaceConfirmed: boolean;
  setSalesReplaceConfirmed: SetState<boolean>;
  salesCutoff: string;
  setSalesCutoff: SetState<string>;
  pendingSalesGeneration: ImportResponse | null;
  setPendingSalesGeneration: SetState<ImportResponse | null>;
  salesOverrideReason: string;
  setSalesOverrideReason: SetState<string>;
  uploading: boolean;
  promotingSales: boolean;
  message: string;
  messageType: "success" | "warning" | "error";
  handleUpload: () => Promise<void>;
  handleSalesPromotion: () => Promise<void>;
  erpReconciliationMonths: string[];
  erpReconciliationMonth: string;
  setErpReconciliationMonth: SetState<string>;
  erpReconciliationFile: File | null;
  setErpReconciliationFile: SetState<File | null>;
  erpReconciliationBusy: boolean;
  erpReconciliationError: string;
  erpReconciliationResult: ErpReconciliationResponse | null;
  setErpReconciliationError: SetState<string>;
  setErpReconciliationResult: SetState<ErpReconciliationResponse | null>;
  handleErpReconciliation: () => Promise<void>;
  promoActualsFile: File | null;
  setPromoActualsFile: SetState<File | null>;
  promoActualsMonth: string;
  setPromoActualsMonth: SetState<string>;
  promoActualsCutoff: string;
  setPromoActualsCutoff: SetState<string>;
  promoActualsUploading: boolean;
  promoActualsMessage: string;
  handlePromoActualsUpload: () => Promise<void>;
};

export type ExportsModel = {
  catalog: SettingsCatalog | null;
  filterOptions: FilterOptions | null;
  exportMode: ExportMode;
  handleExportModeChange: (mode: ExportMode) => void;
  exportDataset: string;
  handleDatasetChange: (dataset: string) => void;
  selectedDataset: SettingsCatalog["datasets"][number] | null;
  availableYears: string[];
  selectedYears: string[];
  toggleYear: (year: string) => void;
  availableMonthNumbers: string[];
  selectedMonthNumbers: string[];
  toggleMonthNumber: (month: string) => void;
  selectedDays: number[];
  setSelectedDays: SetState<number[]>;
  toggleDay: (day: number) => void;
  exportMonths: string[];
  includeClosedStores: boolean;
  setIncludeClosedStores: SetState<boolean>;
  isIncentiveProductsExport: boolean;
  exportFilters: ExportFilters;
  toggleFilter: (key: keyof ExportFilters, value: string) => void;
  exportDimensions: string[];
  setExportDimensions: SetState<string[]>;
  exportMetrics: string[];
  setExportMetrics: SetState<string[]>;
  monthlyMetrics: string[];
  setMonthlyMetrics: SetState<string[]>;
  dailyMetrics: string[];
  setDailyMetrics: SetState<string[]>;
  comparisonLevels: string[];
  setComparisonLevels: SetState<string[]>;
  exportStep: ExportStep;
  setExportStep: SetState<ExportStep>;
  exportBusy: boolean;
  exportCancelling: boolean;
  handlePreviewExport: () => Promise<void>;
  handleDownloadExport: () => Promise<void>;
  handleCancelExport: () => Promise<void>;
  handleRetryExportDownload: () => Promise<void>;
  exportMessage: string;
  exportOperation: ExportOperation | null;
  preview: ExportPreview | null;
  setPreview: SetState<ExportPreview | null>;
};
