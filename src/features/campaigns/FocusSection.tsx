import { useMemo } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Building2, PackageSearch, Sparkles, Tag } from "lucide-react";
import type { CampaignSnapshot, FocusHistoryPoint } from "../../api/generated/runtime-types";
import { ExportTableButton } from "../../components/ExportTableButton";
import {
  ErrorCard,
  LoadingCard,
  Metric,
} from "../../components/common/DataDisplay";
import { formatCurrency, formatInt, formatPercent } from "../../lib/formatters";
import { CampaignMonthBar } from "./CampaignControls";

export function FocusSection({
  snapshot,
  history,
  historyMonth,
  month,
  months,
  currentMonth,
  loading,
  error,
  onHistoryMonthChange,
  onMonthChange,
  onRetry,
}: {
  snapshot: CampaignSnapshot;
  history: FocusHistoryPoint[];
  historyMonth: string;
  month: string;
  months: string[];
  currentMonth: string;
  loading: boolean;
  error: string;
  onHistoryMonthChange: (month: string) => void;
  onMonthChange: (month: string) => void;
  onRetry: () => void;
}) {
  const selectedPoint = useMemo(
    () =>
      history.find((item) => item.month === historyMonth) ??
      history.at(-1) ??
      null,
    [history, historyMonth],
  );
  const chart = useMemo(
    () =>
      history.map((item) => ({
        month: item.month.slice(2),
        sales: Number(item.total_focus_sales),
        qty: Number(item.total_focus_qty),
        share: Number(item.focus_share_pct ?? 0),
      })),
    [history],
  );
  const headline = useMemo(() => {
    const leader = snapshot.products[0];
    return leader
      ? `${leader.item_name} conduce ${month} cu ${formatInt(leader.qty_total)} bucati si ${formatCurrency(leader.sales_total)}.`
      : `Nu exista inca focus products vandute in ${month} pentru filtrarea selectata.`;
  }, [snapshot.products, month]);
  return (
    <>
      <CampaignMonthBar
        title="Focus"
        icon={Sparkles}
        months={months}
        value={month}
        onChange={onMonthChange}
        currentMonth={currentMonth}
      />
      <div className="glass rounded-4xl border border-amber-100 bg-linear-to-br from-amber-50 via-white to-white p-4 dark:border-amber-900/30 dark:from-amber-950/20 dark:via-slate-900 dark:to-slate-900">
        <div className="mb-3 flex items-center gap-2 text-amber-600 dark:text-amber-400">
          <Sparkles size={16} />
          <span className="text-[11px] font-bold uppercase tracking-[0.22em]">
            Focus Products
          </span>
        </div>
        <div className="text-lg font-black">
          Indicator permanent de performanta
        </div>
        <p className="mt-2 text-xs text-slate-600 dark:text-slate-300">
          {headline}
        </p>
      </div>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <FocusStat
          icon={Tag}
          label="Vanzari focus"
          value={formatCurrency(snapshot.overview.total_focus_sales)}
          accent="amber"
        />
        <FocusStat
          icon={PackageSearch}
          label="Cantitate focus"
          value={formatInt(snapshot.overview.total_focus_qty)}
          accent="indigo"
        />
        <FocusStat
          icon={Sparkles}
          label="Share focus"
          value={formatPercent(snapshot.overview.focus_share_pct)}
          accent="emerald"
        />
        <FocusStat
          icon={Building2}
          label="Magazine active"
          value={formatInt(snapshot.overview.active_focus_stores)}
          accent="rose"
        />
      </div>
      <div className="glass rounded-3xl p-4">
        <div className="mb-3 flex items-center justify-between gap-3">
          <div>
            <h3 className="text-sm font-bold">
              Luna de referinta pentru istoric
            </h3>
            <p className="text-[11px] text-slate-500">
              Selector local doar pentru istoricul focus
            </p>
          </div>
          <select
            value={historyMonth}
            onChange={(event) => onHistoryMonthChange(event.target.value)}
            className="rounded-2xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-semibold outline-none dark:border-slate-700 dark:bg-slate-800"
          >
            {months.map((candidate) => (
              <option key={candidate} value={candidate}>
                {candidate}
              </option>
            ))}
          </select>
        </div>
      </div>
      {loading ? (
        <LoadingCard label="Se incarca istoricul focus..." />
      ) : error ? (
        <ErrorCard message={error} onRetry={onRetry} />
      ) : !selectedPoint ? (
        <ErrorCard
          message="Nu exista indicatori focus pentru luna selectata."
          onRetry={onRetry}
        />
      ) : (
        <FocusHistoryView
          chart={chart}
          selectedPoint={selectedPoint}
          historyMonth={historyMonth}
          snapshot={snapshot}
          month={month}
        />
      )}
    </>
  );
}

function FocusHistoryView({
  chart,
  selectedPoint,
  historyMonth,
  snapshot,
  month,
}: {
  chart: Array<{ month: string; sales: number; qty: number; share: number }>;
  selectedPoint: FocusHistoryPoint;
  historyMonth: string;
  snapshot: CampaignSnapshot;
  month: string;
}) {
  return (
    <>
      <div className="glass rounded-3xl p-4">
        <div className="mb-3 flex items-center justify-between">
          <div>
            <h3 className="text-sm font-bold">Istoric focus</h3>
            <p className="text-[11px] text-slate-500">
              Evolutia indicatorului permanent pana la {historyMonth}
            </p>
          </div>
          <div className="rounded-2xl bg-slate-50 px-3 py-2 text-right dark:bg-slate-800/60">
            <div className="text-[10px] uppercase tracking-wide text-slate-500">
              Luna selectata
            </div>
            <div className="text-lg font-black">{selectedPoint.month}</div>
          </div>
        </div>
        <div className="h-64">
          <ResponsiveContainer
            width="100%"
            height="100%"
            minWidth={1}
            minHeight={1}
          >
            <AreaChart data={chart}>
              <CartesianGrid
                strokeDasharray="3 3"
                vertical={false}
                opacity={0.15}
              />
              <XAxis
                dataKey="month"
                tick={{ fontSize: 10 }}
                axisLine={false}
                tickLine={false}
              />
              <YAxis
                yAxisId="sales"
                tick={{ fontSize: 10 }}
                axisLine={false}
                tickLine={false}
              />
              <YAxis
                yAxisId="share"
                orientation="right"
                tick={{ fontSize: 10 }}
                axisLine={false}
                tickLine={false}
              />
              <Tooltip
                formatter={(value: unknown, name: unknown) =>
                  String(name) === "Share"
                    ? `${Number(value).toFixed(2)}%`
                    : formatCurrency(Number(value))
                }
              />
              <Legend />
              <Area
                yAxisId="sales"
                type="monotone"
                dataKey="sales"
                name="Vanzari focus"
                stroke="#d97706"
                fill="#fbbf24"
                fillOpacity={0.2}
                strokeWidth={3}
              />
              <Line
                yAxisId="share"
                type="monotone"
                dataKey="share"
                name="Share"
                stroke="#4f46e5"
                strokeWidth={2}
                dot={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>
      <div className="glass rounded-3xl p-4">
        <div className="grid grid-cols-2 gap-3 text-xs lg:grid-cols-4">
          <Metric
            label="Vanzari focus"
            value={formatCurrency(selectedPoint.total_focus_sales)}
          />
          <Metric
            label="Cantitate focus"
            value={formatInt(selectedPoint.total_focus_qty)}
          />
          <Metric
            label="Pondere in volum"
            value={formatPercent(selectedPoint.focus_share_pct)}
          />
          <Metric
            label="Magazine active"
            value={formatInt(selectedPoint.active_focus_stores)}
          />
        </div>
      </div>
      <FocusProductsTable snapshot={snapshot} month={month} />
    </>
  );
}

function FocusProductsTable({
  snapshot,
  month,
}: {
  snapshot: CampaignSnapshot;
  month: string;
}) {
  const rows = snapshot.products.map((item) => ({
    key: item.item_code,
    primary: item.item_name,
    secondary: item.item_code,
    rightTop: formatCurrency(item.sales_total),
    rightBottom: `${formatInt(item.qty_total)} buc · ${formatInt(item.store_count)} magazine`,
    sales: item.sales_total,
    quantity: item.qty_total,
    stores: item.store_count,
  }));
  return (
    <div className="glass rounded-3xl p-4">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-bold">Top produse focus</h3>
          <p className="text-[11px] text-slate-500">
            Snapshot pentru luna {month}
          </p>
        </div>
        <ExportTableButton
          filename="Top produse focus"
          sheetName="Top produse focus"
          rows={rows}
          columns={[
            { header: "Denumire", value: (row) => row.primary },
            { header: "Cod", value: (row) => row.secondary },
            {
              header: "Vanzari",
              value: (row) => row.sales,
              format: "currency",
            },
            {
              header: "Cantitate",
              value: (row) => row.quantity,
              format: "integer",
            },
            {
              header: "Magazine",
              value: (row) => row.stores,
              format: "integer",
            },
          ]}
        />
      </div>
      <div className="space-y-2">
        {rows.map((row) => (
          <div
            key={row.key}
            className="rounded-2xl bg-slate-50 p-3 dark:bg-slate-800/60"
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="text-sm font-bold">{row.primary}</div>
                <div className="text-[11px] text-slate-500">
                  {row.secondary}
                </div>
              </div>
              <div className="text-right">
                <div className="text-sm font-black text-amber-600 dark:text-amber-400">
                  {row.rightTop}
                </div>
                <div className="text-[11px] text-slate-500">
                  {row.rightBottom}
                </div>
              </div>
            </div>
          </div>
        ))}
        {rows.length === 0 && (
          <div className="rounded-2xl bg-slate-50 p-4 text-xs font-semibold text-slate-500 dark:bg-slate-800/60">
            Nu exista produse focus vandute pe filtrarea selectata.
          </div>
        )}
      </div>
    </div>
  );
}

const ACCENTS = {
  amber: "bg-amber-50 text-amber-600 dark:bg-amber-900/20",
  indigo: "bg-indigo-50 text-indigo-600 dark:bg-indigo-900/20",
  emerald: "bg-emerald-50 text-emerald-600 dark:bg-emerald-900/20",
  rose: "bg-rose-50 text-rose-600 dark:bg-rose-900/20",
} as const;
function FocusStat({
  icon: Icon,
  label,
  value,
  accent,
}: {
  icon: typeof Sparkles;
  label: string;
  value: string;
  accent: keyof typeof ACCENTS;
}) {
  return (
    <div className="glass rounded-3xl p-4">
      <div
        className={`mb-3 flex h-10 w-10 items-center justify-center rounded-2xl ${ACCENTS[accent]}`}
      >
        <Icon size={18} />
      </div>
      <div className="text-[11px] font-bold uppercase tracking-wide text-slate-500">
        {label}
      </div>
      <div className="mt-1 text-lg font-black">{value}</div>
    </div>
  );
}
