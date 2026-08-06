import { Building2, Sparkles } from "lucide-react";
import { FirmaBadge } from "../../components/FirmaBadge";
import type { IncentiveTopAgent, PromoTopStore } from "../../api/generated/runtime-types";
import { formatCurrency, formatInt } from "../../lib/formatters";
import {
  achievementColor,
  achievementLabel,
  displayStoreName,
} from "./formatters";
import { SortableTable } from "./SortableTable";

export function IncentiveAgentsTable({
  rows,
  month,
}: {
  rows: IncentiveTopAgent[];
  month: string;
}) {
  return (
    <div className="glass min-w-0 rounded-4xl border border-indigo-100 bg-linear-to-br from-indigo-50 via-white to-white p-4 dark:border-indigo-900/30 dark:from-indigo-950/20 dark:via-slate-900 dark:to-slate-900 lg:rounded-2xl lg:p-3 xl:order-2">
      <div className="mb-3 flex items-center gap-2 text-indigo-600 dark:text-indigo-400">
        <Sparkles size={16} />
        <span className="text-[11px] font-bold uppercase tracking-[0.22em]">
          Agenti
        </span>
      </div>
      <SortableTable<IncentiveTopAgent>
        rows={rows}
        defaultSortKey="val_incentive"
        exportFilename={`focus-incentive-agenti-${month}`}
        exportSheetName="Agenti incentive"
        exportColumns={[
          { header: "#", value: (_row, index) => index + 1, format: "integer" },
          { header: "Agent", value: (row) => row.agent_name },
          { header: "Firma", value: (row) => row.firma },
          {
            header: "Magazin",
            value: (row) => displayStoreName(row.store_name),
          },
          {
            header: "%Prev.",
            value: (row) => row.achievement,
            format: "percent",
          },
          { header: "Cant.", value: (row) => row.qty_sold, format: "integer" },
          {
            header: "Val Inc.",
            value: (row) => row.val_incentive,
            format: "currency",
          },
          {
            header: "Incentive potential",
            value: (row) => row.incentive_potential ?? 0,
            format: "currency",
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
            key: "achievement",
            label: "%Prev.",
            align: "right",
            exportValue: (row) =>
              achievementLabel(row.achievement),
            render: (row) => (
              <span
                className={achievementColor(
                  row.achievement,
                )}
              >
                {achievementLabel(row.achievement)}
              </span>
            ),
          },
          {
            key: "qty_sold",
            label: "Cant.",
            align: "right",
            render: (row) => (
              <span className="text-slate-500">
                {formatInt(row.qty_sold)}
              </span>
            ),
          },
          {
            key: "val_incentive",
            label: "Val Inc.",
            align: "right",
            render: (row) => (
              <span
                className={
                  row.val_incentive > 0
                    ? "font-black text-indigo-600"
                    : "text-slate-400"
                }
              >
                {row.val_incentive > 0
                  ? formatCurrency(row.val_incentive)
                  : "0 RON"}
              </span>
            ),
          },
          {
            key: "incentive_potential",
            label: "Incentive potential",
            align: "right",
            render: (row) => (
              <span className="font-black text-emerald-600">
                {formatCurrency(
                  row.incentive_potential ?? 0,
                )}
              </span>
            ),
          },
        ]}
      />
    </div>
  );
}

export function IncentiveStoresTable({
  rows,
  month,
}: {
  rows: PromoTopStore[];
  month: string;
}) {
  return (
    <div className="glass min-w-0 rounded-4xl border border-indigo-100 bg-linear-to-br from-indigo-50 via-white to-white p-4 dark:border-indigo-900/30 dark:from-indigo-950/20 dark:via-slate-900 dark:to-slate-900 lg:rounded-2xl lg:p-3 xl:order-1">
      <div className="mb-3 flex items-center gap-2 text-indigo-600 dark:text-indigo-400">
        <Building2 size={16} />
        <span className="text-[11px] font-bold uppercase tracking-[0.22em]">
          Magazine
        </span>
      </div>
      <SortableTable<PromoTopStore>
        rows={rows}
        defaultSortKey="incentive_value"
        exportFilename={`focus-incentive-magazine-${month}`}
        exportSheetName="Magazine incentive"
        exportColumns={[
          { header: "#", value: (_row, index) => index + 1, format: "integer" },
          { header: "Firma", value: (row) => row.firma },
          {
            header: "Magazin",
            value: (row) => displayStoreName(row.store_name),
          },
          {
            header: "%Prev.",
            value: (row) => row.achievement,
            format: "percent",
          },
          { header: "Cant.", value: (row) => row.qty, format: "integer" },
          {
            header: "Val Inc.",
            value: (row) => row.incentive_value,
            format: "currency",
          },
          {
            header: "Incentive potential",
            value: (row) => row.incentive_potential ?? 0,
            format: "currency",
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
            render: (row) => <StoreName store={row} />,
          },
          {
            key: "achievement",
            label: "%Prev.",
            align: "right",
            exportValue: (row) =>
              achievementLabel(row.achievement),
            render: (row) => (
              <span
                className={achievementColor(row.achievement)}
              >
                {achievementLabel(row.achievement)}
              </span>
            ),
          },
          {
            key: "qty",
            label: "Cant.",
            align: "right",
            render: (row) => (
              <span className="text-slate-500">
                {formatInt(row.qty)}
              </span>
            ),
          },
          {
            key: "incentive_value",
            label: "Val Inc.",
            align: "right",
            render: (row) => {
              const value = row.incentive_value;
              return (
                <span
                  className={
                    value > 0 ? "font-black text-indigo-600" : "text-slate-400"
                  }
                >
                  {value > 0 ? formatCurrency(value) : "—"}
                </span>
              );
            },
          },
          {
            key: "incentive_potential",
            label: "Incentive potential",
            align: "right",
            render: (row) => (
              <span className="font-black text-emerald-600">
                {formatCurrency(
                  row.incentive_potential ?? 0,
                )}
              </span>
            ),
          },
        ]}
      />
    </div>
  );
}

function StoreName({ store }: { store: PromoTopStore }) {
  const displayName = store.store_name.includes(" - ")
    ? store.store_name.split(" - ").slice(1).join(" - ")
    : store.store_name;
  return (
    <span className="flex items-center">
      <FirmaBadge firma={store.firma} />
      <span
        className="max-w-[90px] truncate font-semibold"
        title={store.store_name}
      >
        {displayName}
      </span>
    </span>
  );
}
