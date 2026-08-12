import { useState } from "react";

import {
  uploadErpReconciliationFile,
  uploadPromoActualsFile,
} from "../../../api/imports";
import type { ErpReconciliationResponse } from "../../../api/imports";
import { pollImportJob } from "../../../lib/importJobPolling";
import {
  formatIsoDateInput,
  getCurrentYearMonth,
  shiftIsoDate,
} from "../../../lib/dates";
import * as presenters from "../presenters";
import { IMPORT_POLL_OPTIONS } from "./importFlowShared";

const yesterday = () => shiftIsoDate(formatIsoDateInput(), -1);

export function usePromoActualsImport() {
  const [promoActualsFile, setPromoActualsFile] = useState<File | null>(null);
  const [promoActualsMonth, setPromoActualsMonth] = useState(getCurrentYearMonth);
  const [promoActualsCutoff, setPromoActualsCutoff] = useState(yesterday);
  const [promoActualsUploading, setPromoActualsUploading] = useState(false);
  const [promoActualsMessage, setPromoActualsMessage] = useState("");
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
      const outcome = await pollImportJob(initialJob, IMPORT_POLL_OPTIONS);
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
        presenters.formatExportError(error, "Importul raportului promo a eșuat."),
      );
    } finally {
      setPromoActualsUploading(false);
    }
  };
  return {
    promoActualsFile, setPromoActualsFile, promoActualsMonth, setPromoActualsMonth,
    promoActualsCutoff, setPromoActualsCutoff, promoActualsUploading,
    promoActualsMessage, handlePromoActualsUpload,
  };
}

export function useErpReconciliationImport() {
  const [erpReconciliationFile, setErpReconciliationFile] = useState<File | null>(null);
  const [erpReconciliationMonth, setErpReconciliationMonth] = useState("");
  const [erpReconciliationBusy, setErpReconciliationBusy] = useState(false);
  const [erpReconciliationError, setErpReconciliationError] = useState("");
  const [erpReconciliationResult, setErpReconciliationResult] =
    useState<ErpReconciliationResponse | null>(null);
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
      const outcome = await pollImportJob(initialJob, IMPORT_POLL_OPTIONS);
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
        presenters.formatExportError(error, "Verificarea raportului ERP a eșuat."),
      );
    } finally {
      setErpReconciliationBusy(false);
    }
  };
  return {
    erpReconciliationMonth, setErpReconciliationMonth,
    erpReconciliationFile, setErpReconciliationFile,
    erpReconciliationBusy, erpReconciliationError, setErpReconciliationError,
    erpReconciliationResult, setErpReconciliationResult, handleErpReconciliation,
  };
}

