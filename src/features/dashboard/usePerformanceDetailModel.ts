import { useEffect, useMemo, useState } from 'react';

import type { PerformanceDetailResponse } from '../../api/generated/runtime-types';
import { fetchSalaryAgentHistoryByRetailCode, type SalaryAgentHistory } from '../../api/salarii';
import type { PerformanceSelection } from './PerformanceDetailDrawer';

export type MonthlyPerformanceMetric = 'sales' | 'bon2acc' | 'focus' | 'returns';

function daysInMonthFromKey(monthKey: string) {
  const [year, month] = monthKey.split('-').map(Number);
  if (!year || !month) return 31;
  return new Date(year, month, 0).getDate();
}

function useAgentSalaryHistory(
  open: boolean,
  canViewSalaries: boolean,
  detail: PerformanceDetailResponse | null,
  selection: PerformanceSelection | null,
) {
  const [history, setHistory] = useState<SalaryAgentHistory | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    if (!open || !canViewSalaries || detail?.level !== 'agent' || !selection?.site_code) {
      setHistory(null); setLoading(false); setError('');
      return undefined;
    }
    let cancelled = false;
    setLoading(true); setError(''); setHistory(null);
    fetchSalaryAgentHistoryByRetailCode({ agent_code: detail.key, site_code: selection.site_code })
      .then((data) => { if (!cancelled) setHistory(data); })
      .catch(() => { if (!cancelled) setError('Salariile nu au putut fi incarcate.'); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [canViewSalaries, detail?.key, detail?.level, open, selection?.site_code]);
  return { history, loading, error };
}

export function usePerformanceDetailModel({
  open, canViewSalaries, detail, selection,
}: {
  open: boolean;
  canViewSalaries: boolean;
  detail: PerformanceDetailResponse | null;
  selection: PerformanceSelection | null;
}) {
  const [monthlyMetric, setMonthlyMetric] = useState<MonthlyPerformanceMetric>('sales');
  const historyData = useMemo(() => (detail?.history ?? []).map((point) => ({
    month: point.month,
    sales: Number(point.month === detail?.month ? (detail.summary.forecast_sales ?? point.total_sales ?? 0) : (point.total_sales ?? 0)),
    target: Number(point.total_target ?? 0),
    targetPct: point.month === detail?.month
      ? (detail.summary.forecast_target_progress_pct ?? point.target_progress_pct ?? null)
      : (point.target_progress_pct ?? null),
    bon2acc: point.proc_bon2acc ?? null,
    focus: point.prc_focus_acc_qty ?? null,
    returns: Number(point.return_receipt_count ?? 0),
  })), [detail]);
  const dailyData = useMemo(() => {
    if (!detail) return [];
    const valuesByDay = new Map(detail.daily.map((point) => [Number(point.sale_date.slice(8, 10)), {
      sales: Number(point.total_sales ?? 0), qty: point.total_quantity ?? 0, receipts: point.receipt_count ?? 0,
    }]));
    const daysInMonth = detail.summary.days_in_month ?? daysInMonthFromKey(detail.month);
    return Array.from({ length: daysInMonth }, (_, index) => {
      const day = index + 1;
      const value = valuesByDay.get(day);
      return { day, sales: value?.sales ?? null, qty: value?.qty ?? null, receipts: value?.receipts ?? null };
    });
  }, [detail]);
  const salary = useAgentSalaryHistory(open, canViewSalaries, detail, selection);
  const selectedPeer = detail?.peer_rows.find((row) => row.is_selected) ?? null;
  const agentStoreShare = detail?.context_summary && detail.context_summary.total_sales > 0
    ? Number(detail.summary.total_sales) * 100 / Number(detail.context_summary.total_sales) : null;
  const monthlyMetricLabel = monthlyMetric === 'sales' ? 'Vanzare'
    : monthlyMetric === 'bon2acc' ? 'ProcBon2Acc' : monthlyMetric === 'focus' ? 'PrcFocus/AccQtty' : 'Retururi';
  const monthlyMetricColor = monthlyMetric === 'sales' ? '#4f46e5'
    : monthlyMetric === 'bon2acc' ? '#0f766e' : monthlyMetric === 'focus' ? '#db2777' : '#dc2626';
  return {
    monthlyMetric, setMonthlyMetric, historyData, dailyData, salary, selectedPeer, agentStoreShare,
    monthlyMetricLabel, monthlyMetricColor,
    showMonthlyTargetLines: detail?.level !== 'agent' && monthlyMetric === 'sales',
    isReturnsMetric: monthlyMetric === 'returns',
  };
}

export type PerformanceDetailModel = ReturnType<typeof usePerformanceDetailModel>;
