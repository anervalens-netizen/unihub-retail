// @vitest-environment jsdom

import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../../../api/client";
import type {
  ErpReconciliationResponse,
  ImportJobStatus,
  PromoActualImportResponse,
} from "../../../api/generated/runtime-types";
import {
  formatIsoDateInput,
  getCurrentYearMonth,
  shiftIsoDate,
} from "../../../lib/dates";

const api = vi.hoisted(() => ({
  getImportJobStatus: vi.fn(),
  pollImportJob: vi.fn(),
  uploadErpReconciliationFile: vi.fn(),
  uploadPromoActualsFile: vi.fn(),
}));

vi.mock("../../../api/imports", () => ({
  getImportJobStatus: api.getImportJobStatus,
  uploadErpReconciliationFile: api.uploadErpReconciliationFile,
  uploadPromoActualsFile: api.uploadPromoActualsFile,
}));

vi.mock("../../../lib/importJobPolling", () => ({
  pollImportJob: api.pollImportJob,
}));

import {
  useErpReconciliationImport,
  usePromoActualsImport,
} from "./useAuxiliaryImports";

const EXPECTED_CUTOFF = shiftIsoDate(formatIsoDateInput(), -1);

function makeJob(overrides: Partial<ImportJobStatus> = {}): ImportJobStatus {
  return {
    erp_result: null,
    error: null,
    job_id: "aux-job-1",
    job_kind: "promo_actuals",
    promo_result: null,
    result: null,
    status: "queued",
    ...overrides,
  };
}

function makePromoResult(
  overrides: Partial<PromoActualImportResponse> = {},
): PromoActualImportResponse {
  return {
    config_sha256: "config-sha",
    cutoff_date: "2026-08-10",
    filename: "promo.xlsx",
    generation_id: "gen-abcdef123456-extra",
    import_month: "2026-08",
    material_sha256: "material-sha",
    promo_units: 12345,
    report_rows: 100,
    source_sha256: "source-sha",
    updated_promotions: 3,
    ...overrides,
  };
}

function makeErpResult(
  overrides: Partial<ErpReconciliationResponse> = {},
): ErpReconciliationResponse {
  return {
    app_only_metrics: [],
    cutoff_matches: true,
    file_digest: "file-digest",
    filename: "erp.xlsx",
    import_month: "2026-07",
    issue_count: 0,
    issues: [],
    metrics: [],
    notes: [],
    omitted_issue_count: 0,
    report_agent_count: 10,
    report_cutoff_date: "2026-08-01",
    report_store_count: 20,
    retail_agent_count: 10,
    retail_cutoff_date: "2026-08-01",
    retail_store_count: 20,
    status: "ok",
    ...overrides,
  };
}

describe("usePromoActualsImport", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("initializes with the current month, yesterday cutoff and idle state", () => {
    const { result } = renderHook(() => usePromoActualsImport());

    expect(result.current.promoActualsFile).toBeNull();
    expect(result.current.promoActualsMonth).toBe(getCurrentYearMonth());
    expect(result.current.promoActualsCutoff).toBe(EXPECTED_CUTOFF);
    expect(result.current.promoActualsUploading).toBe(false);
    expect(result.current.promoActualsMessage).toBe("");
    expect(api.uploadPromoActualsFile).not.toHaveBeenCalled();
  });

  it("does not call the API without a selected file", async () => {
    const { result } = renderHook(() => usePromoActualsImport());

    await act(() => result.current.handlePromoActualsUpload());

    expect(api.uploadPromoActualsFile).not.toHaveBeenCalled();
    expect(api.pollImportJob).not.toHaveBeenCalled();
    expect(result.current.promoActualsUploading).toBe(false);
  });

  it("applies a confirmed promo report and clears the selected file", async () => {
    const { result } = renderHook(() => usePromoActualsImport());
    const promoResult = makePromoResult();
    const initialJob = makeJob();
    api.uploadPromoActualsFile.mockResolvedValue(initialJob);
    api.pollImportJob.mockResolvedValue({
      kind: "complete",
      job: makeJob({ status: "complete", promo_result: promoResult }),
    });

    const file = new File(["promo-bytes"], "promo.xlsx");
    act(() => {
      result.current.setPromoActualsFile(file);
      result.current.setPromoActualsMonth("2026-08");
      result.current.setPromoActualsCutoff("2026-08-10");
    });
    await act(() => result.current.handlePromoActualsUpload());

    expect(api.uploadPromoActualsFile).toHaveBeenCalledWith(file, "2026-08", "2026-08-10");
    expect(api.pollImportJob).toHaveBeenCalledWith(
      initialJob,
      expect.objectContaining({
        intervalMs: 1500,
        getStatus: api.getImportJobStatus,
      }),
    );
    const formattedUnits = (12345).toLocaleString("ro-RO");
    expect(result.current.promoActualsMessage).toContain(
      `Raport aplicat: ${formattedUnits} unități promo`,
    );
    expect(result.current.promoActualsMessage).toContain("cutoff 2026-08-10");
    expect(result.current.promoActualsMessage).toContain("3 promoții actualizate");
    expect(result.current.promoActualsMessage).toContain("Generație gen-abcdef12");
    expect(result.current.promoActualsFile).toBeNull();
    expect(result.current.promoActualsUploading).toBe(false);
  });

  it("keeps the file selected and reports worker errors", async () => {
    const { result } = renderHook(() => usePromoActualsImport());
    api.uploadPromoActualsFile.mockResolvedValue(makeJob());
    api.pollImportJob.mockResolvedValue({
      kind: "complete",
      job: makeJob({ status: "complete", error: "cutoff regresiv" }),
    });

    act(() => result.current.setPromoActualsFile(new File(["x"], "promo.xlsx")));
    await act(() => result.current.handlePromoActualsUpload());

    expect(result.current.promoActualsMessage).toBe(
      "Importul raportului promo a eșuat.",
    );
    expect(result.current.promoActualsFile).not.toBeNull();
    expect(result.current.promoActualsUploading).toBe(false);
  });

  it("warns against resubmission when the promo job stays unconfirmed", async () => {
    const { result } = renderHook(() => usePromoActualsImport());
    api.uploadPromoActualsFile.mockResolvedValue(makeJob());
    api.pollImportJob.mockResolvedValue({
      kind: "unconfirmed",
      reason: "connection",
      job: makeJob({ status: "in_progress" }),
    });

    act(() => result.current.setPromoActualsFile(new File(["x"], "promo.xlsx")));
    await act(() => result.current.handlePromoActualsUpload());

    expect(result.current.promoActualsMessage).toContain(
      "statusul nu poate fi confirmat momentan",
    );
    expect(result.current.promoActualsMessage).toContain("Nu retrimite fișierul");
    expect(result.current.promoActualsUploading).toBe(false);
  });
});

describe("useErpReconciliationImport", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("initializes idle with an empty month and no result", () => {
    const { result } = renderHook(() => useErpReconciliationImport());

    expect(result.current.erpReconciliationMonth).toBe("");
    expect(result.current.erpReconciliationFile).toBeNull();
    expect(result.current.erpReconciliationBusy).toBe(false);
    expect(result.current.erpReconciliationError).toBe("");
    expect(result.current.erpReconciliationResult).toBeNull();
    expect(api.uploadErpReconciliationFile).not.toHaveBeenCalled();
  });

  it("does not call the API without a selected file", async () => {
    const { result } = renderHook(() => useErpReconciliationImport());

    await act(() => result.current.handleErpReconciliation());

    expect(api.uploadErpReconciliationFile).not.toHaveBeenCalled();
    expect(result.current.erpReconciliationBusy).toBe(false);
  });

  it("stores the reconciliation result for a confirmed job", async () => {
    const { result } = renderHook(() => useErpReconciliationImport());
    const erpResult = makeErpResult();
    const initialJob = makeJob({ job_kind: "erp_reconciliation" });
    api.uploadErpReconciliationFile.mockResolvedValue(initialJob);
    api.pollImportJob.mockResolvedValue({
      kind: "complete",
      job: makeJob({ status: "complete", erp_result: erpResult }),
    });

    const file = new File(["erp-bytes"], "erp.xlsx");
    act(() => {
      result.current.setErpReconciliationFile(file);
      result.current.setErpReconciliationMonth("2026-07");
    });
    await act(() => result.current.handleErpReconciliation());

    expect(api.uploadErpReconciliationFile).toHaveBeenCalledWith(file, "2026-07");
    expect(api.pollImportJob).toHaveBeenCalledWith(
      initialJob,
      expect.objectContaining({ getStatus: api.getImportJobStatus }),
    );
    expect(result.current.erpReconciliationResult).toBe(erpResult);
    expect(result.current.erpReconciliationError).toBe("");
    expect(result.current.erpReconciliationBusy).toBe(false);
  });

  it("reports worker errors without a result", async () => {
    const { result } = renderHook(() => useErpReconciliationImport());
    api.uploadErpReconciliationFile.mockResolvedValue(makeJob());
    api.pollImportJob.mockResolvedValue({
      kind: "complete",
      job: makeJob({ status: "complete", error: "digest nepotrivit" }),
    });

    act(() => result.current.setErpReconciliationFile(new File(["x"], "erp.xlsx")));
    await act(() => result.current.handleErpReconciliation());

    expect(result.current.erpReconciliationError).toBe(
      "Verificarea raportului ERP a eșuat.",
    );
    expect(result.current.erpReconciliationResult).toBeNull();
    expect(result.current.erpReconciliationBusy).toBe(false);
  });

  it("surfaces an expired session from the upload call", async () => {
    const { result } = renderHook(() => useErpReconciliationImport());
    api.uploadErpReconciliationFile.mockRejectedValue(new ApiError(401, "", null));

    act(() => result.current.setErpReconciliationFile(new File(["x"], "erp.xlsx")));
    await act(() => result.current.handleErpReconciliation());

    expect(result.current.erpReconciliationError).toBe(
      "Sesiunea a expirat. Vei fi redirectionat catre autentificare.",
    );
    expect(result.current.erpReconciliationBusy).toBe(false);
    expect(api.pollImportJob).not.toHaveBeenCalled();
  });

  it("warns against resubmission when the reconciliation stays unconfirmed", async () => {
    const { result } = renderHook(() => useErpReconciliationImport());
    api.uploadErpReconciliationFile.mockResolvedValue(makeJob());
    api.pollImportJob.mockResolvedValue({
      kind: "unconfirmed",
      reason: "not_found",
      job: makeJob({ status: "queued" }),
    });

    act(() => result.current.setErpReconciliationFile(new File(["x"], "erp.xlsx")));
    await act(() => result.current.handleErpReconciliation());

    expect(result.current.erpReconciliationError).toContain("Nu retrimite raportul");
    expect(result.current.erpReconciliationResult).toBeNull();
    expect(result.current.erpReconciliationBusy).toBe(false);
  });
});
