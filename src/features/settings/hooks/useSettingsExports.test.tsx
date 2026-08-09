// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  createExportOperation: vi.fn(),
  cancelExportOperation: vi.fn(),
  downloadBlob: vi.fn(),
  downloadExport: vi.fn(),
  downloadExportOperation: vi.fn(),
  getAvailableMonths: vi.fn(),
  getExportCatalog: vi.fn(),
  getExportOperation: vi.fn(),
  getResumableExportOperation: vi.fn(),
  getFilterOptions: vi.fn(),
  pollExportOperation: vi.fn(),
  previewExport: vi.fn(),
  uncertainExportOperationId: vi.fn(),
}));

vi.mock("../../../api/exports", () => ({
  cancelExportOperation: api.cancelExportOperation,
  createExportOperation: api.createExportOperation,
  downloadExport: api.downloadExport,
  downloadExportOperation: api.downloadExportOperation,
  getExportCatalog: api.getExportCatalog,
  getExportOperation: api.getExportOperation,
  getResumableExportOperation: api.getResumableExportOperation,
  previewExport: api.previewExport,
  uncertainExportOperationId: api.uncertainExportOperationId,
}));

vi.mock("../../../lib/exportOperationPolling", () => ({
  pollExportOperation: api.pollExportOperation,
}));

vi.mock("../../../api/filters", () => ({
  getAvailableMonths: api.getAvailableMonths,
  getFilterOptions: api.getFilterOptions,
}));

vi.mock("../../../lib/download", () => ({ downloadBlob: api.downloadBlob }));

import { useSettingsExports } from "./useSettingsExports";

const catalog = {
  comparison_levels: [],
  daily_metrics: [],
  datasets: [
    {
      key: "agents",
      label: "Agenți",
      description: "",
      dimensions: [
        { key: "agent", label: "Agent", group: "general", type: "string" },
      ],
    },
    {
      key: "stores",
      label: "Magazine",
      description: "",
      dimensions: [
        {
          key: "site_code",
          label: "Magazin",
          group: "general",
          type: "string",
        },
      ],
    },
  ],
  metrics: [],
  monthly_metrics: [],
};

const filterOptions = {
  agenti: [],
  asmi: [],
  firme: [],
  magazine: [],
  regionali: [],
};

function wrapper(client = new QueryClient({
  defaultOptions: { queries: { retry: false, staleTime: Infinity } },
})) {
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
}

describe("useSettingsExports request ownership", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.sessionStorage.clear();
    api.getAvailableMonths.mockResolvedValue(["2026-08", "2026-07"]);
    api.getExportCatalog.mockResolvedValue(catalog);
    api.getFilterOptions.mockResolvedValue(filterOptions);
    api.getResumableExportOperation.mockResolvedValue(null);
    api.uncertainExportOperationId.mockReturnValue(null);
  });

  it("does not refetch bootstrap data on dataset changes and isolates identities", async () => {
    const { result, rerender } = renderHook(
      ({ identityKey }) => useSettingsExports(true, identityKey),
      { initialProps: { identityKey: "user-a" }, wrapper: wrapper() },
    );

    await waitFor(() => {
      expect(result.current.catalog).not.toBeNull();
      expect(result.current.exportMonths).toEqual(["2026-08"]);
      expect(result.current.filterOptions).not.toBeNull();
    });
    expect(api.getAvailableMonths).toHaveBeenCalledTimes(1);
    expect(api.getExportCatalog).toHaveBeenCalledTimes(1);
    expect(api.getFilterOptions).toHaveBeenCalledTimes(1);

    act(() => result.current.handleDatasetChange("stores"));
    expect(result.current.exportDataset).toBe("stores");
    expect(api.getAvailableMonths).toHaveBeenCalledTimes(1);
    expect(api.getExportCatalog).toHaveBeenCalledTimes(1);
    expect(api.getFilterOptions).toHaveBeenCalledTimes(1);

    rerender({ identityKey: "user-b" });
    await waitFor(() => {
      expect(api.getAvailableMonths).toHaveBeenCalledTimes(2);
      expect(api.getExportCatalog).toHaveBeenCalledTimes(2);
      expect(api.getFilterOptions).toHaveBeenCalledTimes(2);
    });
  });

  it("surfaces preview/download errors and permits an explicit retry", async () => {
    const { result } = renderHook(
      () => useSettingsExports(true, "user-a"),
      { wrapper: wrapper() },
    );
    await waitFor(() => expect(result.current.exportMonths).toEqual(["2026-08"]));

    api.previewExport
      .mockRejectedValueOnce(new Error("preview offline"))
      .mockResolvedValueOnce({ columns: [], rows: [], total_rows: 0, truncated: false });
    await act(() => result.current.handlePreviewExport());
    expect(result.current.exportMessage).toContain(
      "Preview-ul nu a putut fi generat",
    );
    await act(() => result.current.handlePreviewExport());
    expect(api.previewExport).toHaveBeenCalledTimes(2);
    expect(result.current.preview?.total_rows).toBe(0);

    api.downloadExport
      .mockRejectedValueOnce(new Error("download offline"))
      .mockResolvedValueOnce(new Blob(["xlsx"]));
    await act(() => result.current.handleDownloadExport());
    expect(result.current.exportMessage).toContain(
      "Exportul nu a putut fi generat",
    );
    await act(() => result.current.handleDownloadExport());
    expect(api.downloadExport).toHaveBeenCalledTimes(2);
    expect(api.downloadBlob).toHaveBeenCalledOnce();
  });

  it("invalidates Settings queries when export permission is revoked", async () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: Infinity } },
    });
    const { rerender } = renderHook(
      ({ enabled, authorized }) =>
        useSettingsExports(enabled, "user-a", authorized),
      {
        initialProps: { enabled: true, authorized: true },
        wrapper: wrapper(client),
      },
    );
    await waitFor(() => expect(api.getExportCatalog).toHaveBeenCalledOnce());

    rerender({ enabled: false, authorized: false });
    await waitFor(() =>
      expect(
        client.getQueryData(["settings", "user-a", "export-catalog"]),
      ).toBeUndefined(),
    );

    rerender({ enabled: true, authorized: true });
    await waitFor(() => expect(api.getExportCatalog).toHaveBeenCalledTimes(2));
  });

  it("creates one durable complex operation, polls its id, then downloads the artifact", async () => {
    const queued = {
      id: 7,
      kind: "daily_metrics",
      status: "queued",
      job_id: "export-complex:7",
      filename: null,
      artifact_size: null,
      artifact_sha256: null,
      error_code: null,
      created_at: "2026-08-06T12:00:00Z",
      started_at: null,
      finished_at: null,
      expires_at: null,
      can_download: false,
    } as const;
    const completed = {
      ...queued,
      status: "completed" as const,
      filename: "complex.xlsx",
      artifact_size: 42,
      artifact_sha256: "a".repeat(64),
      finished_at: "2026-08-06T12:01:00Z",
      expires_at: "2026-08-06T13:01:00Z",
      can_download: true,
    };
    api.createExportOperation.mockResolvedValue(queued);
    api.pollExportOperation.mockResolvedValue({
      kind: "terminal",
      operation: completed,
    });
    api.downloadExportOperation.mockResolvedValue(new Blob(["xlsx"]));
    const { result } = renderHook(() => useSettingsExports(true, "user-a"), {
      wrapper: wrapper(),
    });
    await waitFor(() => expect(result.current.exportMonths).toEqual(["2026-08"]));

    act(() => result.current.setDailyMetrics(["total_sales"]));
    await act(() => result.current.handleDownloadExport());

    expect(api.createExportOperation).toHaveBeenCalledOnce();
    expect(api.pollExportOperation).toHaveBeenCalledOnce();
    expect(api.downloadExportOperation).toHaveBeenCalledExactlyOnceWith(
      7,
      expect.any(AbortSignal),
    );
    expect(api.downloadExport).not.toHaveBeenCalled();
    expect(api.downloadBlob).toHaveBeenCalledWith(expect.any(Blob), "complex.xlsx");
    expect(result.current.exportOperation?.status).toBe("completed");
  });

  it("recovers one completed unclaimed operation after reopen and downloads it once", async () => {
    const completed = {
      id: 11,
      kind: "daily_comparison",
      status: "completed",
      job_id: "export-complex:11",
      filename: "recovered.xlsx",
      artifact_size: 42,
      artifact_sha256: "a".repeat(64),
      peak_rss_bytes: 1024,
      build_seconds: 0.3,
      cell_count: 20,
      error_code: null,
      created_at: "2026-08-06T12:00:00Z",
      started_at: "2026-08-06T12:00:01Z",
      finished_at: "2026-08-06T12:01:00Z",
      expires_at: "2026-08-06T13:01:00Z",
      can_download: true,
    } as const;
    api.getResumableExportOperation
      .mockResolvedValueOnce(completed)
      .mockResolvedValueOnce(null);
    api.pollExportOperation.mockResolvedValue({
      kind: "terminal",
      operation: completed,
    });
    api.downloadExportOperation.mockResolvedValue(new Blob(["xlsx"]));

    const first = renderHook(() => useSettingsExports(true, "user-a"), {
      wrapper: wrapper(),
    });
    await waitFor(() => expect(api.downloadBlob).toHaveBeenCalledOnce());
    expect(api.createExportOperation).not.toHaveBeenCalled();
    first.unmount();

    const second = renderHook(() => useSettingsExports(true, "user-a"), {
      wrapper: wrapper(),
    });
    await waitFor(() => expect(api.getResumableExportOperation).toHaveBeenCalledTimes(2));
    expect(api.downloadBlob).toHaveBeenCalledOnce();
    second.unmount();
  });

  it("keeps the stored id after transport failure and retries explicitly after reload", async () => {
    const completed = {
      id: 15,
      kind: "daily_comparison",
      status: "completed",
      job_id: "export-complex:15",
      filename: "retry.xlsx",
      artifact_size: 42,
      artifact_sha256: "a".repeat(64),
      peak_rss_bytes: 1024,
      build_seconds: 0.3,
      cell_count: 20,
      error_code: null,
      created_at: "2026-08-06T12:00:00Z",
      started_at: "2026-08-06T12:00:01Z",
      finished_at: "2026-08-06T12:01:00Z",
      expires_at: "2026-08-06T13:01:00Z",
      can_download: true,
    } as const;
    api.getResumableExportOperation
      .mockResolvedValueOnce(completed)
      .mockResolvedValue(null);
    api.getExportOperation.mockResolvedValue(completed);
    api.pollExportOperation.mockResolvedValue({ kind: "terminal", operation: completed });
    api.downloadExportOperation
      .mockRejectedValueOnce(new Error("transport interrupted"))
      .mockResolvedValueOnce(new Blob(["xlsx"]));

    const first = renderHook(() => useSettingsExports(true, "user-a"), {
      wrapper: wrapper(),
    });
    await waitFor(() => expect(first.result.current.exportMessage).toContain("Statusul exportului activ"));
    expect(window.sessionStorage.getItem("unihub:settings:export-operation:user-a")).toBe("15");
    first.unmount();

    const second = renderHook(() => useSettingsExports(true, "user-a"), {
      wrapper: wrapper(),
    });
    await waitFor(() => expect(api.downloadBlob).toHaveBeenCalledOnce());
    expect(api.getExportOperation).toHaveBeenCalledWith(15, expect.any(AbortSignal));
    expect(api.downloadExportOperation).toHaveBeenCalledTimes(2);
    expect(window.sessionStorage.getItem("unihub:settings:export-operation:user-a")).toBeNull();
    second.unmount();

    const third = renderHook(() => useSettingsExports(true, "user-a"), {
      wrapper: wrapper(),
    });
    await waitFor(() => expect(api.getResumableExportOperation).toHaveBeenCalledTimes(2));
    expect(api.downloadExportOperation).toHaveBeenCalledTimes(2);
    third.unmount();
  });

  it("recovers a publish-uncertain id without resubmitting", async () => {
    const uncertain = new Error("publish timeout");
    const queued = {
      id: 12,
      kind: "daily_metrics",
      status: "queued",
      job_id: "export-complex:12",
      filename: null,
      artifact_size: null,
      artifact_sha256: null,
      peak_rss_bytes: null,
      build_seconds: null,
      cell_count: null,
      error_code: null,
      created_at: "2026-08-06T12:00:00Z",
      started_at: null,
      finished_at: null,
      expires_at: null,
      can_download: false,
    } as const;
    api.createExportOperation.mockRejectedValue(uncertain);
    api.uncertainExportOperationId.mockReturnValue(12);
    api.getExportOperation.mockResolvedValue(queued);
    api.pollExportOperation.mockResolvedValue({ kind: "unconfirmed", operation: queued });
    const { result } = renderHook(() => useSettingsExports(true, "user-a"), {
      wrapper: wrapper(),
    });
    await waitFor(() => expect(result.current.exportBusy).toBe(false));

    act(() => result.current.setDailyMetrics(["total_sales"]));
    await act(() => result.current.handleDownloadExport());

    expect(api.createExportOperation).toHaveBeenCalledOnce();
    expect(api.getExportOperation).toHaveBeenCalledWith(12, expect.any(AbortSignal));
    expect(result.current.exportMessage).toContain("Nu retrimite cererea");
  });

  it("aborts local polling on unmount without cancelling the durable operation", async () => {
    const queued = {
      id: 13,
      kind: "daily_metrics",
      status: "queued",
      job_id: "export-complex:13",
      filename: null,
      artifact_size: null,
      artifact_sha256: null,
      peak_rss_bytes: null,
      build_seconds: null,
      cell_count: null,
      error_code: null,
      created_at: "2026-08-06T12:00:00Z",
      started_at: null,
      finished_at: null,
      expires_at: null,
      can_download: false,
    } as const;
    api.getResumableExportOperation.mockResolvedValue(queued);
    let observedSignal: AbortSignal | undefined;
    api.pollExportOperation.mockImplementation(
      async (_initial, _fetchStatus, options) => {
        observedSignal = options.signal;
        await new Promise<void>((resolve) =>
          options.signal?.addEventListener("abort", () => resolve(), { once: true }),
        );
        return { kind: "aborted", operation: queued };
      },
    );
    const hook = renderHook(() => useSettingsExports(true, "user-a"), {
      wrapper: wrapper(),
    });
    await waitFor(() => expect(observedSignal).toBeDefined());

    hook.unmount();

    expect(observedSignal?.aborted).toBe(true);
    expect(api.cancelExportOperation).not.toHaveBeenCalled();
  });

  it("cancels an active durable operation only after explicit user action", async () => {
    const queued = {
      id: 14,
      kind: "daily_metrics",
      status: "queued",
      job_id: "export-complex:14",
      filename: null,
      artifact_size: null,
      artifact_sha256: null,
      peak_rss_bytes: null,
      build_seconds: null,
      cell_count: null,
      error_code: null,
      created_at: "2026-08-06T12:00:00Z",
      started_at: null,
      finished_at: null,
      expires_at: null,
      can_download: false,
    } as const;
    const cancelled = {
      ...queued,
      status: "cancelled" as const,
      error_code: "cancelled_by_user",
      finished_at: "2026-08-06T12:00:10Z",
    };
    api.getResumableExportOperation.mockResolvedValue(queued);
    api.pollExportOperation.mockImplementation(
      async (_initial, _fetchStatus, options) => {
        await new Promise<void>((resolve) =>
          options.signal?.addEventListener("abort", () => resolve(), { once: true }),
        );
        return { kind: "aborted", operation: queued };
      },
    );
    api.cancelExportOperation.mockResolvedValue(cancelled);
    const { result } = renderHook(() => useSettingsExports(true, "user-a"), {
      wrapper: wrapper(),
    });
    await waitFor(() => expect(result.current.exportOperation?.id).toBe(14));

    await act(() => result.current.handleCancelExport());

    expect(api.cancelExportOperation).toHaveBeenCalledExactlyOnceWith(14);
    expect(result.current.exportOperation?.status).toBe("cancelled");
    expect(result.current.exportMessage).toContain("a fost anulat");
  });

  it("does not resubmit a complex export whose status is unconfirmed", async () => {
    const queued = {
      id: 8,
      kind: "daily_metrics",
      status: "queued",
      job_id: "export-complex:8",
      filename: null,
      artifact_size: null,
      artifact_sha256: null,
      error_code: null,
      created_at: "2026-08-06T12:00:00Z",
      started_at: null,
      finished_at: null,
      expires_at: null,
      can_download: false,
    } as const;
    api.createExportOperation.mockResolvedValue(queued);
    api.pollExportOperation.mockResolvedValue({
      kind: "unconfirmed",
      operation: queued,
    });
    const { result } = renderHook(() => useSettingsExports(true, "user-a"), {
      wrapper: wrapper(),
    });
    await waitFor(() => expect(result.current.exportMonths).toEqual(["2026-08"]));

    act(() => result.current.setDailyMetrics(["total_sales"]));
    await act(() => result.current.handleDownloadExport());

    expect(api.createExportOperation).toHaveBeenCalledExactlyOnceWith(
      expect.objectContaining({ daily_metrics: ["total_sales"] }),
    );
    expect(api.downloadExportOperation).not.toHaveBeenCalled();
    expect(result.current.exportMessage).toContain("Nu retrimite cererea");
  });
});
