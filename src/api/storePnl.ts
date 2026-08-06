import { generatedGet } from './generated/client';
import type {
  PnlAnnualPoint,
  PnlMetrics,
  PnlMonth,
  PnlOverview,
  PnlPermissions,
  PnlReconciliation,
  PnlStore,
  PnlStoreOption,
  PnlMonthlyPoint,
} from './generated/runtime-types';

export async function getPnlPermissions(): Promise<PnlPermissions> {
  const data = await generatedGet('pnl_permissions_api_store_pnl_permissions_get') as PnlPermissions;
  if (
    !data
    || typeof data !== 'object'
    || typeof data.can_view !== 'boolean'
    || Object.keys(data).some((key) => key !== 'can_view')
  ) {
    throw new Error('Invalid P&L permissions response');
  }
  return data;
}

export async function getPnlMonths(signal?: AbortSignal): Promise<PnlMonth[]> {
  const data = await generatedGet('months_api_store_pnl_months_get', { signal }) as { months: PnlMonth[] };
  return data.months;
}

export async function getPnlStores(company: string, regional = '', signal?: AbortSignal): Promise<PnlStoreOption[]> {
  const data = await generatedGet('stores_api_store_pnl_stores_get', {
    params: { company: company || undefined, regional: regional || undefined },
    signal,
  }) as { stores: PnlStoreOption[] };
  return data.stores;
}

export async function getPnlRegions(company: string, signal?: AbortSignal): Promise<string[]> {
  const data = await generatedGet('regions_api_store_pnl_regions_get', {
    params: { company: company || undefined },
    signal,
  }) as { regions: string[] };
  return data.regions;
}

export async function getPnlAnnual(
  company: string,
  siteCode: string,
  siteCompany = '',
  regional = '',
  signal?: AbortSignal,
): Promise<PnlAnnualPoint[]> {
  const data = await generatedGet('annual_api_store_pnl_annual_get', {
    params: {
      company: company || undefined,
      site_code: siteCode || undefined,
      site_company: siteCompany || undefined,
      regional: regional || undefined,
    },
    signal,
  }) as { annual: PnlAnnualPoint[] };
  return data.annual;
}

export async function getPnlOverview(
  startMonth: string,
  endMonth: string,
  company: string,
  siteCode = '',
  siteCompany = '',
  regional = '',
  signal?: AbortSignal,
): Promise<PnlOverview> {
  return await generatedGet('overview_api_store_pnl_overview_get', {
    params: {
      start_month: startMonth,
      end_month: endMonth,
      company: company || undefined,
      site_code: siteCode || undefined,
      site_company: siteCompany || undefined,
      regional: regional || undefined,
    },
    signal,
  }) as PnlOverview;
}

export type {
  PnlAnnualPoint,
  PnlMetrics,
  PnlMonth,
  PnlMonthlyPoint,
  PnlOverview,
  PnlPermissions,
  PnlReconciliation,
  PnlStore,
  PnlStoreOption,
};
