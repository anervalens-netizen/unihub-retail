import { useCallback, useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import {
  getImportHistory,
  getImportJobStatus,
  promoteSalesGeneration,
  uploadErpReconciliationFile,
  uploadPromoActualsFile,
  uploadSalesFile,
} from "../../../api/imports";
import type { ErpReconciliationResponse } from "../../../api/imports";
import type {
  ImportResponse,
} from "../../../api/generated/runtime-types";
import { ApiError } from "../../../api/client";
import { pollImportJob } from "../../../lib/importJobPolling";
import { queryKeys } from "../../../lib/queryKeys";
import {
  formatIsoDateInput,
  getCurrentYearMonth,
  shiftIsoDate,
} from "../../../lib/dates";
import * as presenters from "../presenters";
import type { ImportsModel } from "../types";

const CACHE_TTL_MS = 5 * 60 * 1000;
const POLL_OPTIONS = {
  intervalMs: 1500,
  // Fereastră UI maximă 30 min; rezultatele ARQ sunt păstrate minimum 60 min.
  maxAttempts: 1200,
  maxConsecutiveErrors: 20,
  getStatus: getImportJobStatus,
};
const yesterday = () => shiftIsoDate(formatIsoDateInput(), -1);

export function useSettingsImports(
  enabled: boolean,
  onImportCompleted: (month: string) => void,
  identityKey = "anonymous",
  authorized = enabled,
): ImportsModel {
  const queryClient = useQueryClient();
  const historyKey = useMemo(
    () => queryKeys.settings.imports(identityKey),
    [identityKey],
  );
  const historyQuery = useQuery({
    queryKey: historyKey,
    enabled,
    queryFn: ({ signal }) => getImportHistory(signal),
    staleTime: CACHE_TTL_MS,
    retry: 1,
  });
  const history = useMemo(() => historyQuery.data ?? [], [historyQuery.data]);
  const [file, setFile] = useState<File | null>(null);
  const [salesReplaceConfirmed, setSalesReplaceConfirmed] = useState(false);
  const [salesCutoff, setSalesCutoff] = useState(yesterday);
  const [pendingSalesGeneration, setPendingSalesGeneration] =
    useState<ImportResponse | null>(null);
  const [salesOverrideReason, setSalesOverrideReason] = useState("");
  const [uploading, setUploading] = useState(false);
  const [promotingSales, setPromotingSales] = useState(false);
  const [message, setMessage] = useState("");
  const [messageType, setMessageType] = useState<
    "success" | "warning" | "error"
  >("success");
  const [erpReconciliationFile, setErpReconciliationFile] =
    useState<File | null>(null);
  const [erpReconciliationMonth, setErpReconciliationMonth] = useState("");
  const [erpReconciliationBusy, setErpReconciliationBusy] = useState(false);
  const [erpReconciliationError, setErpReconciliationError] = useState("");
  const [erpReconciliationResult, setErpReconciliationResult] =
    useState<ErpReconciliationResponse | null>(null);
  const [promoActualsFile, setPromoActualsFile] = useState<File | null>(null);
  const [promoActualsMonth, setPromoActualsMonth] =
    useState(getCurrentYearMonth);
  const [promoActualsCutoff, setPromoActualsCutoff] = useState(yesterday);
  const [promoActualsUploading, setPromoActualsUploading] = useState(false);
  const [promoActualsMessage, setPromoActualsMessage] = useState("");

  const refreshHistory = useCallback(async () => {
    await queryClient.invalidateQueries({ queryKey: historyKey, exact: true });
    await queryClient.fetchQuery({
      queryKey: historyKey,
      queryFn: ({ signal }) => getImportHistory(signal),
      staleTime: 0,
    });
  }, [historyKey, queryClient]);

  useEffect(() => {
    if (!authorized) {
      void queryClient.removeQueries({ queryKey: historyKey, exact: true });
      return;
    }
    if (enabled && historyQuery.isError) {
      setMessage("Nu am putut încărca istoricul importurilor.");
      setMessageType("error");
    }
  }, [authorized, enabled, historyKey, historyQuery.isError, queryClient]);

  const erpReconciliationMonths = useMemo(
    () =>
      Array.from(
        new Set(
          history
            .filter((entry) => entry.status === "completed")
            .map((entry) => entry.import_month),
        ),
      ).sort((a, b) => b.localeCompare(a)),
    [history],
  );

  useEffect(() => {
    setErpReconciliationMonth((current) =>
      erpReconciliationMonths.includes(current)
        ? current
        : (erpReconciliationMonths[0] ?? ""),
    );
  }, [erpReconciliationMonths]);

  const handleUpload = async () => {
    if (!file || !salesReplaceConfirmed) return;
    let uploadAccepted = false;
    try {
      setUploading(true);
      setMessage("");
      setMessageType("success");
      const initialJob = await uploadSalesFile(file, salesCutoff);
      uploadAccepted = true;
      setMessage("Fișier încărcat. Importul rulează în worker.");
      const outcome = await pollImportJob(initialJob, {
        ...POLL_OPTIONS,
        onConnectionIssue: () => {
          setMessageType("warning");
          setMessage(
            "Conexiune întreruptă temporar. Importul continuă în worker; reconectez automat.",
          );
        },
        onConnectionRestored: () => {
          setMessageType("success");
          setMessage("Conexiune restabilită. Importul rulează în worker.");
        },
      });
      if (outcome.kind === "unconfirmed") {
        setMessageType("warning");
        setMessage(
          "Fișierul a fost încărcat, dar statusul final nu poate fi confirmat momentan. Importul poate continua în worker; reîncarcă pagina și verifică istoricul înainte de a retrimite fișierul.",
        );
        return;
      }
      const job = outcome.job;
      if (job.error || !job.result) {
        if (job.error) throw new Error(job.error);
        setMessageType("warning");
        setMessage(
          "Workerul a încheiat jobul, dar rezultatul nu poate fi confirmat. Verifică istoricul importurilor.",
        );
        return;
      }
      const response = job.result;
      if (response.generation_state === "validated") {
        if (
          !response.generation_token ||
          !response.manifest_sha256 ||
          !response.manifest
        )
          throw new Error("Manifestul generației validate este incomplet.");
        setPendingSalesGeneration(response);
        setSalesOverrideReason("");
        setMessageType("warning");
        setMessage(
          `Generația ${response.import_month} a fost validată; datele live nu s-au schimbat. Verifică manifestul și promovează explicit.`,
        );
        setFile(null);
        setSalesReplaceConfirmed(false);
        return;
      }
      await refreshHistory().catch(() => undefined);
      onImportCompleted(response.import_month);
      setErpReconciliationMonth(response.import_month);
      const parts = [
        `Import ${response.import_month}: ${response.rows_imported} rânduri importate`,
      ];
      if (response.rows_filtered > 0)
        parts.push(`${response.rows_filtered} rânduri non-ASM filtrate`);
      if (response.coverage_report.active_store_coverage_pct != null)
        parts.push(
          `coverage magazine active ${response.coverage_report.active_store_coverage_pct}%`,
        );
      if ((response.coverage_report.missing_active_store_count ?? 0) > 0)
        parts.push(
          `${response.coverage_report.missing_active_store_count} magazine active absente, fără schimbare de stare`,
        );
      parts.push(
        response.is_month_final
          ? "Luna a fost marcată ca FINALĂ"
          : "Import intermediar (lună în curs)",
      );
      setMessage(parts.join(" · "));
      setFile(null);
      setSalesReplaceConfirmed(false);
    } catch (error) {
      if (
        !uploadAccepted &&
        !(error instanceof ApiError && error.status < 500)
      ) {
        setMessageType("warning");
        setMessage(
          "Conexiunea s-a întrerupt înainte de confirmare. Fișierul poate fi deja în procesare; reîncarcă pagina și verifică istoricul înainte de a retrimite.",
        );
        return;
      }
      const detail = error instanceof Error ? error.message : "";
      setMessage(
        detail && !detail.startsWith("API error")
          ? `Importul a eșuat: ${detail}`
          : "Importul a eșuat. Verifică fișierul și încearcă din nou.",
      );
      setMessageType("error");
    } finally {
      setUploading(false);
    }
  };

  const handleSalesPromotion = async () => {
    const pending = pendingSalesGeneration;
    if (
      !pending?.generation_token ||
      !pending.manifest_sha256 ||
      !pending.manifest
    )
      return;
    const hasBlockingAnomaly = pending.manifest.anomalies.some(
      (item) => item.blocking,
    );
    if (hasBlockingAnomaly && salesOverrideReason.trim().length < 10) {
      setMessageType("error");
      setMessage(
        "Anomaliile blocante necesită un motiv explicit de minimum 10 caractere.",
      );
      return;
    }
    try {
      setPromotingSales(true);
      setMessageType("success");
      setMessage("Promovarea generației rulează în worker.");
      const initialJob = await promoteSalesGeneration(
        pending.snapshot_id,
        pending.generation_token,
        pending.manifest_sha256,
        hasBlockingAnomaly ? salesOverrideReason.trim() : undefined,
      );
      const outcome = await pollImportJob(initialJob, POLL_OPTIONS);
      if (outcome.kind === "unconfirmed") {
        setMessageType("warning");
        setMessage(
          "Promovarea nu poate fi confirmată momentan; verifică istoricul înainte de retry.",
        );
        return;
      }
      if (
        outcome.job.error ||
        !outcome.job.result ||
        outcome.job.result.generation_state !== "promoted"
      )
        throw new Error(
          outcome.job.error ||
            "Promovarea nu are un rezultat terminal verificat.",
        );
      const response = outcome.job.result;
      await refreshHistory().catch(() => undefined);
      onImportCompleted(response.import_month);
      setErpReconciliationMonth(response.import_month);
      setPendingSalesGeneration(null);
      setSalesOverrideReason("");
      setMessageType("success");
      setMessage(
        `Import ${response.import_month} promovat: ${response.rows_imported} rânduri · hash business ${response.manifest?.business_sha256?.slice(0, 12) ?? "indisponibil"}.`,
      );
    } catch (error) {
      setMessageType("error");
      setMessage(
        presenters.formatExportError(
          error,
          "Promovarea generației de vânzări a eșuat.",
        ),
      );
    } finally {
      setPromotingSales(false);
    }
  };

  const handlePromoActualsUpload = async () => {
    if (!promoActualsFile) return;
    try {
      setPromoActualsUploading(true);
      setPromoActualsMessage("");
      const initialJob = await uploadPromoActualsFile(
        promoActualsFile,
        promoActualsMonth,
        promoActualsCutoff,
      );
      const outcome = await pollImportJob(initialJob, POLL_OPTIONS);
      if (outcome.kind === "unconfirmed") {
        setPromoActualsMessage(
          "Importul promo continuă în worker, dar statusul nu poate fi confirmat momentan. Nu retrimite fișierul; încearcă din nou verificarea mai târziu.",
        );
        return;
      }
      if (outcome.job.error || !outcome.job.promo_result) {
        throw new Error(outcome.job.error || "Workerul promo nu a returnat un rezultat verificat.");
      }
      const result = outcome.job.promo_result;
      setPromoActualsMessage(
        `Raport aplicat: ${result.promo_units.toLocaleString("ro-RO")} unități promo, cutoff ${result.cutoff_date}, ${result.updated_promotions} promoții actualizate. Generație ${result.generation_id.slice(0, 12)}.`,
      );
      setPromoActualsFile(null);
    } catch (error) {
      setPromoActualsMessage(
        presenters.formatExportError(
          error,
          "Importul raportului promo a eșuat.",
        ),
      );
    } finally {
      setPromoActualsUploading(false);
    }
  };

  const handleErpReconciliation = async () => {
    if (!erpReconciliationFile) return;
    try {
      setErpReconciliationBusy(true);
      setErpReconciliationError("");
      setErpReconciliationResult(null);
      const initialJob = await uploadErpReconciliationFile(
        erpReconciliationFile,
        erpReconciliationMonth,
      );
      const outcome = await pollImportJob(initialJob, POLL_OPTIONS);
      if (outcome.kind === "unconfirmed") {
        setErpReconciliationError(
          "Reconcilierea continuă în worker, dar statusul nu poate fi confirmat momentan. Nu retrimite raportul.",
        );
        return;
      }
      if (outcome.job.error || !outcome.job.erp_result) {
        throw new Error(outcome.job.error || "Workerul ERP nu a returnat un rezultat verificat.");
      }
      setErpReconciliationResult(outcome.job.erp_result);
    } catch (error) {
      setErpReconciliationError(
        presenters.formatExportError(
          error,
          "Verificarea raportului ERP a eșuat.",
        ),
      );
    } finally {
      setErpReconciliationBusy(false);
    }
  };

  return {
    history,
    file,
    setFile,
    salesReplaceConfirmed,
    setSalesReplaceConfirmed,
    salesCutoff,
    setSalesCutoff,
    pendingSalesGeneration,
    setPendingSalesGeneration,
    salesOverrideReason,
    setSalesOverrideReason,
    uploading,
    promotingSales,
    message,
    messageType,
    handleUpload,
    handleSalesPromotion,
    erpReconciliationMonths,
    erpReconciliationMonth,
    setErpReconciliationMonth,
    erpReconciliationFile,
    setErpReconciliationFile,
    erpReconciliationBusy,
    erpReconciliationError,
    erpReconciliationResult,
    setErpReconciliationError,
    setErpReconciliationResult,
    handleErpReconciliation,
    promoActualsFile,
    setPromoActualsFile,
    promoActualsMonth,
    setPromoActualsMonth,
    promoActualsCutoff,
    setPromoActualsCutoff,
    promoActualsUploading,
    promoActualsMessage,
    handlePromoActualsUpload,
  };
}
