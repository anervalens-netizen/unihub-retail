import type { PnlMetrics, PnlMonthlyPoint, PnlStoreOption } from '../../api/storePnl';
import { formatIsoMonth, getCurrentYearMonth } from '../../lib/dates';

export const CATEGORY_LABELS: Record<string, string> = {
  v1: 'Venituri cartele', v11: 'Venituri accesorii', v2: 'Venituri încărcări', v3: 'Alte venituri', c1: 'Cost cartele', c11: 'Cost accesorii', c2: 'Cost încărcări', c3: 'Cost salarial', c4: 'Chirii', c5: 'Utilități', c6: 'Alte costuri', a1: 'Amortizare',
};

export const money = new Intl.NumberFormat('ro-RO', { style: 'currency', currency: 'RON', maximumFractionDigits: 0 });
export const compactMoney = new Intl.NumberFormat('ro-RO', { notation: 'compact', maximumFractionDigits: 1 });

export function monthLabel(value: string): string { return formatIsoMonth(value); }

export function defaultPnlRange(months: string[], now?: Date): { start: string; end: string } {
  const available = [...months].sort();
  const currentYear = getCurrentYearMonth(now).slice(0, 4);
  let selected = available.filter((month) => month.startsWith(`${currentYear}-`));
  if (!selected.length && available.length) {
    const latestYear = available[available.length - 1]?.slice(0, 4);
    selected = available.filter((month) => month.startsWith(`${latestYear}-`));
  }
  return { start: selected[0] ?? '', end: selected[selected.length - 1] ?? '' };
}

export function pnlStoreOptionValue(store: PnlStoreOption): string { return JSON.stringify([store.scope_company, store.site_code]); }
export function marginPct(metrics: PnlMetrics): string { return metrics.revenue ? `${((metrics.ebit / metrics.revenue) * 100).toFixed(1)}%` : '—'; }

export function monthlyVariance(points: PnlMonthlyPoint[]) {
  if (points.length < 2) return null;
  const sorted = [...points].sort((left, right) => left.month.localeCompare(right.month));
  const current = sorted.at(-1);
  const previous = sorted.at(-2);
  if (!current || !previous) return null;
  const pct = (value: number, base: number) => base === 0 ? null : ((value - base) / Math.abs(base)) * 100;
  return { currentMonth: current.month, previousMonth: previous.month, revenuePct: pct(current.revenue, previous.revenue), ebitdaPct: pct(current.ebitda, previous.ebitda), ebitPct: pct(current.ebit, previous.ebit) };
}
