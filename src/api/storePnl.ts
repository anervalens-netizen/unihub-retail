import { generatedGet } from './generated/client';
import type { RetailOperationQueries } from './generated/contracts';
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
  const data = await generatedGet('pnl_permissions_api_store_pnl_permissions_get');
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
  const data = await generatedGet('months_api_store_pnl_months_get', { signal });
  return data.months;
}

export async function getPnlStores(company: string, regional = '', signal?: AbortSignal): Promise<PnlStoreOption[]> {
  const params: RetailOperationQueries['stores_api_store_pnl_stores_get'] = {
    company: company || undefined,
    regional: regional || undefined,
  };
  const data = await generatedGet('stores_api_store_pnl_stores_get', {
    params,
    signal,
  });
  return data.stores;
}

export async function getPnlRegions(company: string, signal?: AbortSignal): Promise<string[]> {
  const params: RetailOperationQueries['regions_api_store_pnl_regions_get'] = {
    company: company || undefined,
  };
  const data = await generatedGet('regions_api_store_pnl_regions_get', {
    params,
    signal,
  });
  return data.regions;
}

export async function getPnlAnnual(
  company: string,
  siteCode: string,
  siteCompany = '',
  regional = '',
  signal?: AbortSignal,
): Promise<PnlAnnualPoint[]> {
  const params: RetailOperationQueries['annual_api_store_pnl_annual_get'] = {
    company: company || undefined,
    site_code: siteCode || undefined,
    site_company: siteCompany || undefined,
    regional: regional || undefined,
  };
  const data = await generatedGet('annual_api_store_pnl_annual_get', {
    params,
    signal,
  });
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
  const params: RetailOperationQueries['overview_api_store_pnl_overview_get'] = {
    start_month: startMonth,
    end_month: endMonth,
    company: company || undefined,
    site_code: siteCode || undefined,
    site_company: siteCompany || undefined,
    regional: regional || undefined,
  };
  return await generatedGet('overview_api_store_pnl_overview_get', {
    params,
    signal,
  });
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
