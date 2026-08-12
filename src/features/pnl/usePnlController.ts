import { useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';

import { getPnlAnnual, getPnlMonths, getPnlOverview, getPnlRegions, getPnlStores } from '../../api/storePnl';
import { defaultPnlRange, monthlyVariance, pnlStoreOptionValue } from './model';

export function usePnlController() {
  const [startMonth, setStartMonth] = useState('');
  const [endMonth, setEndMonth] = useState('');
  const [company, setCompany] = useState('');
  const [regional, setRegional] = useState('');
  const [storeScope, setStoreScope] = useState('');
  const [storeSearch, setStoreSearch] = useState('');
  const monthsQuery = useQuery({ queryKey: ['store-pnl-months'], queryFn: ({ signal }) => getPnlMonths(signal), staleTime: 5 * 60_000 });
  useEffect(() => {
    if (!monthsQuery.data?.length || endMonth) return;
    const range = defaultPnlRange(monthsQuery.data.map((item) => item.month));
    setStartMonth(range.start); setEndMonth(range.end);
  }, [monthsQuery.data, endMonth]);
  const storesQuery = useQuery({ queryKey: ['store-pnl-stores', company, regional], queryFn: ({ signal }) => getPnlStores(company, regional, signal), staleTime: 5 * 60_000 });
  const regionsQuery = useQuery({ queryKey: ['store-pnl-regions', company], queryFn: ({ signal }) => getPnlRegions(company, signal), staleTime: 5 * 60_000 });
  const selectedStore = useMemo(() => storesQuery.data?.find((store) => pnlStoreOptionValue(store) === storeScope), [storeScope, storesQuery.data]);
  const siteCode = selectedStore?.site_code ?? '';
  const siteCompany = selectedStore?.scope_company ?? '';
  const overviewQuery = useQuery({
    queryKey: ['store-pnl-overview', startMonth, endMonth, company, regional, siteCode, siteCompany],
    queryFn: ({ signal }) => getPnlOverview(startMonth, endMonth, company, siteCode, siteCompany, regional, signal),
    enabled: Boolean(startMonth && endMonth),
  });
  const annualQuery = useQuery({ queryKey: ['store-pnl-annual', company, regional, siteCode, siteCompany], queryFn: ({ signal }) => getPnlAnnual(company, siteCode, siteCompany, regional, signal) });
  const data = overviewQuery.data;
  const variance = useMemo(() => monthlyVariance(data?.monthly ?? []), [data?.monthly]);
  const reconciliationWarnings = useMemo(() => data?.reconciliation.filter((item) => item.retail_sales_net !== 0 && Math.abs(item.difference_to_net / item.retail_sales_net) >= 0.05) ?? [], [data]);
  const filteredStores = useMemo(() => {
    const needle = storeSearch.trim().toLocaleLowerCase('ro-RO');
    if (!needle) return data?.stores ?? [];
    return (data?.stores ?? []).filter((store) => `${store.location} ${store.site_code} ${store.company}`.toLocaleLowerCase('ro-RO').includes(needle));
  }, [data?.stores, storeSearch]);
  const selectCompany = (value: string) => { setCompany(value); setRegional(''); setStoreScope(''); };
  const selectRegional = (value: string) => { setRegional(value); setStoreScope(''); };
  return { startMonth, setStartMonth, endMonth, setEndMonth, company, selectCompany, regional, selectRegional, storeScope, setStoreScope, storeSearch, setStoreSearch, monthsQuery, storesQuery, regionsQuery, selectedStore, overviewQuery, annualQuery, data, variance, reconciliationWarnings, filteredStores, singleReconciliation: data?.reconciliation.length === 1 ? data.reconciliation[0] : undefined };
}

export type PnlController = ReturnType<typeof usePnlController>;
