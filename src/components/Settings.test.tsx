// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("../auth/AuthContext", () => ({
  useAuth: () => ({ user: null }),
}));

vi.mock("../auth/permissions", () => ({
  canAdministerImports: () => false,
  canExportReports: () => false,
}));

vi.mock("../hooks/useAvailableMonths", () => ({
  useAvailableMonths: () => ({
    months: [],
    status: "empty",
    isLoading: false,
    isFetching: false,
    error: null,
    staleAt: null,
    retry: vi.fn(),
    setMonths: vi.fn(),
  }),
}));

import { SettingsPage as Settings } from "../features/settings/SettingsPage";
import { ImportsView } from "../features/settings/ImportsView";
import { ExportsView } from "../features/settings/ExportsView";
import type { ExportsModel, ImportsModel } from "../features/settings/types";

const importsModel = (overrides: Partial<ImportsModel> = {}): ImportsModel => ({
  history: [],
  file: null,
  setFile: vi.fn(),
  salesReplaceConfirmed: false,
  setSalesReplaceConfirmed: vi.fn(),
  salesCutoff: "2026-08-05",
  setSalesCutoff: vi.fn(),
  pendingSalesGeneration: null,
  setPendingSalesGeneration: vi.fn(),
  salesOverrideReason: "",
  setSalesOverrideReason: vi.fn(),
  uploading: false,
  promotingSales: false,
  message: "",
  messageType: "success",
  handleUpload: vi.fn(),
  handleSalesPromotion: vi.fn(),
  erpReconciliationMonths: [],
  erpReconciliationMonth: "",
  setErpReconciliationMonth: vi.fn(),
  erpReconciliationFile: null,
  setErpReconciliationFile: vi.fn(),
  erpReconciliationBusy: false,
  erpReconciliationError: "",
  erpReconciliationResult: null,
  setErpReconciliationError: vi.fn(),
  setErpReconciliationResult: vi.fn(),
  handleErpReconciliation: vi.fn(),
  promoActualsFile: null,
  setPromoActualsFile: vi.fn(),
  promoActualsMonth: "2026-08",
  setPromoActualsMonth: vi.fn(),
  promoActualsCutoff: "2026-08-05",
  setPromoActualsCutoff: vi.fn(),
  promoActualsUploading: false,
  promoActualsMessage: "",
  handlePromoActualsUpload: vi.fn(),
  ...overrides,
});

const exportsModel = (overrides: Partial<ExportsModel> = {}): ExportsModel => ({
  catalog: null,
  filterOptions: null,
  exportMode: "table",
  handleExportModeChange: vi.fn(),
  exportDataset: "agents",
  handleDatasetChange: vi.fn(),
  selectedDataset: null,
  availableYears: [],
  selectedYears: [],
  toggleYear: vi.fn(),
  availableMonthNumbers: [],
  selectedMonthNumbers: [],
  toggleMonthNumber: vi.fn(),
  selectedDays: [],
  setSelectedDays: vi.fn(),
  toggleDay: vi.fn(),
  exportMonths: [],
  includeClosedStores: false,
  setIncludeClosedStores: vi.fn(),
  isIncentiveProductsExport: false,
  exportFilters: { firma: [], regional: [], asm: [], site_code: [], agent: [] },
  toggleFilter: vi.fn(),
  exportDimensions: [],
  setExportDimensions: vi.fn(),
  exportMetrics: [],
  setExportMetrics: vi.fn(),
  monthlyMetrics: [],
  setMonthlyMetrics: vi.fn(),
  dailyMetrics: [],
  setDailyMetrics: vi.fn(),
  comparisonLevels: [],
  setComparisonLevels: vi.fn(),
  exportStep: 4,
  setExportStep: vi.fn(),
  exportBusy: false,
  exportCancelling: false,
  handlePreviewExport: vi.fn(),
  handleDownloadExport: vi.fn(),
  handleCancelExport: vi.fn(),
  handleRetryExportDownload: vi.fn(),
  exportMessage: "",
  exportOperation: null,
  preview: null,
  setPreview: vi.fn(),
  ...overrides,
});

describe("Settings permission boundary", () => {
  it("keeps restricted users on preferences and hides server operations", () => {
    const client = new QueryClient();
    render(
      <QueryClientProvider client={client}>
        <Settings
          theme="light"
          setTheme={vi.fn()}
          onImportCompleted={vi.fn()}
        />
      </QueryClientProvider>,
    );

    expect(
      screen.getByRole("tablist", { name: "Secțiuni Setări" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("tab", { name: "Preferințe", selected: true }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("tab", { name: "Importuri" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("tab", { name: "Exporturi" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText(/disponibile doar rolurilor manageriale/),
    ).toBeInTheDocument();
  });
});

describe("Settings operations", () => {
  it("shows import polling warning and keeps upload action disabled while loading", () => {
    render(
      <ImportsView
        model={importsModel({
          uploading: true,
          messageType: "warning",
          message: "Conexiune întreruptă temporar.",
        })}
      />,
    );

    expect(
      screen.getByText("Conexiune întreruptă temporar."),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Validare în desfășurare..." }),
    ).toBeDisabled();
  });

  it("surfaces ERP retry error and invokes the export preview action", () => {
    const retry = vi.fn();
    const preview = vi.fn();
    const { rerender } = render(
      <ImportsView
        model={importsModel({
          erpReconciliationError: "Reîncearcă verificarea ERP.",
          erpReconciliationFile: new File(["erp"], "erp.xlsx"),
          erpReconciliationMonth: "2026-08",
          handleErpReconciliation: retry,
        })}
      />,
    );

    expect(screen.getByText("Reîncearcă verificarea ERP.")).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: "Verifică raportul fără import" }),
    );
    expect(retry).toHaveBeenCalledOnce();
    rerender(
      <ExportsView
        model={exportsModel({
          handlePreviewExport: preview,
          exportMonths: ["2026-08"],
          selectedDays: [1],
        })}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Preview" }));
    expect(preview).toHaveBeenCalledOnce();
  });
});
