import React, { useEffect, useRef, useState } from 'react';
import { RefreshCw, X } from 'lucide-react';
import { fetchSalaryAgentHistory } from '../api/salarii';
import type { SalaryAgentHistory } from '../api/salarii';
import { SalaryAgentBarChart } from './SalaryAgentBarChart';

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

export function SalaryDrawer({ personId, fullName, isOpen, onClose }: Props) {
  const [history, setHistory] = useState<SalaryAgentHistory | null>(null);
  const [loading, setLoading] = useState(false);
  const overlayRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isOpen || !personId) return;
    let active = true;
    setLoading(true);
    setHistory(null);
    fetchSalaryAgentHistory(personId)
      .then((h) => { if (active) setHistory(h); })
      .catch(() => { if (active) setHistory(null); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [isOpen, personId]);

  function handleOverlayClick(e: React.MouseEvent) {
    if (e.target === overlayRef.current) onClose();
  }

  if (!isOpen) return null;

  const companyColor = (company?: string) =>
    company === 'Mobicell' ? 'text-indigo-500' : 'text-emerald-500';

  return (
    <div
      ref={overlayRef}
      onClick={handleOverlayClick}
      className="fixed inset-0 z-50 flex justify-end bg-black/30 backdrop-blur-sm transition-opacity"
    >
      <div className="animate-slide-in-right flex h-full w-full max-w-md flex-col bg-white/95 dark:bg-slate-900/95 shadow-2xl">
        {/* Header */}
        <div className="flex items-start justify-between border-b border-slate-200 px-6 py-5 dark:border-slate-700">
          <div>
            <h2 className="text-lg font-bold text-slate-800 dark:text-white">{fullName}</h2>
            {history && (
              <p className="mt-1 text-sm text-slate-500">
                Istoric salarial &bull;{' '}
                <span className={companyColor(history.records[0]?.company_name)}>
                  {history.records[0]?.company_name}
                </span>
                {history.records[0]?.locatie && ` \u2022 ${history.records[0].locatie}`}
              </p>
            )}
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-slate-800"
          >
            <X size={20} />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto px-6 py-5">
          {loading && (
            <div className="flex items-center justify-center py-16">
              <RefreshCw size={24} className="animate-spin text-indigo-500" />
            </div>
          )}

          {!loading && history && (
            <div className="space-y-6">
              {/* Stat row */}
              <div className="grid grid-cols-3 gap-3">
                <div className="glass rounded-2xl p-3 text-center">
                  <div className="text-xs font-medium text-slate-500">Total</div>
                  <div className="mt-1 text-sm font-bold text-slate-800 dark:text-white">
                    {formatCurrency(history.total)} RON
                  </div>
                </div>
                <div className="glass rounded-2xl p-3 text-center">
                  <div className="text-xs font-medium text-slate-500">Luni</div>
                  <div className="mt-1 text-sm font-bold text-slate-800 dark:text-white">
                    {history.month_count}
                  </div>
                </div>
                <div className="glass rounded-2xl p-3 text-center">
                  <div className="text-xs font-medium text-slate-500">Medie</div>
                  <div className="mt-1 text-sm font-bold text-slate-800 dark:text-white">
                    {formatCurrency(history.avg)} RON
                  </div>
                  <div className="mt-1 text-[10px] text-slate-400">
                    {history.avg_month_count}/{history.month_count} luni ≥ 2.000 RON
                  </div>
                </div>
              </div>

              {/* Bar chart */}
              <div>
                <h3 className="mb-3 text-sm font-semibold text-slate-600 dark:text-slate-300">
                  Evoluție Lunară
                </h3>
                <SalaryAgentBarChart data={history.records} />
              </div>

              {/* Monthly table */}
              <div>
                <h3 className="mb-3 text-sm font-semibold text-slate-600 dark:text-slate-300">
                  Detalii Lunare
                </h3>
                <div className="overflow-hidden rounded-2xl border border-slate-200 dark:border-slate-700">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="bg-slate-50 dark:bg-slate-800">
                        <th className="px-3 py-2 text-left text-xs font-semibold text-slate-500">Luna</th>
                        <th className="px-3 py-2 text-left text-xs font-semibold text-slate-500">Companie</th>
                        <th className="px-3 py-2 text-left text-xs font-semibold text-slate-500">Locatie</th>
                        <th className="px-3 py-2 text-right text-xs font-semibold text-slate-500">Salariu</th>
                      </tr>
                    </thead>
                    <tbody>
                      {history.records.map((r, i) => (
                        <tr
                          key={i}
                          className="border-t border-slate-100 dark:border-slate-800 dark:text-slate-700"
                        >
                          <td className="px-3 py-2 text-slate-700 dark:text-slate-300">
                            {formatMonth(r.year, r.month)}
                          </td>
                          <td className={`px-3 py-2 font-medium ${companyColor(r.company_name)}`}>
                            {r.company_name}
                          </td>
                          <td className="px-3 py-2 text-slate-500">
                            {r.locatie || '-'}
                          </td>
                          <td className="px-3 py-2 text-right font-semibold text-slate-800 dark:text-white">
                            {formatCurrency(r.total_salary)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}

          {!loading && !history && (
            <div className="flex flex-col items-center justify-center py-16 gap-3">
              <p className="text-slate-500">Nu s-au putut încărca datele</p>
              <button
                onClick={() => fetchSalaryAgentHistory(personId).then(setHistory).catch(() => setHistory(null))}
                className="rounded-lg bg-indigo-500 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-600"
              >
                Retry
              </button>
            </div>
          )}
        </div>
      </div>

    </div>
  );
}
