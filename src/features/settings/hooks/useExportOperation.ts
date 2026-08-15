import { useCallback, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import {
  cancelExportOperation,
  createExportOperation,
  downloadExport,
  downloadExportOperation,
  getExportOperation,
  getResumableExportOperation,
  previewExport,
  uncertainExportOperationId,
} from "../../../api/exports";
import type { ExportOperation, ExportPreview, ExportRequest } from "../../../api/exports";
import { downloadBlob } from "../../../lib/download";
import { pollExportOperation } from "../../../lib/exportOperationPolling";
import { queryKeys } from "../../../lib/queryKeys";
import * as presenters from "../presenters";
import {
  clearStoredExportOperationId,
  readStoredExportOperationId,
  storeExportOperationId,
} from "./exportOperationStorage";

const POLL_OPTIONS = { intervalMs: 1_500, maxAttempts: 1_200, maxConsecutiveErrors: 20 };

function useExportRuntime(identityKey: string) {
  const queryClient = useQueryClient();
  const [exportMessage, setExportMessage] = useState("");
  const [exportOperation, setExportOperation] = useState<ExportOperation | null>(null);
  const [exportBusy, setExportBusy] = useState(false);
  const [exportCancelling, setExportCancelling] = useState(false);
  const controllerRef = useRef<AbortController | null>(null);
  const follow = useCallback(async (initial: ExportOperation, controller: AbortController) => {
    setExportOperation(initial);
    const outcome = await pollExportOperation(
      initial,
      async (operationId, signal) => queryClient.fetchQuery({
        queryKey: queryKeys.settings.exportOperation(identityKey, operationId),
        queryFn: () => getExportOperation(operationId, signal), staleTime: 0,
      }),
      { ...POLL_OPTIONS, signal: controller.signal, onUpdate: setExportOperation },
    );
    if (outcome.kind === "aborted") return;
    setExportOperation(outcome.operation);
    if (outcome.kind === "unconfirmed") {
      setExportMessage(`Exportul #${initial.id} continuă în worker, dar statusul nu poate fi confirmat. Nu retrimite cererea.`);
      return;
    }
    if (outcome.operation.status !== "completed" || !outcome.operation.can_download) {
      clearStoredExportOperationId(identityKey);
      throw new Error(`Exportul #${initial.id} s-a încheiat cu status ${outcome.operation.status}.`);
    }
    downloadBlob(await downloadExportOperation(initial.id, controller.signal), outcome.operation.filename || "export_retail.xlsx");
    clearStoredExportOperationId(identityKey);
    void queryClient.removeQueries({ queryKey: queryKeys.settings.exportOperation(identityKey, initial.id), exact: true });
  }, [identityKey, queryClient]);
  useEffect(() => () => { controllerRef.current?.abort(); controllerRef.current = null; }, []);
  return {
    queryClient, exportMessage, setExportMessage, exportOperation,
    setExportOperation, exportBusy, setExportBusy, exportCancelling,
    setExportCancelling, controllerRef, follow,
  };
}

function useExportRecovery(
  enabled: boolean,
  authorized: boolean,
  identityKey: string,
  runtime: ReturnType<typeof useExportRuntime>,
) {
  const { controllerRef, follow, queryClient, setExportBusy, setExportMessage, setExportOperation } = runtime;
  useEffect(() => {
    if (!enabled || !authorized) return;
    const controller = new AbortController();
    controllerRef.current = controller; setExportBusy(true);
    void (async () => {
      try {
        const storedId = readStoredExportOperationId(identityKey);
        let resumable: ExportOperation | null = null;
        if (storedId !== null) {
          try {
            resumable = await queryClient.fetchQuery({
              queryKey: queryKeys.settings.exportOperation(identityKey, storedId),
              queryFn: () => getExportOperation(storedId, controller.signal), staleTime: 0,
            });
            if (resumable && ["failed", "cancelled", "expired"].includes(resumable.status)) {
              clearStoredExportOperationId(identityKey); setExportOperation(resumable); return;
            }
          } catch (error) {
            if (!controller.signal.aborted) setExportMessage(presenters.formatExportError(error, `Statusul exportului #${storedId} nu poate fi confirmat. ID-ul a fost păstrat pentru retry.`));
            return;
          }
        } else {
          resumable = await queryClient.fetchQuery({
            queryKey: queryKeys.settings.exportResumable(identityKey),
            queryFn: () => getResumableExportOperation(controller.signal), staleTime: 0,
          });
          if (resumable) storeExportOperationId(identityKey, resumable.id);
        }
        if (resumable && !controller.signal.aborted) await follow(resumable, controller);
      } catch (error) {
        if (!controller.signal.aborted) setExportMessage(presenters.formatExportError(error, "Statusul exportului activ nu a putut fi verificat."));
      } finally {
        if (controllerRef.current === controller) { controllerRef.current = null; setExportBusy(false); }
      }
    })();
    return () => { controller.abort(); if (controllerRef.current === controller) controllerRef.current = null; };
  }, [authorized, controllerRef, enabled, follow, identityKey, queryClient, setExportBusy, setExportMessage, setExportOperation]);
}

function useExportExecution(
  identityKey: string,
  request: ExportRequest,
  setPreview: (preview: ExportPreview | null) => void,
  runtime: ReturnType<typeof useExportRuntime>,
) {
  const { controllerRef, follow, queryClient, setExportBusy, setExportMessage, setExportOperation } = runtime;
  const handlePreviewExport = async () => {
    try { setExportBusy(true); setExportMessage(""); setPreview(await previewExport(request)); }
    catch (error) { setExportMessage(presenters.formatExportError(error, "Preview-ul nu a putut fi generat. Verifica selectia.")); }
    finally { setExportBusy(false); }
  };
  const handleDownloadExport = async () => {
    const controller = new AbortController();
    try {
      setExportBusy(true); setExportMessage(""); setExportOperation(null);
      const complex = request.export_mode === "daily_comparison" || (request.daily_metrics?.length ?? 0) > 0;
      if (complex) {
        controllerRef.current?.abort(); controllerRef.current = controller;
        let initial: ExportOperation;
        try {
          initial = await createExportOperation(request);
          storeExportOperationId(identityKey, initial.id);
        } catch (error) {
          const operationId = uncertainExportOperationId(error);
          if (operationId === null) throw error;
          storeExportOperationId(identityKey, operationId);
          try {
            initial = await queryClient.fetchQuery({
              queryKey: queryKeys.settings.exportOperation(identityKey, operationId),
              queryFn: () => getExportOperation(operationId, controller.signal), staleTime: 0,
            });
          } catch {
            setExportMessage(`Exportul #${operationId} a fost rezervat, dar publicarea și statusul nu pot fi confirmate. Nu retrimite cererea.`);
            return;
          }
        }
        await follow(initial, controller); return;
      }
      downloadBlob(await downloadExport(request), `${request.filename || "export_retail"}.xlsx`);
    } catch (error) {
      setExportMessage(presenters.formatExportError(error, "Exportul nu a putut fi generat. Verifica selectia."));
    } finally {
      if (controllerRef.current === controller) controllerRef.current = null;
      if (!controller.signal.aborted || controllerRef.current === null) setExportBusy(false);
    }
  };
  return { handlePreviewExport, handleDownloadExport };
}

function useExportTermination(identityKey: string, runtime: ReturnType<typeof useExportRuntime>) {
  const { controllerRef, exportOperation, follow, setExportBusy, setExportCancelling, setExportMessage, setExportOperation } = runtime;
  const handleCancelExport = async () => {
    const operation = exportOperation;
    if (!operation || !["queued", "running"].includes(operation.status)) return;
    setExportCancelling(true); setExportMessage(""); controllerRef.current?.abort(); controllerRef.current = null;
    try {
      const cancelled = await cancelExportOperation(operation.id); setExportOperation(cancelled);
      if (cancelled.status === "cancelled") clearStoredExportOperationId(identityKey);
      setExportMessage(cancelled.status === "cancelled" ? `Exportul #${operation.id} a fost anulat.` : `Exportul #${operation.id} nu mai poate fi anulat; status ${cancelled.status}.`);
    } catch (error) { setExportMessage(presenters.formatExportError(error, "Exportul nu a putut fi anulat.")); }
    finally { setExportCancelling(false); setExportBusy(false); }
  };
  const handleRetryExportDownload = async () => {
    const operation = exportOperation;
    if (!operation || operation.status !== "completed" || !operation.can_download) return;
    const controller = new AbortController();
    controllerRef.current?.abort(); controllerRef.current = controller;
    storeExportOperationId(identityKey, operation.id); setExportBusy(true); setExportMessage("");
    try { await follow(operation, controller); }
    catch (error) {
      if (!controller.signal.aborted) setExportMessage(presenters.formatExportError(error, `Descărcarea exportului #${operation.id} a eșuat. Poți reîncerca până la expirare.`));
    } finally {
      if (controllerRef.current === controller) controllerRef.current = null;
      setExportBusy(false);
    }
  };
  return { handleCancelExport, handleRetryExportDownload };
}

export function useExportOperation(
  enabled: boolean,
  authorized: boolean,
  identityKey: string,
  request: ExportRequest,
  setPreview: (preview: ExportPreview | null) => void,
) {
  const runtime = useExportRuntime(identityKey);
  useExportRecovery(enabled, authorized, identityKey, runtime);
  const execution = useExportExecution(identityKey, request, setPreview, runtime);
  const termination = useExportTermination(identityKey, runtime);
  return {
    exportMessage: runtime.exportMessage,
    exportOperation: runtime.exportOperation,
    exportBusy: runtime.exportBusy,
    exportCancelling: runtime.exportCancelling,
    ...execution,
    ...termination,
  };
}
