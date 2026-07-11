import { client } from "./client";

export interface PnlMonth {
  month: string;
  has_actual: boolean;
  has_estimated: boolean;
}

export interface PnlMetrics {
  revenue: number;
  cogs: number;
  gross_margin: number;
  operating_costs: number;
  ebitda: number;
  depreciation: number;
  ebit: number;
}

export interface PnlMonthlyPoint extends PnlMetrics {
  month: string;
  is_estimated: boolean;
}

export interface PnlStore extends PnlMetrics {
  company: string;
  site_code: string;
  source_site_code: string;
  location: string;
  has_estimates: boolean;
}

export interface PnlOverview {
  start_month: string;
  end_month: string;
  company: string | null;
  summary: PnlMetrics;
  monthly: PnlMonthlyPoint[];
  categories: Record<string, number>;
  stores: PnlStore[];
}

export interface PnlPermissions {
  can_view: boolean;
}

export async function getPnlPermissions(): Promise<PnlPermissions> {
  const { data } = await client.get<PnlPermissions>("/api/store-pnl/permissions");
  if (
    !data
    || typeof data !== "object"
    || typeof data.can_view !== "boolean"
    || Object.keys(data).some((key) => key !== "can_view")
  ) {
    throw new Error("Invalid P&L permissions response");
  }
  return data;
}

export async function getPnlMonths(): Promise<PnlMonth[]> {
  const { data } = await client.get<{ months: PnlMonth[] }>(
    "/api/store-pnl/months",
  );
  return data.months;
}

export async function getPnlOverview(
  startMonth: string,
  endMonth: string,
  company: string,
): Promise<PnlOverview> {
  const { data } = await client.get<PnlOverview>("/api/store-pnl/overview", {
    params: {
      start_month: startMonth,
      end_month: endMonth,
      company: company || undefined,
    },
  });
  return data;
}
