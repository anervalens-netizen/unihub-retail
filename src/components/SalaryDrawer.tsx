import React, { useCallback, useEffect, useRef, useState } from 'react';
import { RefreshCw, X } from 'lucide-react';
import { fetchSalaryAgentHistory } from '../api/salarii';
import type { SalaryAgentHistory } from '../api/salarii';
import { SalaryAgentBarChart } from './SalaryAgentBarChart';
import { TableHeaderCell } from './common/TableHeader';

interface Props {
  personId: string;
  fullName: string;
  isOpen: boolean;
  onClose: () => void;
}

function formatMonth(year: number, month: number): string {
  const months = ['Ian', 'Feb', 'Mar', 'Apr', 'Mai', 'Iun', 'Iul', 'Aug', 'Sep', 'Oct', 'Noi', 'Dec'];
  return `${months[month - 1]} ${year}`;
}

function formatCurrency(value: number): string {
  return value.toLocaleString('ro-RO');
}

function companyColor(company?: string): string {
  return company === 'Mobicell' ? 'text-indigo-500' : 'text-emerald-500';
}

type SalaryDrawerHeaderProps = Pick<Props, 'fullName' | 'onClose'> & {
  history: SalaryAgentHistory | null;
  closeButtonRef: React.RefObject<HTMLButtonElement | null>;
};

function SalaryDrawerHeader({ fullName, history, onClose, closeButtonRef }: SalaryDrawerHeaderProps) {
  const latest = history?.records[0];
  return (
    <div className="flex items-start justify-between border-b border-slate-200 px-6 py-5 dark:border-slate-700">
      <div>
        <h2 id="salary-drawer-title" className="text-lg font-bold text-slate-800 dark:text-white">{fullName}</h2>
        {history && (
          <p className="mt-1 text-sm text-slate-500">Istoric salarial &bull; <span className={companyColor(latest?.company_name)}>{latest?.company_name}</span>{latest?.locatie && ` \u2022 ${latest.locatie}`}</p>
        )}
      </div>
      <button ref={closeButtonRef} type="button" onClick={onClose} className="rounded-lg p-1.5 text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-slate-800" aria-label="Închide istoricul salarial"><X size={20} aria-hidden="true" /></button>
    </div>
  );
}

function SalaryHistorySummary({ history }: { history: SalaryAgentHistory }) {
  return (
    <div className="grid grid-cols-3 gap-3">
      <div className="glass rounded-2xl p-3 text-center"><div className="text-xs font-medium text-slate-500">Total</div><div className="mt-1 text-sm font-bold text-slate-800 dark:text-white">{formatCurrency(history.total)} RON</div></div>
      <div className="glass rounded-2xl p-3 text-center"><div className="text-xs font-medium text-slate-500">Luni</div><div className="mt-1 text-sm font-bold text-slate-800 dark:text-white">{history.month_count}</div></div>
      <div className="glass rounded-2xl p-3 text-center">
        <div className="text-xs font-medium text-slate-500">Medie</div><div className="mt-1 text-sm font-bold text-slate-800 dark:text-white">{formatCurrency(history.avg)} RON</div>
        <div className="mt-1 text-[10px] text-slate-400">{history.avg_month_count}/{history.month_count} luni ≥ 2.000 RON</div>
      </div>
    </div>
  );
}

function SalaryHistoryTable({ history }: { history: SalaryAgentHistory }) {
  return (
    <div>
      <h3 className="mb-3 text-sm font-semibold text-slate-600 dark:text-slate-300">Detalii Lunare</h3>
      <div className="overflow-hidden rounded-2xl border border-slate-200 dark:border-slate-700">
        <table className="w-full text-sm">
          <thead><tr className="bg-slate-50 dark:bg-slate-800"><TableHeaderCell>Luna</TableHeaderCell><TableHeaderCell>Companie</TableHeaderCell><TableHeaderCell>Locație</TableHeaderCell><TableHeaderCell align="right">Salariu</TableHeaderCell></tr></thead>
          <tbody>{history.records.map((record, index) => (
            <tr key={index} className="border-t border-slate-100 dark:border-slate-800 dark:text-slate-700">
              <td className="px-3 py-2 text-slate-700 dark:text-slate-300">{formatMonth(record.year, record.month)}</td>
              <td className={`px-3 py-2 font-medium ${companyColor(record.company_name)}`}>{record.company_name}</td>
              <td className="px-3 py-2 text-slate-500">{record.locatie || '-'}</td>
              <td className="px-3 py-2 text-right font-semibold text-slate-800 dark:text-white">{formatCurrency(record.total_salary)}</td>
            </tr>
          ))}</tbody>
        </table>
      </div>
    </div>
  );
}

function SalaryHistoryContent({ history }: { history: SalaryAgentHistory }) {
  return (
    <div className="space-y-6">
      <SalaryHistorySummary history={history} />
      <div><h3 className="mb-3 text-sm font-semibold text-slate-600 dark:text-slate-300">Evoluție Lunară</h3><SalaryAgentBarChart data={history.records} /></div>
      <SalaryHistoryTable history={history} />
    </div>
  );
}

export function SalaryDrawer({ personId, fullName, isOpen, onClose }: Props) {
  const [history, setHistory] = useState<SalaryAgentHistory | null>(null);
  const [loading, setLoading] = useState(false);
  const overlayRef = useRef<HTMLDivElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);
  const requestGenerationRef = useRef(0);
  const requestControllerRef = useRef<AbortController | null>(null);
  const onCloseRef = useRef(onClose);

  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  const loadHistory = useCallback((requestedPersonId: string) => {
    requestControllerRef.current?.abort();
    const controller = new AbortController();
    requestControllerRef.current = controller;
    const generation = ++requestGenerationRef.current;
    setLoading(true);
    setHistory(null);
    fetchSalaryAgentHistory(requestedPersonId, controller.signal)
      .then((loadedHistory) => {
        if (generation === requestGenerationRef.current) setHistory(loadedHistory);
      })
      .catch(() => {
        if (generation === requestGenerationRef.current) setHistory(null);
      })
      .finally(() => {
        if (generation === requestGenerationRef.current) setLoading(false);
      });
  }, []);

  useEffect(() => {
    if (!isOpen || !personId) return;
    previousFocusRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        onCloseRef.current();
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    closeButtonRef.current?.focus();
    loadHistory(personId);
    return () => {
      requestGenerationRef.current += 1;
      requestControllerRef.current?.abort();
      requestControllerRef.current = null;
      document.removeEventListener('keydown', handleKeyDown);
      const previous = previousFocusRef.current;
      if (previous?.isConnected) previous.focus();
      previousFocusRef.current = null;
    };
  }, [isOpen, personId, loadHistory]);

  function handleOverlayClick(e: React.MouseEvent) {
    if (e.target === overlayRef.current) onClose();
  }

  if (!isOpen) return null;

  return (
    <div
      ref={overlayRef}
      onClick={handleOverlayClick}
      className="fixed inset-0 z-50 flex justify-end bg-black/30 backdrop-blur-sm transition-opacity"
    >
      <div
        className="animate-slide-in-right flex h-full w-full max-w-md flex-col bg-white/95 dark:bg-slate-900/95 shadow-2xl"
        role="dialog"
        aria-modal="true"
        aria-labelledby="salary-drawer-title"
        aria-busy={loading}
      >
        <SalaryDrawerHeader fullName={fullName} history={history} onClose={onClose} closeButtonRef={closeButtonRef} />
        <div className="flex-1 overflow-y-auto px-6 py-5">
          {loading && <div className="flex items-center justify-center py-16" role="status" aria-live="polite"><RefreshCw size={24} aria-hidden="true" className="animate-spin text-indigo-500" /><span className="sr-only">Se încarcă istoricul salarial</span></div>}
          {!loading && history && <SalaryHistoryContent history={history} />}
          {!loading && !history && <div className="flex flex-col items-center justify-center gap-3 py-16" role="alert"><p className="text-slate-500">Nu s-au putut încărca datele</p><button type="button" onClick={() => loadHistory(personId)} className="rounded-lg bg-indigo-500 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-600">Retry</button></div>}
        </div>
      </div>
    </div>
  );
}
