import FirmaBadge from "../../components/FirmaBadge";
import type { AgentStat, RegionalStat, StoreStat } from "../../api/generated/runtime-types";
import { formatAmount, formatInt, formatPercent } from "../../lib/formatters";
import type { BreakdownColumn } from "./BreakdownTable";
import type { PerformanceSelection } from "./PerformanceDetailDrawer";
import type {
  AgentSortKey,
  RegionalSortKey,
  StoreSortKey,
} from "./dashboardTypes";

type Column<Key extends string> = { key: Key; label: string };
const COMPACT_TD_CLASS =
  "px-1.5 py-1 whitespace-nowrap align-middle leading-tight";
const COMPACT_NUM_TD_CLASS = `${COMPACT_TD_CLASS} text-right tabular-nums`;
const COMPACT_TEXT_TD_CLASS = `${COMPACT_TD_CLASS} text-left`;

const STORE_COLUMNS: Column<StoreSortKey>[] = [
  { key: "locatie", label: "Magazin" },
  { key: "site_code", label: "Firma" },
  { key: "target", label: "Target" },
  { key: "total_vanzari", label: "Vanzari" },
  { key: "proc_realizare_target", label: "Procent" },
  { key: "forecast_target_pct", label: "Forecast%" },
  { key: "promo_qty", label: "Promo" },
  { key: "incentive_qty", label: "Incentive" },
  { key: "qty_total", label: "Cantitate" },
  { key: "medie_produs", label: "Medie produs" },
  { key: "nr_bonuri", label: "Nr bonuri" },
  { key: "proc_bon2acc", label: "ProcBon2Acc" },
  { key: "prc_focus_acc_qty", label: "Focus%" },
  { key: "return_receipt_count", label: "Retururi" },
  { key: "nr_agenti", label: "Agenti" },
  { key: "zile_active", label: "Zile active" },
];
const AGENT_COLUMNS: Column<AgentSortKey>[] = [
  { key: "agent", label: "Agent" },
  { key: "locatie", label: "Magazin" },
  { key: "target", label: "Target" },
  { key: "total_vanzari", label: "Vanzari" },
  { key: "proc_realizare_target", label: "Procent" },
  { key: "promo_qty", label: "Promo" },
  { key: "incentive_qty", label: "Incentive" },
  { key: "acc_qty_realizat", label: "Cantitate" },
  { key: "medie_produs", label: "Medie produs" },
  { key: "nr_bonuri", label: "Nr bonuri" },
  { key: "proc_bon2acc", label: "ProcBon2Acc" },
  { key: "prc_focus_acc_qty", label: "Focus%" },
  { key: "return_receipt_count", label: "Retururi" },
  { key: "zile_lucrate", label: "Zile lucrate" },
  { key: "medie_zilnica", label: "Medie zilnica" },
];
const REGIONAL_COLUMNS: Column<RegionalSortKey>[] = [
  { key: "regional", label: "Regional" },
  { key: "target", label: "Target" },
  { key: "total_vanzari", label: "Vanzari" },
  { key: "proc_realizare_target", label: "Procent" },
  { key: "forecast_target_pct", label: "Forecast%" },
  { key: "promo_qty", label: "Promo" },
  { key: "incentive_qty", label: "Incentive" },
  { key: "qty_total", label: "Cantitate" },
  { key: "medie_produs", label: "Medie produs" },
  { key: "nr_bonuri", label: "Nr bonuri" },
  { key: "proc_bon2acc", label: "ProcBon2Acc" },
  { key: "prc_focus_acc_qty", label: "Focus%" },
];

export const CURRENT_REGIONAL_COLUMNS = REGIONAL_COLUMNS.filter(
  (column) => column.key !== "incentive_qty",
);
export const CURRENT_STORE_COLUMNS = STORE_COLUMNS.filter(
  (column) => column.key !== "site_code" && column.key !== "incentive_qty",
);
export const CURRENT_AGENT_COLUMNS = AGENT_COLUMNS.filter(
  (column) => column.key !== "incentive_qty",
);
export const HIST_REGIONAL_COLUMNS = REGIONAL_COLUMNS.filter(
  (column) =>
    ![
      "promo_qty",
      "incentive_qty",
      "forecast_target_pct",
      "medie_produs",
    ].includes(column.key),
);
export const HIST_STORE_COLUMNS = STORE_COLUMNS.filter(
  (column) =>
    ![
      "site_code",
      "promo_qty",
      "incentive_qty",
      "forecast_target_pct",
      "medie_produs",
    ].includes(column.key),
);
export const HIST_AGENT_COLUMNS = AGENT_COLUMNS.filter(
  (column) =>
    !["promo_qty", "incentive_qty", "medie_produs"].includes(column.key),
);
export const STORE_ASC_SORT_KEYS: StoreSortKey[] = ["locatie", "site_code"];
export const AGENT_ASC_SORT_KEYS: AgentSortKey[] = ["locatie", "agent"];
export const REGIONAL_ASC_SORT_KEYS: RegionalSortKey[] = ["regional"];

function PromoMetric({ qty, discount }: { qty: number; discount: number }) {
  return (
    <span className="inline-flex flex-col items-end leading-[11px] lg:leading-tight">
      <span className="font-semibold">{formatInt(qty)} buc.</span>
      <span className="text-[10px] font-semibold text-amber-600 dark:text-amber-400">
        {formatAmount(discount)} RON
      </span>
    </span>
  );
}

export function regionalBreakdownColumns(
  columns: Column<RegionalSortKey>[],
  onOpen?: (selection: PerformanceSelection) => void,
): BreakdownColumn<RegionalStat, RegionalSortKey>[] {
  return columns.map((column, index) => ({
    ...column,
    headerClassName: index === 0 ? "w-24 max-w-24" : "max-w-[4.5rem]",
    cellClassName:
      column.key === "regional"
        ? `max-w-24 truncate font-semibold ${COMPACT_TEXT_TD_CLASS}`
        : column.key === "proc_realizare_target"
          ? `${COMPACT_NUM_TD_CLASS} font-bold text-indigo-600`
          : column.key === "forecast_target_pct"
            ? `${COMPACT_NUM_TD_CLASS} font-bold text-slate-700 dark:text-slate-200`
            : COMPACT_NUM_TD_CLASS,
    render: (row) => {
      if (column.key === "regional")
        return onOpen ? (
          <button
            type="button"
            onClick={() => onOpen({ level: "regional", key: row.regional })}
            className="max-w-full truncate text-left font-semibold text-indigo-700 underline-offset-2 hover:underline dark:text-indigo-300"
            title="Detalii performanta"
          >
            {row.regional}
          </button>
        ) : (
          row.regional
        );
      if (
        column.key === "target" ||
        column.key === "total_vanzari" ||
        column.key === "medie_produs"
      )
        return formatAmount(row[column.key] ?? 0);
      if (column.key === "promo_qty")
        return (
          <PromoMetric
            qty={row.promo_qty}
            discount={row.promo_discount_value ?? 0}
          />
        );
      if (
        column.key === "proc_realizare_target" ||
        column.key === "forecast_target_pct" ||
        column.key === "proc_bon2acc" ||
        column.key === "prc_focus_acc_qty"
      )
        return formatPercent(row[column.key] ?? null);
      return formatInt(row[column.key] ?? 0);
    },
  }));
}

export function storeBreakdownColumns(
  columns: Column<StoreSortKey>[],
  onOpen?: (selection: PerformanceSelection) => void,
): BreakdownColumn<StoreStat, StoreSortKey>[] {
  return columns.map((column, index) => ({
    ...column,
    headerClassName: index === 0 ? "w-32 max-w-32" : "max-w-[4.5rem]",
    cellClassName:
      column.key === "locatie"
        ? `max-w-32 truncate font-semibold ${COMPACT_TEXT_TD_CLASS}`
        : column.key === "proc_realizare_target"
          ? `${COMPACT_NUM_TD_CLASS} font-bold text-indigo-600`
          : column.key === "forecast_target_pct"
            ? `${COMPACT_NUM_TD_CLASS} font-bold text-slate-700 dark:text-slate-200`
            : column.key === "return_receipt_count"
              ? `${COMPACT_NUM_TD_CLASS} font-bold text-rose-600 dark:text-rose-400`
              : COMPACT_NUM_TD_CLASS,
    render: (row) => {
      if (column.key === "locatie") {
        const label = (
          <>
            <FirmaBadge firma={row.firma} />
            <span className="truncate">{row.locatie}</span>
          </>
        );
        return onOpen ? (
          <button
            type="button"
            onClick={() => onOpen({ level: "store", key: row.site_code })}
            className="inline-flex min-w-0 max-w-full items-center text-left font-semibold text-indigo-700 underline-offset-2 hover:underline dark:text-indigo-300"
            title="Detalii performanta"
          >
            {label}
          </button>
        ) : (
          <span className="inline-flex min-w-0 items-center">{label}</span>
        );
      }
      if (column.key === "site_code") return row.firma;
      if (
        column.key === "target" ||
        column.key === "total_vanzari" ||
        column.key === "medie_zilnica" ||
        column.key === "medie_produs"
      )
        return formatAmount(
          column.key === "medie_zilnica"
            ? row.zile_active > 0
              ? row.total_vanzari / row.zile_active
              : 0
            : (row[column.key] ?? 0),
        );
      if (column.key === "promo_qty")
        return (
          <PromoMetric
            qty={row.promo_qty}
            discount={row.promo_discount_value ?? 0}
          />
        );
      if (
        column.key === "proc_realizare_target" ||
        column.key === "forecast_target_pct" ||
        column.key === "proc_bon2acc" ||
        column.key === "prc_focus_acc_qty"
      )
        return formatPercent(row[column.key] ?? null);
      return formatInt(row[column.key] ?? 0);
    },
  }));
}

export function agentBreakdownColumns(
  columns: Column<AgentSortKey>[],
  onOpen?: (selection: PerformanceSelection) => void,
): BreakdownColumn<AgentStat, AgentSortKey>[] {
  return columns.map((column, index) => ({
    ...column,
    headerClassName:
      index === 0
        ? "w-20 max-w-20"
        : index === 1
          ? "w-28 max-w-28"
          : "max-w-[4.5rem]",
    cellClassName:
      column.key === "agent"
        ? `max-w-20 truncate font-bold ${COMPACT_TEXT_TD_CLASS}`
        : column.key === "locatie"
          ? `max-w-28 truncate text-slate-500 ${COMPACT_TEXT_TD_CLASS}`
          : column.key === "total_vanzari"
            ? `${COMPACT_NUM_TD_CLASS} font-bold text-indigo-600`
            : column.key === "return_receipt_count"
              ? `${COMPACT_NUM_TD_CLASS} font-bold text-rose-600 dark:text-rose-400`
              : COMPACT_NUM_TD_CLASS,
    render: (row) => {
      if (column.key === "agent")
        return onOpen ? (
          <button
            type="button"
            onClick={() =>
              onOpen({
                level: "agent",
                key: row.agent,
                site_code: row.site_code,
              })
            }
            className="max-w-full truncate text-left font-bold text-indigo-700 underline-offset-2 hover:underline dark:text-indigo-300"
            title="Detalii performanta"
          >
            {row.agent}
          </button>
        ) : (
          row.agent
        );
      if (column.key === "locatie") return row.locatie;
      if (
        column.key === "target" ||
        column.key === "total_vanzari" ||
        column.key === "medie_zilnica" ||
        column.key === "medie_produs"
      )
        return formatAmount(
          column.key === "medie_zilnica"
            ? row.zile_lucrate > 0
              ? row.total_vanzari / row.zile_lucrate
              : 0
            : (row[column.key] ?? 0),
        );
      if (column.key === "promo_qty")
        return (
          <PromoMetric
            qty={row.promo_qty}
            discount={row.promo_discount_value ?? 0}
          />
        );
      if (
        column.key === "proc_realizare_target" ||
        column.key === "proc_bon2acc" ||
        column.key === "prc_focus_acc_qty"
      )
        return formatPercent(row[column.key] ?? null);
      return formatInt(row[column.key] ?? 0);
    },
  }));
}
