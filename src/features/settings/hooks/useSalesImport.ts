import { useState } from "react";

import { promoteSalesGeneration, uploadSalesFile } from "../../../api/imports";
import type { ImportResponse } from "../../../api/generated/runtime-types";
import { ApiError } from "../../../api/client";
import { pollImportJob } from "../../../lib/importJobPolling";
import { formatIsoDateInput, shiftIsoDate } from "../../../lib/dates";
import * as presenters from "../presenters";
import { IMPORT_POLL_OPTIONS } from "./importFlowShared";

type SharedActions = {
  refreshHistory: () => Promise<void>;
  onImportCompleted: (month: string) => void;
  setErpReconciliationMonth: (month: string) => void;
};
type SalesMessages = {
  setMessage: (message: string) => void;
  setMessageType: (type: "success" | "warning" | "error") => void;
};

const yesterday = () => shiftIsoDate(formatIsoDateInput(), -1);

function useSalesValidation(actions: SharedActions, messages: SalesMessages) {
  const [file, setFile] = useState<File | null>(null);
  const [salesReplaceConfirmed, setSalesReplaceConfirmed] = useState(false);
  const [salesCutoff, setSalesCutoff] = useState(yesterday);
  const [pendingSalesGeneration, setPendingSalesGeneration] = useState<ImportResponse | null>(null);
  const [salesOverrideReason, setSalesOverrideReason] = useState("");
  const [uploading, setUploading] = useState(false);
  const handleUpload = async () => {
    if (!file || !salesReplaceConfirmed) return;
    let uploadAccepted = false;
    try {
      setUploading(true); messages.setMessage(""); messages.setMessageType("success");
      const initialJob = await uploadSalesFile(file, salesCutoff);
      uploadAccepted = true;
      messages.setMessage("Fișier încărcat. Importul rulează în worker.");
      const outcome = await pollImportJob(initialJob, {
        ...IMPORT_POLL_OPTIONS,
        onConnectionIssue: () => {
          messages.setMessageType("warning");
          messages.setMessage("Conexiune întreruptă temporar. Importul continuă în worker; reconectez automat.");
        },
        onConnectionRestored: () => {
          messages.setMessageType("success");
          messages.setMessage("Conexiune restabilită. Importul rulează în worker.");
        },
      });
      if (outcome.kind === "unconfirmed") {
        messages.setMessageType("warning");
        messages.setMessage("Fișierul a fost încărcat, dar statusul final nu poate fi confirmat momentan. Importul poate continua în worker; reîncarcă pagina și verifică istoricul înainte de a retrimite fișierul.");
        return;
      }
      const job = outcome.job;
      if (job.error || !job.result) {
        if (job.error) throw new Error(job.error);
        messages.setMessageType("warning");
        messages.setMessage("Workerul a încheiat jobul, dar rezultatul nu poate fi confirmat. Verifică istoricul importurilor.");
        return;
      }
      const response = job.result;
      if (response.generation_state === "validated") {
        if (!response.generation_token || !response.manifest_sha256 || !response.manifest) {
          throw new Error("Manifestul generației validate este incomplet.");
        }
        setPendingSalesGeneration(response); setSalesOverrideReason("");
        messages.setMessageType("warning");
        messages.setMessage(`Generația ${response.import_month} a fost validată; datele live nu s-au schimbat. Verifică manifestul și promovează explicit.`);
        setFile(null); setSalesReplaceConfirmed(false); return;
      }
      await actions.refreshHistory().catch(() => undefined);
      actions.onImportCompleted(response.import_month);
      actions.setErpReconciliationMonth(response.import_month);
      const parts = [`Import ${response.import_month}: ${response.rows_imported} rânduri importate`];
      if (response.rows_filtered > 0) parts.push(`${response.rows_filtered} rânduri non-ASM filtrate`);
      if (response.coverage_report.active_store_coverage_pct != null) parts.push(`coverage magazine active ${response.coverage_report.active_store_coverage_pct}%`);
      if ((response.coverage_report.missing_active_store_count ?? 0) > 0) parts.push(`${response.coverage_report.missing_active_store_count} magazine active absente, fără schimbare de stare`);
      parts.push(response.is_month_final ? "Luna a fost marcată ca FINALĂ" : "Import intermediar (lună în curs)");
      messages.setMessage(parts.join(" · ")); setFile(null); setSalesReplaceConfirmed(false);
    } catch (error) {
      if (!uploadAccepted && !(error instanceof ApiError && error.status < 500)) {
        messages.setMessageType("warning");
        messages.setMessage("Conexiunea s-a întrerupt înainte de confirmare. Fișierul poate fi deja în procesare; reîncarcă pagina și verifică istoricul înainte de a retrimite.");
        return;
      }
      const detail = error instanceof Error ? error.message : "";
      messages.setMessage(detail && !detail.startsWith("API error") ? `Importul a eșuat: ${detail}` : "Importul a eșuat. Verifică fișierul și încearcă din nou.");
      messages.setMessageType("error");
    } finally { setUploading(false); }
  };
  return {
    file, setFile, salesReplaceConfirmed, setSalesReplaceConfirmed, salesCutoff,
    setSalesCutoff, pendingSalesGeneration, setPendingSalesGeneration,
    salesOverrideReason, setSalesOverrideReason, uploading, handleUpload,
  };
}

function useSalesPromotion(
  sales: ReturnType<typeof useSalesValidation>,
  actions: SharedActions,
  messages: SalesMessages,
) {
  const [promotingSales, setPromotingSales] = useState(false);
  const handleSalesPromotion = async () => {
    const pending = sales.pendingSalesGeneration;
    if (!pending?.generation_token || !pending.manifest_sha256 || !pending.manifest) return;
    const hasBlockingAnomaly = pending.manifest.anomalies.some((item) => item.blocking);
    if (hasBlockingAnomaly && sales.salesOverrideReason.trim().length < 10) {
      messages.setMessageType("error");
      messages.setMessage("Anomaliile blocante necesită un motiv explicit de minimum 10 caractere.");
      return;
    }
    try {
      setPromotingSales(true); messages.setMessageType("success");
      messages.setMessage("Promovarea generației rulează în worker.");
      const initialJob = await promoteSalesGeneration(
        pending.snapshot_id, pending.generation_token, pending.manifest_sha256,
        hasBlockingAnomaly ? sales.salesOverrideReason.trim() : undefined,
      );
      const outcome = await pollImportJob(initialJob, IMPORT_POLL_OPTIONS);
      if (outcome.kind === "unconfirmed") {
        messages.setMessageType("warning");
        messages.setMessage("Promovarea nu poate fi confirmată momentan; verifică istoricul înainte de retry.");
        return;
      }
      if (outcome.job.error || !outcome.job.result || outcome.job.result.generation_state !== "promoted") {
        throw new Error(outcome.job.error || "Promovarea nu are un rezultat terminal verificat.");
      }
      const response = outcome.job.result;
      await actions.refreshHistory().catch(() => undefined);
      actions.onImportCompleted(response.import_month);
      actions.setErpReconciliationMonth(response.import_month);
      sales.setPendingSalesGeneration(null); sales.setSalesOverrideReason("");
      messages.setMessageType("success");
      messages.setMessage(`Import ${response.import_month} promovat: ${response.rows_imported} rânduri · hash business ${response.manifest?.business_sha256?.slice(0, 12) ?? "indisponibil"}.`);
    } catch (error) {
      messages.setMessageType("error");
      messages.setMessage(presenters.formatExportError(error, "Promovarea generației de vânzări a eșuat."));
    } finally { setPromotingSales(false); }
  };
  return { promotingSales, handleSalesPromotion };
}

export function useSalesImport(actions: SharedActions) {
  const [message, setMessage] = useState("");
  const [messageType, setMessageType] = useState<"success" | "warning" | "error">("success");
  const messages = { setMessage, setMessageType };
  const validation = useSalesValidation(actions, messages);
  const promotion = useSalesPromotion(validation, actions, messages);
  return { ...validation, ...promotion, message, messageType, setMessage, setMessageType };
}

