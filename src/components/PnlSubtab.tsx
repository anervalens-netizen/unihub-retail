import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  BadgeDollarSign,
  Building2,
  ChartNoAxesCombined,
  TrendingDown,
  TrendingUp,
} from "lucide-react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  getPnlMonths,
  getPnlOverview,
  type PnlMetrics,
  type PnlMonthlyPoint,
} from "../api/storePnl";

const CATEGORY_LABELS: Record<string, string> = {
  v1: "Venituri cartele",
  v11: "Venituri accesorii",
  v2: "Venituri încărcări",
  v3: "Alte venituri",
  c1: "Cost cartele",
  c11: "Cost accesorii",
  c2: "Cost încărcări",
  c3: "Cost salarial",
  c4: "Chirii",
  c5: "Utilități",
  c6: "Alte costuri",
  a1: "Amortizare",
};

const money = new Intl.NumberFormat("ro-RO", {
  style: "currency",
  currency: "RON",
  maximumFractionDigits: 0,
});
const compactMoney = new Intl.NumberFormat("ro-RO", {
  notation: "compact",
  maximumFractionDigits: 1,
});

function monthLabel(value: string): string {
  return new Intl.DateTimeFormat("ro-RO", {
    month: "short",
    year: "2-digit",
  }).format(new Date(`${value}-01T00:00:00`));
}

function KpiCard({
  label,
  value,
  icon: Icon,
}: {
  label: string;
  value: number;
  icon: typeof TrendingUp;
}) {
  const positive = value >= 0;
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-700 dark:bg-slate-900">
      <div className="flex items-center justify-between text-xs font-medium uppercase tracking-wide text-slate-500">
        {label}
        <span className="rounded-xl bg-indigo-50 p-2 text-indigo-600 dark:bg-indigo-950/40">
          <Icon size={16} />
        </span>
      </div>
      <div
        className={`mt-3 text-xl font-bold ${label.includes("EBIT") ? (positive ? "text-emerald-600" : "text-rose-600") : "text-slate-900 dark:text-slate-100"}`}
      >
        {money.format(value)}
      </div>
    </div>
  );
}

function marginPct(metrics: PnlMetrics): string {
  return metrics.revenue
    ? `${((metrics.ebit / metrics.revenue) * 100).toFixed(1)}%`
    : "—";
}

export function PnlSubtab() {
  const [startMonth, setStartMonth] = useState("");
  const [endMonth, setEndMonth] = useState("");
  const [company, setCompany] = useState("");
  const [storeSearch, setStoreSearch] = useState("");
  const monthsQuery = useQuery({
    queryKey: ["store-pnl-months"],
    queryFn: getPnlMonths,
    staleTime: 5 * 60_000,
  });

  useEffect(() => {
    if (!monthsQuery.data?.length || endMonth) return;
    const available = monthsQuery.data.map((item) => item.month).sort();
    setEndMonth(available.at(-1) ?? "");
    setStartMonth(available.at(-12) ?? available[0] ?? "");
  }, [monthsQuery.data, endMonth]);

  const overviewQuery = useQuery({
    queryKey: ["store-pnl-overview", startMonth, endMonth, company],
    queryFn: () => getPnlOverview(startMonth, endMonth, company),
    enabled: Boolean(startMonth && endMonth),
  });
  const data = overviewQuery.data;
  const filteredStores = useMemo(() => {
    const needle = storeSearch.trim().toLocaleLowerCase("ro-RO");
    if (!needle) return data?.stores ?? [];
    return (data?.stores ?? []).filter((store) =>
      `${store.location} ${store.site_code} ${store.company}`
        .toLocaleLowerCase("ro-RO")
        .includes(needle),
    );
  }, [data?.stores, storeSearch]);

  if (monthsQuery.isLoading)
    return (
      <div className="p-8 text-sm text-slate-500">
        Se încarcă istoricul P&amp;L…
      </div>
    );
  if (monthsQuery.isError)
    return (
      <div className="m-6 rounded-xl bg-rose-50 p-4 text-sm text-rose-700">
        Nu am putut încărca lunile P&amp;L.
      </div>
    );

  return (
    <div className="space-y-6 p-4 sm:p-6">
      <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <BadgeDollarSign className="text-indigo-600" />
            <h2 className="text-xl font-bold text-slate-900 dark:text-white">
              Profit &amp; Loss
            </h2>
          </div>
          <p className="mt-1 text-sm text-slate-500">
            Performanță financiară pe rețea, companie și magazin.
          </p>
        </div>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
          <label className="text-xs text-slate-500">
            De la
            <select
              value={startMonth}
              onChange={(e) => setStartMonth(e.target.value)}
              className="mt-1 block w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900"
            >
              {monthsQuery.data?.map((item) => (
                <option key={item.month} value={item.month}>
                  {monthLabel(item.month)}
                  {item.has_estimated ? " · estimat" : ""}
                </option>
              ))}
            </select>
          </label>
          <label className="text-xs text-slate-500">
            Până la
            <select
              value={endMonth}
              onChange={(e) => setEndMonth(e.target.value)}
              className="mt-1 block w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900"
            >
              {monthsQuery.data?.map((item) => (
                <option key={item.month} value={item.month}>
                  {monthLabel(item.month)}
                  {item.has_estimated ? " · estimat" : ""}
                </option>
              ))}
            </select>
          </label>
          <label className="text-xs text-slate-500">
            Companie
            <select
              value={company}
              onChange={(e) => setCompany(e.target.value)}
              className="mt-1 block w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900"
            >
              <option value="">Toată rețeaua</option>
              <option value="Mobiup">Mobiup</option>
              <option value="Mobicell">Mobicell</option>
            </select>
          </label>
        </div>
      </div>

      {data?.monthly.some((point) => point.is_estimated) && (
        <div className="flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-300">
          <AlertTriangle size={17} className="mt-0.5 shrink-0" />
          <span>
            Intervalul conține luni estimate. Acestea sunt marcate distinct în
            grafic și în tabel.
          </span>
        </div>
      )}

      {overviewQuery.isLoading && (
        <div className="py-16 text-center text-sm text-slate-500">
          Calculez indicatorii financiari…
        </div>
      )}
      {overviewQuery.isError && (
        <div className="rounded-xl bg-rose-50 p-4 text-sm text-rose-700">
          Nu am putut încărca raportul P&amp;L.
        </div>
      )}
      {data && (
        <>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
            <KpiCard
              label="Venituri"
              value={data.summary.revenue}
              icon={TrendingUp}
            />
            <KpiCard
              label="Marjă brută"
              value={data.summary.gross_margin}
              icon={ChartNoAxesCombined}
            />
            <KpiCard
              label="Costuri operaționale"
              value={data.summary.operating_costs}
              icon={TrendingDown}
            />
            <KpiCard
              label="EBITDA"
              value={data.summary.ebitda}
              icon={BadgeDollarSign}
            />
            <KpiCard
              label={`EBIT · ${marginPct(data.summary)}`}
              value={data.summary.ebit}
              icon={Building2}
            />
          </div>

          <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-700 dark:bg-slate-900">
            <h3 className="mb-4 font-semibold text-slate-900 dark:text-white">
              Evoluție lunară
            </h3>
            <div className="h-80">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={data.monthly}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#94a3b833" />
                  <XAxis
                    dataKey="month"
                    tickFormatter={monthLabel}
                    fontSize={11}
                  />
                  <YAxis
                    tickFormatter={(value) => compactMoney.format(value)}
                    fontSize={11}
                  />
                  <Tooltip
                    formatter={(value) => money.format(Number(value))}
                    labelFormatter={(label) =>
                      `${monthLabel(String(label))}${data.monthly.find((x) => x.month === label)?.is_estimated ? " · estimat" : ""}`
                    }
                  />
                  <Legend />
                  <Line
                    type="monotone"
                    dataKey="revenue"
                    name="Venituri"
                    stroke="#4f46e5"
                    strokeWidth={2.5}
                    dot={({
                      cx,
                      cy,
                      payload,
                    }: {
                      cx?: number;
                      cy?: number;
                      payload: PnlMonthlyPoint;
                    }) => (
                      <circle
                        cx={cx}
                        cy={cy}
                        r={payload.is_estimated ? 5 : 3}
                        fill={payload.is_estimated ? "#f59e0b" : "#4f46e5"}
                      />
                    )}
                  />
                  <Line
                    type="monotone"
                    dataKey="ebitda"
                    name="EBITDA"
                    stroke="#10b981"
                    strokeWidth={2}
                  />
                  <Line
                    type="monotone"
                    dataKey="ebit"
                    name="EBIT"
                    stroke="#f43f5e"
                    strokeWidth={2}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="grid gap-4 xl:grid-cols-[0.8fr_1.2fr]">
            <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-700 dark:bg-slate-900">
              <h3 className="mb-3 font-semibold">Structură P&amp;L</h3>
              <div className="space-y-2">
                {Object.entries(data.categories).map(([code, value]) => (
                  <div
                    key={code}
                    className="flex items-center justify-between rounded-lg bg-slate-50 px-3 py-2 text-sm dark:bg-slate-800/60"
                  >
                    <span className="text-slate-600 dark:text-slate-300">
                      {CATEGORY_LABELS[code] ?? code}
                    </span>
                    <span className="font-semibold tabular-nums">
                      {money.format(value)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
            <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm dark:border-slate-700 dark:bg-slate-900">
              <div className="flex items-center justify-between gap-3 border-b border-slate-200 p-4 dark:border-slate-700">
                <div>
                  <h3 className="font-semibold">Magazine</h3>
                  <p className="text-xs text-slate-500">ordonate după EBIT</p>
                </div>
                <input
                  value={storeSearch}
                  onChange={(e) => setStoreSearch(e.target.value)}
                  placeholder="Caută magazin…"
                  className="w-44 rounded-xl border border-slate-200 bg-transparent px-3 py-2 text-sm dark:border-slate-700"
                />
              </div>
              <div className="max-h-[580px] overflow-auto">
                <table className="w-full text-sm">
                  <thead className="sticky top-0 bg-slate-50 text-xs uppercase text-slate-500 dark:bg-slate-800">
                    <tr>
                      <th className="px-3 py-2 text-left">Magazin</th>
                      <th className="px-3 py-2 text-right">Venituri</th>
                      <th className="px-3 py-2 text-right">EBITDA</th>
                      <th className="px-3 py-2 text-right">EBIT</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredStores.map((store) => (
                      <tr
                        key={`${store.company}-${store.source_site_code}`}
                        className="border-t border-slate-100 dark:border-slate-800"
                      >
                        <td className="px-3 py-2">
                          <div className="font-medium">{store.location}</div>
                          <div className="text-xs text-slate-500">
                            {store.company} · {store.site_code}
                            {store.has_estimates && (
                              <span className="ml-1 rounded bg-amber-100 px-1.5 py-0.5 text-amber-700">
                                estimat
                              </span>
                            )}
                          </div>
                        </td>
                        <td className="px-3 py-2 text-right tabular-nums">
                          {money.format(store.revenue)}
                        </td>
                        <td
                          className={`px-3 py-2 text-right tabular-nums ${store.ebitda < 0 ? "text-rose-600" : ""}`}
                        >
                          {money.format(store.ebitda)}
                        </td>
                        <td
                          className={`px-3 py-2 text-right font-semibold tabular-nums ${store.ebit < 0 ? "text-rose-600" : "text-emerald-600"}`}
                        >
                          {money.format(store.ebit)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
