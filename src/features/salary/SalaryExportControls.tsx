import { useCallback, useEffect, useRef, useState } from 'react';
import { Download, RefreshCw } from 'lucide-react';

import {
  createSalaryExportOperation,
  uncertainSalaryExportOperationId,
} from '../../api/salarii';
import type { SalaryExportKind, SalaryExportRequest } from '../../api/salarii';
import {
  downloadExportOperation,
  getExportOperation,
  isExportOperationNotFound,
} from '../../api/exports';
import type { ExportOperation } from '../../api/exports';
import { downloadBlob } from '../../lib/download';
import { pollExportOperation } from '../../lib/exportOperationPolling';


const SALARY_EXPORT_OPERATION_KEY = 'unihub:salary-export-operation';
export type SalaryExportBusy = SalaryExportKind | 'resume' | null;


function readOperationId(): number | null {
  if (typeof window === 'undefined') return null;
  const value = Number(window.sessionStorage.getItem(SALARY_EXPORT_OPERATION_KEY));
  return Number.isInteger(value) && value > 0 ? value : null;
}


function storeOperationId(operationId: number | null): void {
  if (typeof window === 'undefined') return;
  if (operationId === null) window.sessionStorage.removeItem(SALARY_EXPORT_OPERATION_KEY);
  else window.sessionStorage.setItem(SALARY_EXPORT_OPERATION_KEY, String(operationId));
}


export function useSalaryExport() {
  const [busy, setBusy] = useState<SalaryExportBusy>(null);
  const [operationId, setOperationId] = useState<number | null>(readOperationId);
  const [message, setMessage] = useState('');
  const controllerRef = useRef<AbortController | null>(null);
  const clearOperation = useCallback(() => {
    storeOperationId(null);
    setOperationId(null);
  }, []);

  const followOperation = useCallback(async (
    initial: ExportOperation,
    controller: AbortController,
  ) => {
    const outcome = await pollExportOperation(initial, getExportOperation, {
      intervalMs: 1_250,
      maxAttempts: 1_440,
      maxConsecutiveErrors: 20,
      signal: controller.signal,
    });
    if (outcome.kind === 'aborted') return;
    if (outcome.kind === 'unconfirmed') {
      setMessage(
        `Exportul #${initial.id} continua in worker; statusul poate fi reluat fara retrimitere.`,
      );
      return;
    }
    if (outcome.operation.status !== 'completed' || !outcome.operation.can_download) {
      clearOperation();
      throw new Error(
        `Exportul #${initial.id} s-a incheiat cu status ${outcome.operation.status}.`,
      );
    }
    downloadBlob(
      await downloadExportOperation(initial.id, controller.signal),
      outcome.operation.filename || 'salarii.xlsx',
    );
    clearOperation();
    setMessage(
      `Export verificat: ${outcome.operation.row_count ?? 0} randuri, SHA-256 inregistrat.`,
    );
  }, [clearOperation]);

  const resume = useCallback(async (savedOperationId: number) => {
    if (controllerRef.current) return;
    const controller = new AbortController();
    controllerRef.current = controller;
    setBusy('resume');
    setMessage(`Verific exportul #${savedOperationId}...`);
    try {
      await followOperation(
        await getExportOperation(savedOperationId, controller.signal),
        controller,
      );
    } catch (error) {
      if (!controller.signal.aborted) {
        if (isExportOperationNotFound(error)) {
          clearOperation();
          setMessage(
            'Exportul salvat nu mai apartine sesiunii curente; referinta a fost eliminata.',
          );
        } else {
          setMessage(
            `Statusul exportului #${savedOperationId} nu poate fi confirmat. ID-ul a fost pastrat pentru retry.`,
          );
        }
      }
    } finally {
      if (controllerRef.current === controller) {
        controllerRef.current = null;
        setBusy(null);
      }
    }
  }, [clearOperation, followOperation]);

  const start = useCallback(async (request: SalaryExportRequest) => {
    if (controllerRef.current || operationId !== null) return;
    const controller = new AbortController();
    controllerRef.current = controller;
    setBusy(request.export_kind);
    setMessage('Exportul este rezervat si generat pe server...');
    try {
      let operation: ExportOperation;
      try {
        operation = await createSalaryExportOperation(request);
      } catch (error) {
        const uncertainId = uncertainSalaryExportOperationId(error);
        if (uncertainId === null) throw error;
        setOperationId(uncertainId);
        storeOperationId(uncertainId);
        operation = await getExportOperation(uncertainId, controller.signal);
      }
      setOperationId(operation.id);
      storeOperationId(operation.id);
      await followOperation(operation, controller);
    } catch {
      if (!controller.signal.aborted) {
        setMessage(
          'Exportul salarial nu a putut fi finalizat; cererea nu a fost retrimisa automat.',
        );
      }
    } finally {
      if (controllerRef.current === controller) {
        controllerRef.current = null;
        setBusy(null);
      }
    }
  }, [followOperation, operationId]);

  useEffect(() => {
    const savedOperationId = readOperationId();
    if (savedOperationId !== null) void resume(savedOperationId);
    return () => {
      controllerRef.current?.abort();
      controllerRef.current = null;
    };
  }, [resume]);

  return { busy, message, operationId, resume, start };
}


export function SalaryExportButton({
  busy,
  disabled,
  onExport,
}: {
  busy: boolean;
  disabled: boolean;
  onExport: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onExport}
      disabled={disabled}
      className="inline-flex shrink-0 items-center gap-1 rounded-lg border border-slate-200 bg-white px-2 py-1 text-[11px] font-bold text-slate-600 transition hover:border-indigo-200 hover:text-indigo-600 disabled:cursor-not-allowed disabled:opacity-40 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:border-indigo-800 dark:hover:text-indigo-300"
      title="Export Excel generat si verificat pe server"
    >
      {busy ? <RefreshCw size={12} className="animate-spin" /> : <Download size={12} />}
      {busy ? 'Generare...' : 'Excel'}
    </button>
  );
}


export function SalaryExportStatus({
  busy,
  message,
  operationId,
  onResume,
}: {
  busy: SalaryExportBusy;
  message: string;
  operationId: number | null;
  onResume: (operationId: number) => void;
}) {
  if (!message) return null;
  return (
    <div
      aria-live="polite"
      className="flex items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-white px-3 py-2 text-xs text-slate-600 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300"
    >
      <span>{message}</span>
      {operationId !== null && busy === null && (
        <button
          type="button"
          onClick={() => onResume(operationId)}
          className="shrink-0 rounded-lg border border-slate-200 px-2 py-1 font-bold hover:text-indigo-600 dark:border-slate-700"
        >
          Reia status
        </button>
      )}
    </div>
  );
}
