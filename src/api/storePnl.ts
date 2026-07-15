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

export interface PnlAnnualPoint extends PnlMetrics {
  year: string;
  store_count: number;
  is_estimated: boolean;
}

export interface PnlStoreOption {
  company_name: string;
  site_code: string;
  location: string;
  regional: string;
  scope_company: string | null;
}

export interface PnlStore extends PnlMetrics {
  company: string;
  site_code: string;
  source_site_code: string;
  location: string;
  regional: string;
  has_estimates: boolean;
}

export interface PnlReconciliation {
  month: string;
  pnl_revenue: number;
  retail_sales_gross: number;
  retail_sales_net: number;
  difference_to_net: number;
  pnl_to_net_sales_pct: number | null;
}

export interface PnlOverview {
  start_month: string;
  end_month: string;
  company: string | null;
  site_code: string | null;
  site_company: string | null;
  regional: string | null;
  summary: PnlMetrics;
  monthly: PnlMonthlyPoint[];
  categories: Record<string, number>;
  stores: PnlStore[];
  reconciliation: PnlReconciliation[];
}

export interface PnlPermissions {
  can_view: boolean;
}

export async function getPnlPermissions(): Promise<PnlPermissions> {
  const { data } = await client.get<PnlPermissions>(
    "/api/store-pnl/permissions",
  );
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

export async function getPnlStores(company: string, regional = ""): Promise<PnlStoreOption[]> {
  const { data } = await client.get<{ stores: PnlStoreOption[] }>(
    "/api/store-pnl/stores",
    { params: { company: company || undefined, regional: regional || undefined } },
  );
  return data.stores;
}

export async function getPnlRegions(company: string): Promise<string[]> {
  const { data } = await client.get<{ regions: string[] }>(
    "/api/store-pnl/regions",
    { params: { company: company || undefined } },
  );
  return data.regions;
}

export async function getPnlAnnual(
  company: string,
  siteCode: string,
  siteCompany = "",
  regional = "",
): Promise<PnlAnnualPoint[]> {
  const { data } = await client.get<{ annual: PnlAnnualPoint[] }>(
    "/api/store-pnl/annual",
    {
      params: {
        company: company || undefined,
        site_code: siteCode || undefined,
        site_company: siteCompany || undefined,
        regional: regional || undefined,
      },
    },
  );
  return data.annual;
}

export async function getPnlOverview(
  startMonth: string,
  endMonth: string,
  company: string,
  siteCode = "",
  siteCompany = "",
  regional = "",
): Promise<PnlOverview> {
  const { data } = await client.get<PnlOverview>("/api/store-pnl/overview", {
    params: {
      start_month: startMonth,
      end_month: endMonth,
      company: company || undefined,
      site_code: siteCode || undefined,
      site_company: siteCompany || undefined,
      regional: regional || undefined,
    },
  });
  return data;
}
