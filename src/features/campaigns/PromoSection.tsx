import { BadgePercent, Building2, Sparkles } from "lucide-react";
import { FirmaBadge } from "../../components/FirmaBadge";
import type {
  CampaignsPromotionsResponse,
  PromoTopAgent,
  PromoTopStore,
} from "../../api/generated/runtime-types";
import { formatCurrency, formatInt } from "../../lib/formatters";
import { displayStoreName } from "./formatters";
import {
  CampaignMonthBar,
  EmptyCard,
  PromotionSelector,
} from "./CampaignControls";
import { SortableTable } from "./SortableTable";

export function PromoSection({
  data,
  month,
  months,
  currentMonth,
  selectedPromotionKey,
  onMonthChange,
  onPromotionChange,
}: {
  data: CampaignsPromotionsResponse | null;
  month: string;
  months: string[];
  currentMonth: string;
  selectedPromotionKey: string;
  onMonthChange: (month: string) => void;
  onPromotionChange: (key: string) => void;
}) {
  return (
    <>
      <div className="lg:hidden">
        <CampaignMonthBar
          title="Promotie"
          icon={BadgePercent}
          months={months}
          value={month}
          onChange={onMonthChange}
          currentMonth={currentMonth}
        />
      </div>
      {data && data.promotions.length > 1 && (
        <PromotionSelector
          promotions={data.promotions}
          selectedKey={selectedPromotionKey || data.selected_promotion_key}
          onSelect={onPromotionChange}
        />
      )}
      {!data?.has_active_promotion ? (
        <EmptyCard message={`Nu exista promotie activa in ${month}.`} />
      ) : (
        <PromoDetails data={data} month={month} />
      )}
    </>
  );
}

function PromoDetails({
  data,
  month,
}: {
  data: CampaignsPromotionsResponse;
  month: string;
}) {
  return (
    <>
      {data.promo_calculation_status === "partial" && (
        <div
          role="status"
          className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs font-semibold text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-200"
        >
          {data.calculation_warnings[0] ||
            "Calcul promo partial; perioada nevalidată nu este folosită pentru Incentive."}
        </div>
      )}
      <div className="glass rounded-4xl border border-amber-100 bg-linear-to-br from-amber-50 via-white to-white p-4 dark:border-amber-900/30 dark:from-amber-950/20 dark:via-slate-900 dark:to-slate-900 lg:grid lg:grid-cols-[minmax(0,2fr)_minmax(140px,1fr)_minmax(0,4fr)] lg:items-center lg:gap-4 lg:rounded-2xl">
        <div className="mb-3 flex items-center gap-2 text-amber-600 dark:text-amber-400 lg:hidden">
          <BadgePercent size={16} />
          <span className="text-[11px] font-bold uppercase tracking-[0.22em]">
            Promotii
          </span>
        </div>
        <div className="mb-1 lg:mb-0">
          <h4 className="text-base font-black tracking-tight">
            {data.promo_title || "Promotie"}
          </h4>
          {data.promo_description && (
            <p className="mt-1 text-xs text-slate-600 dark:text-slate-300">
              {data.promo_description}
            </p>
          )}
        </div>
        <div className="mb-3 lg:mb-0">
          <div className="text-3xl font-black">
            {formatInt(data.promo_qualifying_bons)}
          </div>
          <div className="text-[11px] font-semibold text-slate-500">
            bonuri calificate
          </div>
          <p className="mt-1 text-xs text-slate-500">
            Bonurile respectă mecanismul promoției; unitățile efective sunt
            raportate separat.
          </p>
        </div>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-4">
          <PromoMetric
            value={formatInt(data.promo_discounted_units)}
            label="Unități promo efective"
            accent
          />
          <PromoMetric
            value={formatCurrency(data.promo_discount_value ?? 0)}
            label="Valoare discount"
            accent
          />
          <PromoMetric
            value={formatInt(data.promo_active_stores)}
            label="Magazine"
          />
          <PromoMetric
            value={formatInt(data.promo_active_agents)}
            label="Agenti"
          />
        </div>
      </div>
      <div className="grid gap-3 xl:grid-cols-2">
        {data.top_stores.length > 0 && (
          <PromoStoresTable
            rows={data.top_stores}
            month={month}
            promotionKey={data.selected_promotion_key}
          />
        )}
        {(data.promo_agents ?? []).length > 0 && (
          <PromoAgentsTable
            rows={data.promo_agents ?? []}
            month={month}
            promotionKey={data.selected_promotion_key}
          />
        )}
      </div>
    </>
  );
}

function PromoMetric({
  value,
  label,
  accent = false,
}: {
  value: string;
  label: string;
  accent?: boolean;
}) {
  return (
    <div>
      <div className={`text-lg font-black ${accent ? "text-amber-600" : ""}`}>
        {value}
      </div>
      <div className="text-[10px] text-slate-500">{label}</div>
    </div>
  );
}

function PromoStoresTable({
  rows,
  month,
  promotionKey,
}: {
  rows: PromoTopStore[];
  month: string;
  promotionKey: string;
}) {
  return (
    <div className="glass min-w-0 rounded-4xl border border-amber-100 bg-linear-to-br from-amber-50 via-white to-white p-4 dark:border-amber-900/30 dark:from-amber-950/20 dark:via-slate-900 dark:to-slate-900 lg:rounded-2xl lg:p-3">
      <div className="mb-3 flex items-center gap-2 text-amber-600 dark:text-amber-400">
        <Building2 size={16} />
        <span className="text-[11px] font-bold uppercase tracking-[0.22em]">
          Magazine
        </span>
      </div>
      <SortableTable<PromoTopStore>
        rows={rows}
        defaultSortKey="promo_bons"
        exportFilename={`focus-promo-magazine-${month}-${promotionKey}`}
        exportSheetName="Magazine promo"
        exportColumns={[
          { header: "#", value: (_row, index) => index + 1, format: "integer" },
          { header: "Firma", value: (row) => row.firma },
          {
            header: "Magazin",
            value: (row) => displayStoreName(row.store_name),
          },
          {
            header: "Bonuri",
            value: (row) => row.promo_bons,
            format: "integer",
          },
        ]}
        columns={[
          {
            key: "rank",
            label: "#",
            sortable: false,
            render: (_row, index) => (
              <span className="font-bold text-slate-400">{index + 1}</span>
            ),
          },
          {
            key: "store_name",
            label: "Magazin",
            render: (row) => (
              <StoreName
                store={row}
                maxWidth="max-w-[150px] sm:max-w-[240px]"
              />
            ),
          },
          {
            key: "promo_bons",
            label: "Bonuri",
            align: "right",
            render: (row) => (
              <span className="font-black text-amber-600">
                {formatInt(row.promo_bons ?? 0)}
              </span>
            ),
          },
        ]}
      />
    </div>
  );
}

function PromoAgentsTable({
  rows,
  month,
  promotionKey,
}: {
  rows: PromoTopAgent[];
  month: string;
  promotionKey: string;
}) {
  return (
    <div className="glass min-w-0 rounded-4xl border border-amber-100 bg-linear-to-br from-amber-50 via-white to-white p-4 dark:border-amber-900/30 dark:from-amber-950/20 dark:via-slate-900 dark:to-slate-900 lg:rounded-2xl lg:p-3">
      <div className="mb-3 flex items-center gap-2 text-amber-600 dark:text-amber-400">
        <Sparkles size={16} />
        <span className="text-[11px] font-bold uppercase tracking-[0.22em]">
          Agenti
        </span>
      </div>
      <SortableTable<PromoTopAgent>
        rows={rows}
        defaultSortKey="promo_bons"
        exportFilename={`focus-promo-agenti-${month}-${promotionKey}`}
        exportSheetName="Agenti promo"
        exportColumns={[
          { header: "#", value: (_row, index) => index + 1, format: "integer" },
          { header: "Agent", value: (row) => row.agent_name },
          { header: "Firma", value: (row) => row.firma },
          {
            header: "Magazin",
            value: (row) => displayStoreName(row.store_name),
          },
          {
            header: "Bonuri",
            value: (row) => row.promo_bons,
            format: "integer",
          },
        ]}
        columns={[
          {
            key: "rank",
            label: "#",
            sortable: false,
            render: (_row, index) => (
              <span className="font-bold text-slate-400">{index + 1}</span>
            ),
          },
          {
            key: "agent_name",
            label: "Agent",
            render: (row) => (
              <span
                className="truncate font-semibold"
                title={row.agent_name}
              >
                {row.agent_name}
              </span>
            ),
          },
          {
            key: "store_name",
            label: "Magazin",
            render: (row) => (
              <StoreName
                store={row}
                maxWidth="max-w-[100px]"
              />
            ),
          },
          {
            key: "promo_bons",
            label: "Bonuri",
            align: "right",
            render: (row) => (
              <span className="font-black text-amber-600">
                {formatInt(row.promo_bons)}
              </span>
            ),
          },
        ]}
      />
    </div>
  );
}

function StoreName({
  store,
  maxWidth,
}: {
  store: Pick<PromoTopStore, "firma" | "store_name">;
  maxWidth: string;
}) {
  const displayName = store.store_name.includes(" - ")
    ? store.store_name.split(" - ").slice(1).join(" - ")
    : store.store_name;
  return (
    <span className="flex items-center">
      <FirmaBadge firma={store.firma} />
      <span
        className={`${maxWidth} truncate font-semibold`}
        title={store.store_name}
      >
        {displayName || "—"}
      </span>
    </span>
  );
}
