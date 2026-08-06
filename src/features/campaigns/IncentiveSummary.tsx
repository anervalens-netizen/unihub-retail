import { BadgePercent, Gift, Tag } from "lucide-react";
import { IncentiveQualificationSummary } from "../../components/IncentiveQualificationSummary";
import { ExportTableButton } from "../../components/ExportTableButton";
import type {
  CampaignsPromotionsResponse,
  IncentiveCategory,
  IncentiveCategoryBreakdown,
} from "../../api/generated/runtime-types";
import { formatCurrency, formatInt } from "../../lib/formatters";

export function IncentiveCard({
  promoData,
}: {
  promoData: CampaignsPromotionsResponse | null;
}) {
  const tiers: IncentiveCategory[] = promoData?.incentive_categories ?? [];
  const periods = promoData?.incentive_periods ?? [];
  return (
    <div className="glass rounded-4xl border border-indigo-100 p-4 dark:border-indigo-900/30">
      <header className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <div className="mb-2 flex items-center gap-2 text-indigo-600 dark:text-indigo-400">
            <Gift size={16} />
            <span className="text-[11px] font-bold uppercase tracking-[0.22em]">
              Incentive
            </span>
          </div>
          <h4 className="text-base font-black tracking-tight">
            {promoData?.incentive_title || "Incentive"}
          </h4>
          <p className="mt-1 max-w-3xl text-xs text-slate-500 dark:text-slate-300">
            {periods.length > 1
              ? "Valoarea fiecarui produs este cea activa la data vanzarii. Calificarea se aplica o singura data, pe targetul lunar al magazinului."
              : promoData?.incentive_description ||
                "Bonus calculat pe produs eligibil vandut."}
          </p>
        </div>
        {promoData && promoData.incentive_product_count > 0 && (
          <div className="flex items-center gap-1 rounded-lg bg-indigo-50 px-2 py-1 text-[11px] font-bold text-indigo-700 dark:bg-indigo-950/40 dark:text-indigo-300">
            <Tag size={11} />
            {formatInt(promoData.incentive_product_count)} coduri unice
          </div>
        )}
      </header>
      <div className="mt-4 grid grid-cols-2 gap-x-4 gap-y-3 border-y border-slate-200 py-3 sm:grid-cols-4 dark:border-slate-700">
        <Metric
          value={promoData ? formatInt(promoData.incentive_sold_qty) : "-"}
          label="unități vândute"
        />
        <Metric
          value={
            promoData?.incentive_qty != null
              ? formatInt(promoData.incentive_qty)
              : "-"
          }
          label="unități eligibile după promo"
          accent="text-emerald-600 dark:text-emerald-300"
        />
        <Metric
          value={
            promoData?.incentive_qualified_qty != null
              ? formatInt(promoData.incentive_qualified_qty)
              : "-"
          }
          label="unități în magazinele calificate"
        />
        <Metric
          value={
            promoData?.incentive_value != null
              ? formatCurrency(promoData.incentive_value)
              : "-"
          }
          label="incentive calculat acum"
          accent="text-indigo-600 dark:text-indigo-300"
        />
      </div>
      {periods.length > 0 && <IncentivePeriods periods={periods} />}
      <IncentiveQualificationSummary promoData={promoData} className="mt-3" />
      {tiers.length > 0 && (
        <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-slate-200 pt-3 text-[10px] dark:border-slate-700">
          <span className="font-bold uppercase text-slate-400">
            Tier-uri vandute
          </span>
          {tiers.map((tier) => (
            <span
              key={tier.label}
              className="rounded-full bg-indigo-50 px-2 py-1 font-bold text-indigo-700 dark:bg-indigo-950/40 dark:text-indigo-300"
            >
              {tier.label}: {formatInt(tier.qty)}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function Metric({
  value,
  label,
  accent = "",
}: {
  value: string;
  label: string;
  accent?: string;
}) {
  return (
    <div>
      <div className={`text-2xl font-black ${accent}`}>{value}</div>
      <div className="text-[11px] font-semibold text-slate-500">{label}</div>
    </div>
  );
}

function IncentivePeriods({
  periods,
}: {
  periods: NonNullable<CampaignsPromotionsResponse["incentive_periods"]>;
}) {
  return (
    <div className="mt-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <p className="text-xs font-bold text-slate-700 dark:text-slate-200">
          {periods.length > 1
            ? `${periods.length} mecanisme în luna selectată`
            : "Mecanismul lunii"}
        </p>
        <span className="text-[10px] font-semibold text-slate-400">
          valorile se aplică după data vânzării
        </span>
      </div>
      <div className="grid gap-2 md:grid-cols-2">
        {periods.map((period) => (
          <div
            key={`${period.start_date}-${period.end_date}`}
            className="rounded-xl border border-indigo-100 bg-indigo-50/40 px-3 py-2.5 dark:border-indigo-900/50 dark:bg-indigo-950/20"
          >
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div>
                <div className="text-xs font-black text-indigo-700 dark:text-indigo-300">
                  {period.label}
                </div>
                <div className="mt-0.5 text-[11px] font-semibold text-slate-600 dark:text-slate-300">
                  {period.start_date} – {period.end_date}
                </div>
              </div>
              <span className="rounded-lg bg-white px-2 py-1 text-[10px] font-bold text-indigo-700 shadow-sm dark:bg-slate-900 dark:text-indigo-300">
                {formatInt(period.product_count)} produse în incentive
              </span>
            </div>
            <div className="mt-2 text-xs">
              <p className="text-[10px] font-semibold text-slate-400">
                Valoare acordată / unitate eligibilă
              </p>
              <p className="mt-0.5 font-black">
                {period.reward_values
                  .map((value) => `${formatInt(value)} RON`)
                  .join(" · ")}
              </p>
              <p className="mt-2 text-[10px] leading-relaxed text-slate-500 dark:text-slate-400">
                Se aplică valoarea produsului activă la data vânzării, după
                excluderea unităților promo. La 90–99,99% din target se acordă
                50%; de la 100%, integral.
              </p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function IncentiveCategoryCard({
  promoData,
  month,
}: {
  promoData: CampaignsPromotionsResponse | null;
  month: string;
}) {
  const rows: IncentiveCategoryBreakdown[] = [
    ...(promoData?.incentive_category_breakdown ?? []),
  ].sort(
    (left, right) =>
      right.qty - left.qty || left.label.localeCompare(right.label, "ro"),
  );
  if (!rows.length) return null;
  return (
    <div className="glass rounded-4xl border border-indigo-100 p-4 dark:border-indigo-900/30">
      <div className="mb-3 flex items-center justify-between gap-2">
        <div>
          <div className="flex items-center gap-2 text-indigo-600 dark:text-indigo-400">
            <BadgePercent size={16} />
            <span className="text-[11px] font-bold uppercase tracking-[0.22em]">
              Categorii incentive
            </span>
          </div>
          <p className="mt-1 text-[11px] text-slate-500">
            Cantitate și incentive: calificat / total.
          </p>
        </div>
        <ExportTableButton
          filename={`focus-incentive-categorii-${month}`}
          sheetName="Categorii incentive"
          rows={rows}
          columns={[
            { header: "Categorie", value: (row) => row.label },
            {
              header: "Cantitate calificata",
              value: (row) => row.qualified_qty,
              format: "integer",
            },
            {
              header: "Cantitate totala",
              value: (row) => row.qty,
              format: "integer",
            },
            {
              header: "Incentive calculat",
              value: (row) => row.value,
              format: "currency",
            },
            {
              header: "Incentive total",
              value: (row) => row.potential,
              format: "currency",
            },
          ]}
        />
      </div>
      <div className="grid gap-x-6 gap-y-2 md:grid-cols-2">
        {rows.map((row) => (
          <div key={row.label} className="min-w-0">
            <div
              className="text-xs font-bold text-slate-900 dark:text-white"
              title={row.label}
            >
              {row.label}
            </div>
            <div className="mt-1 grid grid-cols-2 gap-2 text-[10px] text-slate-500 dark:text-slate-400">
              <div>
                <span>Cant. calif./total</span>
                <strong className="ml-1 text-slate-800 dark:text-slate-100">
                  {formatInt(row.qualified_qty)} / {formatInt(row.qty)}
                </strong>
              </div>
              <div className="text-right">
                <span>Inc. calc./total</span>
                <strong className="ml-1 text-indigo-600 dark:text-indigo-300">
                  {formatInt(row.value)} / {formatInt(row.potential)} RON
                </strong>
              </div>
            </div>
            <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
              <div
                className="h-full rounded-full bg-indigo-500"
                style={{
                  width: `${row.qty > 0 ? (row.qualified_qty / row.qty) * 100 : 0}%`,
                }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
