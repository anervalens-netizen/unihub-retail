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
  getPnlAnnual,
  getPnlMonths,
  getPnlOverview,
  getPnlRegions,
  getPnlStores,
  type PnlAnnualPoint,
  type PnlMetrics,
  type PnlMonthlyPoint,
  type PnlStoreOption,
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

export function defaultPnlRange(
  months: string[],
  now = new Date(),
): { start: string; end: string } {
  const available = [...months].sort();
  const currentYear = String(now.getFullYear());
  let selected = available.filter((month) => month.startsWith(`${currentYear}-`));
  if (!selected.length && available.length) {
    const latestYear = available.at(-1)?.slice(0, 4);
    selected = available.filter((month) => month.startsWith(`${latestYear}-`));
  }
  return {
    start: selected[0] ?? "",
    end: selected.at(-1) ?? "",
  };
}

export function pnlStoreOptionValue(store: PnlStoreOption): string {
  return JSON.stringify([store.scope_company, store.site_code]);
}

function FinancialMetric({
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
    <div className="min-w-0 p-4 sm:p-5">
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
  const [regional, setRegional] = useState("");
  const [storeScope, setStoreScope] = useState("");
  const [storeSearch, setStoreSearch] = useState("");
  const monthsQuery = useQuery({
    queryKey: ["store-pnl-months"],
    queryFn: getPnlMonths,
    staleTime: 5 * 60_000,
  });

  useEffect(() => {
    if (!monthsQuery.data?.length || endMonth) return;
    const range = defaultPnlRange(monthsQuery.data.map((item) => item.month));
    setStartMonth(range.start);
    setEndMonth(range.end);
  }, [monthsQuery.data, endMonth]);

  const storesQuery = useQuery({
    queryKey: ["store-pnl-stores", company, regional],
    queryFn: () => getPnlStores(company, regional),
    staleTime: 5 * 60_000,
  });
  const regionsQuery = useQuery({
    queryKey: ["store-pnl-regions", company],
    queryFn: () => getPnlRegions(company),
    staleTime: 5 * 60_000,
  });
  const selectedStore = useMemo(
    () => storesQuery.data?.find(
      (store) => pnlStoreOptionValue(store) === storeScope,
    ),
    [storeScope, storesQuery.data],
  );
  const siteCode = selectedStore?.site_code ?? "";
  const siteCompany = selectedStore?.scope_company ?? "";

  const overviewQuery = useQuery({
    queryKey: [
      "store-pnl-overview",
      startMonth,
      endMonth,
      company,
      regional,
      siteCode,
      siteCompany,
    ],
    queryFn: () => getPnlOverview(
      startMonth,
      endMonth,
      company,
      siteCode,
      siteCompany,
      regional,
    ),
    enabled: Boolean(startMonth && endMonth),
  });
  const annualQuery = useQuery({
    queryKey: ["store-pnl-annual", company, regional, siteCode, siteCompany],
    queryFn: () => getPnlAnnual(company, siteCode, siteCompany, regional),
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
      <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-700 dark:bg-slate-900 sm:p-5">
        <div>
          <div className="flex items-center gap-2">
            <BadgeDollarSign className="text-indigo-600" />
            <h2 className="text-xl font-bold text-slate-900 dark:text-white">
              Profit &amp; Loss
            </h2>
          </div>
          <p className="mt-1 text-sm text-slate-500">
            Performanță financiară pe rețea, regiune, companie și magazin.
          </p>
        </div>
        <div className="mt-4 grid grid-cols-2 gap-2 lg:grid-cols-5">
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
              onChange={(e) => {
                setCompany(e.target.value);
                setRegional("");
                setStoreScope("");
              }}
              className="mt-1 block w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900"
            >
              <option value="">Toată rețeaua</option>
              <option value="Mobiup">Mobiup</option>
              <option value="Mobicell">Mobicell</option>
            </select>
          </label>
          <label className="text-xs text-slate-500">
            RM / regiune
            <select
              value={regional}
              onChange={(e) => {
                setRegional(e.target.value);
                setStoreScope("");
              }}
              disabled={regionsQuery.isLoading || regionsQuery.isError}
              className="mt-1 block w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm disabled:opacity-60 dark:border-slate-700 dark:bg-slate-900"
            >
              <option value="">Toate regiunile</option>
              {regionsQuery.data?.map((region) => (
                <option key={region} value={region}>{region}</option>
              ))}
            </select>
          </label>
          <label className="col-span-2 text-xs text-slate-500 lg:col-span-1">
            Magazin
            <select
              value={storeScope}
              onChange={(e) => setStoreScope(e.target.value)}
              disabled={storesQuery.isLoading || storesQuery.isError}
              className="mt-1 block w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm disabled:opacity-60 dark:border-slate-700 dark:bg-slate-900"
            >
              <option value="">
                {storesQuery.isError
                  ? "Magazine indisponibile"
                  : "Toate magazinele"}
              </option>
              {storesQuery.data?.map((store) => (
                <option
                  key={`${store.company_name}-${store.site_code}`}
                  value={pnlStoreOptionValue(store)}
                >
                  {store.location} · {store.site_code}
                  {store.scope_company ? ` · ${store.scope_company}` : ""}
                </option>
              ))}
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
          <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm dark:border-slate-700 dark:bg-slate-900">
            <div className="grid divide-y divide-slate-200 sm:grid-cols-2 sm:divide-x sm:divide-y-0 xl:grid-cols-5 dark:divide-slate-700">
            <FinancialMetric
              label="Venituri"
              value={data.summary.revenue}
              icon={TrendingUp}
            />
            <FinancialMetric
              label="Marjă brută"
              value={data.summary.gross_margin}
              icon={ChartNoAxesCombined}
            />
            <FinancialMetric
              label="Costuri operaționale"
              value={data.summary.operating_costs}
              icon={TrendingDown}
            />
            <FinancialMetric
              label="EBITDA"
              value={data.summary.ebitda}
              icon={BadgeDollarSign}
            />
            <FinancialMetric
              label={`EBIT · ${marginPct(data.summary)}`}
              value={data.summary.ebit}
              icon={Building2}
            />
            </div>
            {data.reconciliation.length === 1 && data.reconciliation[0].pnl_to_net_sales_pct !== null && (
              <div className="border-t border-slate-200 px-4 py-2 text-xs text-slate-500 dark:border-slate-700">
                Vânzări Retail fără TVA: {money.format(data.reconciliation[0].retail_sales_net)} · Venit P&amp;L / vânzări nete: {data.reconciliation[0].pnl_to_net_sales_pct?.toFixed(1)}%
              </div>
            )}
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
                    dataKey="ebit"
                    name="EBIT"
                    stroke="#f43f5e"
                    strokeWidth={3}
                    strokeDasharray="8 6"
                    dot={{ r: 2, fill: "#f43f5e" }}
                  />
                  <Line
                    type="monotone"
                    dataKey="ebitda"
                    name="EBITDA"
                    stroke="#10b981"
                    strokeWidth={2.5}
                    dot={{
                      r: 4,
                      fill: "#10b981",
                      stroke: "#ffffff",
                      strokeWidth: 1.5,
                    }}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-700 dark:bg-slate-900">
            <div className="mb-4 flex items-start justify-between gap-3">
              <div>
                <h3 className="font-semibold text-slate-900 dark:text-white">
                  Evoluție anuală
                </h3>
                <p className="text-xs text-slate-500">
                  Total pentru lunile disponibile din fiecare an; punctele
                  portocalii includ estimări.
                </p>
              </div>
              {annualQuery.isLoading && (
                <span className="text-xs text-slate-500">Se încarcă…</span>
              )}
            </div>
            {annualQuery.isError ? (
              <div className="rounded-xl bg-rose-50 p-4 text-sm text-rose-700">
                Nu am putut încărca evoluția anuală.
              </div>
            ) : annualQuery.data?.length ? (
              <div className="h-72">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={annualQuery.data}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#94a3b833" />
                    <XAxis dataKey="year" fontSize={11} />
                    <YAxis
                      tickFormatter={(value) => compactMoney.format(value)}
                      fontSize={11}
                    />
                    <Tooltip
                      formatter={(value) => money.format(Number(value))}
                      labelFormatter={(label, payload) => {
                        const point = payload?.[0]?.payload as PnlAnnualPoint | undefined;
                        return `Anul ${String(label)}${point ? ` · ${point.store_count} magazine · ${point.month_count} luni` : ""}`;
                      }}
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
                        payload: PnlAnnualPoint;
                      }) => (
                        <circle
                          cx={cx}
                          cy={cy}
                          r={payload.is_estimated ? 6 : 4}
                          fill={payload.is_estimated ? "#f59e0b" : "#4f46e5"}
                        />
                      )}
                    />
                    <Line
                      type="monotone"
                      dataKey="ebit"
                      name="EBIT"
                      stroke="#f43f5e"
                      strokeWidth={3}
                      strokeDasharray="8 6"
                      dot={{ r: 2, fill: "#f43f5e" }}
                    />
                    <Line
                      type="monotone"
                      dataKey="ebitda"
                      name="EBITDA"
                      stroke="#10b981"
                      strokeWidth={2.5}
                      dot={{
                        r: 4,
                        fill: "#10b981",
                        stroke: "#ffffff",
                        strokeWidth: 1.5,
                      }}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            ) : (
              !annualQuery.isLoading && (
                <div className="py-12 text-center text-sm text-slate-500">
                  Nu există istoric anual pentru selecția curentă.
                </div>
              )
            )}
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
