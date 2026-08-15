// @vitest-environment jsdom

import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../../../api/client";
import type {
  ImportCoverageReport,
  ImportJobStatus,
  ImportResponse,
  SalesGenerationManifest,
} from "../../../api/generated/runtime-types";
import type { ImportJobPollOutcome } from "../../../lib/importJobPolling";
import { formatIsoDateInput, shiftIsoDate } from "../../../lib/dates";

type SalesGenerationAnomaly = SalesGenerationManifest["anomalies"][number];

const api = vi.hoisted(() => ({
  getImportJobStatus: vi.fn(),
  pollImportJob: vi.fn(),
  promoteSalesGeneration: vi.fn(),
  uploadSalesFile: vi.fn(),
}));

vi.mock("../../../api/imports", () => ({
  getImportJobStatus: api.getImportJobStatus,
  promoteSalesGeneration: api.promoteSalesGeneration,
  uploadSalesFile: api.uploadSalesFile,
}));

vi.mock("../../../lib/importJobPolling", () => ({
  pollImportJob: api.pollImportJob,
}));

import { useSalesImport } from "./useSalesImport";

const EXPECTED_CUTOFF = shiftIsoDate(formatIsoDateInput(), -1);

function makeAnomaly(
  overrides: Partial<SalesGenerationAnomaly> = {},
): SalesGenerationAnomaly {
  return {
    blocking: false,
    classification: null,
    code: "coverage_drop",
    count: null,
    cutoff_date: null,
    drop_pct: null,
    import_month: null,
    incoming: null,
    max_sale_date: null,
    message: "Anomalie de test",
    months: null,
    previous: null,
    set_sha256: null,
    site_days: null,
    threshold_pct: null,
    ...overrides,
  };
}

function makeManifest(
  overrides: Partial<SalesGenerationManifest> = {},
): SalesGenerationManifest {
  return {
    agent_count: null,
    anomalies: [],
    business_sha256: "businesshash1234567890",
    cutoff_date: null,
    generation_state: null,
    import_month: null,
    max_sale_date: null,
    parser_resources: null,
    receipt_count: null,
    rows_filtered: null,
    rows_imported: null,
    rows_in_file: null,
    schema_version: null,
    site_day_count: null,
    site_day_sha256: null,
    site_days: null,
    source_sha256: null,
    stage_rows_sha256: null,
    store_count: null,
    total_quantity: null,
    total_value: null,
    ...overrides,
  };
}

function makeCoverage(
  overrides: Partial<ImportCoverageReport> = {},
): ImportCoverageReport {
  return {
    active_store_count_before: null,
    active_store_coverage_pct: null,
    anomalies: null,
    company_count: null,
    incoming_set_sha256: null,
    incoming_store_count: null,
    metadata_change_count: null,
    missing_active_set_sha256: null,
    missing_active_store_count: null,
    missing_prior_set_sha256: null,
    missing_prior_store_count: null,
    new_store_count: null,
    new_store_set_sha256: null,
    prior_snapshot_coverage_pct: null,
    prior_snapshot_store_count: null,
    store_activity_writes: null,
    stores_missing_count: null,
    stores_present_count: null,
    ...overrides,
  };
}

function makeImportResponse(
  overrides: Partial<ImportResponse> = {},
): ImportResponse {
  return {
    agent_count: 12,
    coverage_report: makeCoverage(),
    filename: "vanzari.xlsx",
    generation_state: "promoted",
    generation_token: null,
    import_month: "2026-07",
    is_month_final: false,
    manifest: null,
    manifest_sha256: null,
    rows_filtered: 0,
    rows_imported: 1500,
    rows_in_file: 1500,
    snapshot_id: 7,
    store_count: 30,
    ...overrides,
  };
}

function makeJob(overrides: Partial<ImportJobStatus> = {}): ImportJobStatus {
  return {
    erp_result: null,
    error: null,
    job_id: "sales-job-1",
    job_kind: "sales",
    promo_result: null,
    result: null,
    status: "queued",
    ...overrides,
  };
}

function makeActions() {
  return {
    refreshHistory: vi.fn().mockResolvedValue(undefined),
    onImportCompleted: vi.fn(),
    setErpReconciliationMonth: vi.fn(),
  };
}

const salesFile = () => new File(["sales-bytes"], "vanzari.xlsx");

function renderSalesImport(actions = makeActions()) {
  const hook = renderHook(() => useSalesImport(actions));
  return { ...hook, actions };
}

describe("useSalesImport", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("initializes inputs with the yesterday cutoff and idle flags", () => {
    const { result } = renderSalesImport();

    expect(result.current.file).toBeNull();
    expect(result.current.salesReplaceConfirmed).toBe(false);
    expect(result.current.salesCutoff).toBe(EXPECTED_CUTOFF);
    expect(result.current.pendingSalesGeneration).toBeNull();
    expect(result.current.salesOverrideReason).toBe("");
    expect(result.current.uploading).toBe(false);
    expect(result.current.promotingSales).toBe(false);
    expect(result.current.message).toBe("");
    expect(result.current.messageType).toBe("success");
    expect(api.uploadSalesFile).not.toHaveBeenCalled();
  });

  it("does not call the API until a file is selected and replace is confirmed", async () => {
    const { result } = renderSalesImport();

    await act(() => result.current.handleUpload());
    expect(api.uploadSalesFile).not.toHaveBeenCalled();

    act(() => result.current.setFile(salesFile()));
    await act(() => result.current.handleUpload());
    expect(api.uploadSalesFile).not.toHaveBeenCalled();
    expect(result.current.uploading).toBe(false);
  });

  it("stages a validated generation without touching live data", async () => {
    const { result, actions } = renderSalesImport();
    const validated = makeImportResponse({
      generation_state: "validated",
      generation_token: "token-1",
      manifest_sha256: "manifest-sha-1",
      snapshot_id: 9,
      manifest: makeManifest(),
    });
    const initialJob = makeJob();
    api.uploadSalesFile.mockResolvedValue(initialJob);
    api.pollImportJob.mockResolvedValue({
      kind: "complete",
      job: makeJob({ status: "complete", result: validated }),
    });

    const file = salesFile();
    act(() => {
      result.current.setFile(file);
      result.current.setSalesReplaceConfirmed(true);
      result.current.setSalesCutoff("2026-07-31");
    });
    await act(() => result.current.handleUpload());

    expect(api.uploadSalesFile).toHaveBeenCalledWith(file, "2026-07-31");
    expect(api.pollImportJob).toHaveBeenCalledWith(
      initialJob,
      expect.objectContaining({
        intervalMs: 1500,
        getStatus: api.getImportJobStatus,
        onConnectionIssue: expect.any(Function),
        onConnectionRestored: expect.any(Function),
      }),
    );
    expect(result.current.pendingSalesGeneration).toBe(validated);
    expect(result.current.salesOverrideReason).toBe("");
    expect(result.current.messageType).toBe("warning");
    expect(result.current.message).toContain("Generația 2026-07 a fost validată");
    expect(result.current.message).toContain("promovează explicit");
    expect(result.current.file).toBeNull();
    expect(result.current.salesReplaceConfirmed).toBe(false);
    expect(result.current.uploading).toBe(false);
    expect(actions.refreshHistory).not.toHaveBeenCalled();
    expect(actions.onImportCompleted).not.toHaveBeenCalled();
    expect(actions.setErpReconciliationMonth).not.toHaveBeenCalled();
  });

  it("reports a promoted import with coverage details and refreshes history", async () => {
    const { result, actions } = renderSalesImport();
    actions.refreshHistory.mockRejectedValueOnce(new Error("history offline"));
    const promoted = makeImportResponse({
      generation_state: "promoted",
      rows_imported: 1500,
      rows_filtered: 25,
      is_month_final: true,
      coverage_report: makeCoverage({
        active_store_coverage_pct: 98,
        missing_active_store_count: 1,
      }),
    });
    api.uploadSalesFile.mockResolvedValue(makeJob());
    api.pollImportJob.mockResolvedValue({
      kind: "complete",
      job: makeJob({ status: "complete", result: promoted }),
    });

    act(() => {
      result.current.setFile(salesFile());
      result.current.setSalesReplaceConfirmed(true);
    });
    await act(() => result.current.handleUpload());

    expect(actions.refreshHistory).toHaveBeenCalledTimes(1);
    expect(actions.onImportCompleted).toHaveBeenCalledWith("2026-07");
    expect(actions.setErpReconciliationMonth).toHaveBeenCalledWith("2026-07");
    expect(result.current.messageType).toBe("success");
    expect(result.current.message).toContain("Import 2026-07: 1500 rânduri importate");
    expect(result.current.message).toContain("25 rânduri non-ASM filtrate");
    expect(result.current.message).toContain("coverage magazine active 98%");
    expect(result.current.message).toContain("1 magazine active absente");
    expect(result.current.message).toContain("Luna a fost marcată ca FINALĂ");
    expect(result.current.file).toBeNull();
    expect(result.current.salesReplaceConfirmed).toBe(false);
  });

  it("blocks promotion of a blocking anomaly without a 10+ character reason", async () => {
    const { result } = renderSalesImport();
    const pending = makeImportResponse({
      generation_state: "validated",
      generation_token: "token-1",
      manifest_sha256: "manifest-sha-1",
      snapshot_id: 9,
      manifest: makeManifest({
        anomalies: [makeAnomaly({ blocking: true, code: "structural_contradiction" })],
      }),
    });
    act(() => result.current.setPendingSalesGeneration(pending));

    await act(() => result.current.handleSalesPromotion());
    expect(api.promoteSalesGeneration).not.toHaveBeenCalled();
    expect(result.current.messageType).toBe("error");
    expect(result.current.message).toContain("minimum 10 caractere");

    act(() => result.current.setSalesOverrideReason("scurt"));
    await act(() => result.current.handleSalesPromotion());
    expect(api.promoteSalesGeneration).not.toHaveBeenCalled();
    expect(result.current.pendingSalesGeneration).toBe(pending);
  });

  it("promotes a blocking-anomaly generation with a trimmed override reason", async () => {
    const { result, actions } = renderSalesImport();
    const pending = makeImportResponse({
      generation_state: "validated",
      generation_token: "token-1",
      manifest_sha256: "manifest-sha-1",
      snapshot_id: 9,
      manifest: makeManifest({
        anomalies: [makeAnomaly({ blocking: true })],
      }),
    });
    const promoted = makeImportResponse({
      generation_state: "promoted",
      manifest: makeManifest({ business_sha256: "businesshash1234567890" }),
    });
    const promoteJob = makeJob({ job_id: "promote-job-1" });
    api.promoteSalesGeneration.mockResolvedValue(promoteJob);
    api.pollImportJob.mockResolvedValue({
      kind: "complete",
      job: makeJob({ job_id: "promote-job-1", status: "complete", result: promoted }),
    });

    act(() => {
      result.current.setPendingSalesGeneration(pending);
      result.current.setSalesOverrideReason("  Motiv întemeiat pentru override  ");
    });
    await act(() => result.current.handleSalesPromotion());

    expect(api.promoteSalesGeneration).toHaveBeenCalledWith(
      9,
      "token-1",
      "manifest-sha-1",
      "Motiv întemeiat pentru override",
    );
    expect(api.pollImportJob).toHaveBeenCalledWith(
      promoteJob,
      expect.objectContaining({ getStatus: api.getImportJobStatus }),
    );
    expect(actions.refreshHistory).toHaveBeenCalledTimes(1);
    expect(actions.onImportCompleted).toHaveBeenCalledWith("2026-07");
    expect(actions.setErpReconciliationMonth).toHaveBeenCalledWith("2026-07");
    expect(result.current.pendingSalesGeneration).toBeNull();
    expect(result.current.salesOverrideReason).toBe("");
    expect(result.current.promotingSales).toBe(false);
    expect(result.current.messageType).toBe("success");
    expect(result.current.message).toContain("Import 2026-07 promovat: 1500 rânduri");
    expect(result.current.message).toContain("hash business businesshash");
  });

  it("promotes without an override reason when no anomaly is blocking", async () => {
    const { result } = renderSalesImport();
    const pending = makeImportResponse({
      generation_state: "validated",
      generation_token: "token-2",
      manifest_sha256: "manifest-sha-2",
      snapshot_id: 11,
      manifest: makeManifest({ anomalies: [makeAnomaly({ blocking: false })] }),
    });
    api.promoteSalesGeneration.mockResolvedValue(makeJob());
    api.pollImportJob.mockResolvedValue({
      kind: "complete",
      job: makeJob({ status: "complete", result: makeImportResponse({ generation_state: "promoted" }) }),
    });

    act(() => {
      result.current.setPendingSalesGeneration(pending);
      result.current.setSalesOverrideReason("un motiv care nu ar trebui trimis");
    });
    await act(() => result.current.handleSalesPromotion());

    expect(api.promoteSalesGeneration).toHaveBeenCalledWith(11, "token-2", "manifest-sha-2", undefined);
    expect(result.current.messageType).toBe("success");
  });

  it("does nothing when promoting without a complete pending generation", async () => {
    const { result } = renderSalesImport();

    await act(() => result.current.handleSalesPromotion());
    expect(api.promoteSalesGeneration).not.toHaveBeenCalled();

    act(() =>
      result.current.setPendingSalesGeneration(
        makeImportResponse({ generation_token: null, manifest_sha256: null, manifest: null }),
      ),
    );
    await act(() => result.current.handleSalesPromotion());
    expect(api.promoteSalesGeneration).not.toHaveBeenCalled();
  });

  it("surfaces promotion worker errors and unconfirmed promotions", async () => {
    const { result, actions } = renderSalesImport();
    const pending = makeImportResponse({
      generation_state: "validated",
      generation_token: "token-3",
      manifest_sha256: "manifest-sha-3",
      snapshot_id: 12,
      manifest: makeManifest(),
    });
    api.promoteSalesGeneration.mockResolvedValue(makeJob());
    api.pollImportJob.mockResolvedValue({
      kind: "complete",
      job: makeJob({ status: "complete", error: "promove boom" }),
    });

    act(() => result.current.setPendingSalesGeneration(pending));
    await act(() => result.current.handleSalesPromotion());

    expect(result.current.messageType).toBe("error");
    expect(result.current.message).toBe("Promovarea generației de vânzări a eșuat.");
    expect(result.current.promotingSales).toBe(false);
    expect(result.current.pendingSalesGeneration).toBe(pending);
    expect(actions.refreshHistory).not.toHaveBeenCalled();

    api.pollImportJob.mockResolvedValue({
      kind: "unconfirmed",
      reason: "connection",
      job: makeJob({ status: "in_progress" }),
    });
    await act(() => result.current.handleSalesPromotion());

    expect(result.current.messageType).toBe("warning");
    expect(result.current.message).toContain("Promovarea nu poate fi confirmată momentan");
    expect(actions.refreshHistory).not.toHaveBeenCalled();
  });

  it("keeps the upload flow alive through connection loss and warns on unconfirmed status", async () => {
    const { result } = renderSalesImport();
    const initialJob = makeJob({ job_id: "sales-conn" });
    api.uploadSalesFile.mockResolvedValue(initialJob);
    let pollOptions:
      | {
          onConnectionIssue?: (consecutiveErrors: number) => void;
          onConnectionRestored?: () => void;
        }
      | undefined;
    let resolvePoll: ((outcome: ImportJobPollOutcome) => void) | undefined;
    api.pollImportJob.mockImplementation((_job: ImportJobStatus, options: typeof pollOptions) => {
      pollOptions = options;
      return new Promise<ImportJobPollOutcome>((resolve) => {
        resolvePoll = resolve;
      });
    });

    let uploadPromise: Promise<void> | undefined;
    act(() => {
      result.current.setFile(salesFile());
      result.current.setSalesReplaceConfirmed(true);
    });
    act(() => {
      uploadPromise = result.current.handleUpload();
    });
    await waitFor(() => expect(api.pollImportJob).toHaveBeenCalledTimes(1));

    expect(result.current.uploading).toBe(true);
    expect(result.current.message).toBe("Fișier încărcat. Importul rulează în worker.");

    act(() => pollOptions?.onConnectionIssue?.(1));
    expect(result.current.messageType).toBe("warning");
    expect(result.current.message).toContain("Conexiune întreruptă temporar");

    act(() => pollOptions?.onConnectionRestored?.());
    expect(result.current.messageType).toBe("success");
    expect(result.current.message).toContain("Conexiune restabilită");

    await act(async () => {
      resolvePoll?.({
        kind: "unconfirmed",
        reason: "connection",
        job: makeJob({ job_id: "sales-conn", status: "in_progress" }),
      });
      await uploadPromise;
    });

    expect(result.current.messageType).toBe("warning");
    expect(result.current.message).toContain("statusul final nu poate fi confirmat momentan");
    expect(result.current.message).toContain("verifică istoricul înainte de a retrimite fișierul");
    expect(result.current.uploading).toBe(false);
  });

  it("warns when the connection drops before the upload is confirmed", async () => {
    const { result } = renderSalesImport();
    api.uploadSalesFile.mockRejectedValue(new TypeError("Failed to fetch"));

    act(() => {
      result.current.setFile(salesFile());
      result.current.setSalesReplaceConfirmed(true);
    });
    await act(() => result.current.handleUpload());

    expect(result.current.messageType).toBe("warning");
    expect(result.current.message).toContain("Conexiunea s-a întrerupt înainte de confirmare");
    expect(result.current.uploading).toBe(false);
    expect(api.pollImportJob).not.toHaveBeenCalled();
  });

  it("reports the generic failure message for sub-500 API rejections", async () => {
    const { result } = renderSalesImport();
    api.uploadSalesFile.mockRejectedValue(new ApiError(422, "Format invalid", null));

    act(() => {
      result.current.setFile(salesFile());
      result.current.setSalesReplaceConfirmed(true);
    });
    await act(() => result.current.handleUpload());

    expect(result.current.messageType).toBe("error");
    expect(result.current.message).toBe("Importul a eșuat. Verifică fișierul și încearcă din nou.");
  });

  it("reports worker job errors after a confirmed upload", async () => {
    const { result, actions } = renderSalesImport();
    api.uploadSalesFile.mockResolvedValue(makeJob());
    api.pollImportJob.mockResolvedValue({
      kind: "complete",
      job: makeJob({ status: "complete", error: "randuri duplicate" }),
    });

    act(() => {
      result.current.setFile(salesFile());
      result.current.setSalesReplaceConfirmed(true);
    });
    await act(() => result.current.handleUpload());

    expect(result.current.messageType).toBe("error");
    expect(result.current.message).toBe("Importul a eșuat: randuri duplicate");
    expect(result.current.uploading).toBe(false);
    expect(actions.refreshHistory).not.toHaveBeenCalled();
    expect(actions.onImportCompleted).not.toHaveBeenCalled();
  });

  it("rejects a validated generation whose manifest is incomplete", async () => {
    const { result } = renderSalesImport();
    api.uploadSalesFile.mockResolvedValue(makeJob());
    api.pollImportJob.mockResolvedValue({
      kind: "complete",
      job: makeJob({
        status: "complete",
        result: makeImportResponse({
          generation_state: "validated",
          generation_token: null,
          manifest_sha256: null,
          manifest: null,
        }),
      }),
    });

    act(() => {
      result.current.setFile(salesFile());
      result.current.setSalesReplaceConfirmed(true);
    });
    await act(() => result.current.handleUpload());

    expect(result.current.messageType).toBe("error");
    expect(result.current.message).toBe(
      "Importul a eșuat: Manifestul generației validate este incomplet.",
    );
    expect(result.current.pendingSalesGeneration).toBeNull();
  });

  it("warns when the worker completes without a verifiable result", async () => {
    const { result } = renderSalesImport();
    api.uploadSalesFile.mockResolvedValue(makeJob());
    api.pollImportJob.mockResolvedValue({
      kind: "complete",
      job: makeJob({ status: "complete", error: null, result: null }),
    });

    act(() => {
      result.current.setFile(salesFile());
      result.current.setSalesReplaceConfirmed(true);
    });
    await act(() => result.current.handleUpload());

    expect(result.current.messageType).toBe("warning");
    expect(result.current.message).toContain("rezultatul nu poate fi confirmat");
    expect(result.current.uploading).toBe(false);
  });
});
