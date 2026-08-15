import { useEffect, useMemo, useState } from 'react';

import { getFilterOptions } from '../api/filters';
import type { FilterOptions } from '../api/generated/runtime-types';
import type { AppFilters } from '../lib/appFilters';
import { ALL_FIRMS, ALL_SCOPE, defaultAppFilters } from '../lib/filterValues';
import type { ManagementTab, TabId } from '../lib/tabs';

const EMPTY_OPTIONS: FilterOptions = { firme: [], regionali: [], asmi: [], magazine: [], agenti: [] };

export function useMainLayoutFilters({
  filterMonth, filters, setFilters, activeTab, mgmtSubTab, showFilterButton,
}: {
  filterMonth: string;
  filters: AppFilters;
  setFilters: (filters: AppFilters) => void;
  activeTab: TabId;
  mgmtSubTab: ManagementTab;
  showFilterButton: boolean;
}) {
  const [options, setOptions] = useState<FilterOptions>(EMPTY_OPTIONS);
  useEffect(() => {
    if (!filterMonth) return;
    getFilterOptions(filterMonth).then(setOptions).catch(() => setOptions(EMPTY_OPTIONS));
  }, [filterMonth]);
  const regionals = useMemo(() => {
    if (filters.firma === ALL_FIRMS) return options.regionali;
    return Array.from(new Set(options.magazine.filter((item) => item.firma === filters.firma).map((item) => item.regional))).sort();
  }, [options, filters.firma]);
  const stores = useMemo(() => options.magazine
    .filter((item) => filters.firma === ALL_FIRMS || item.firma === filters.firma)
    .filter((item) => filters.rm === ALL_SCOPE || item.regional === filters.rm)
    .sort((left, right) => left.locatie.localeCompare(right.locatie)), [options, filters.firma, filters.rm]);
  const agents = useMemo(() => {
    const unique = new Map<string, (typeof options.agenti)[number]>();
    options.agenti
      .filter((item) => filters.firma === ALL_FIRMS || item.firma === filters.firma)
      .filter((item) => filters.rm === ALL_SCOPE || item.regional === filters.rm)
      .filter((item) => filters.magazin.length === 0 || filters.magazin.includes(item.site_code))
      .forEach((item) => unique.set(item.agent, item));
    return Array.from(unique.values()).map((item) => item.agent).sort((left, right) => left.localeCompare(right));
  }, [options, filters.firma, filters.rm, filters.magazin]);
  const activeCount = Number(filters.firma !== ALL_FIRMS) + Number(filters.rm !== ALL_SCOPE)
    + Number(filters.magazin.length > 0) + Number(filters.agent.length > 0);
  const hasMobileFilters = showFilterButton && (
    (['hub', 'focus', 'agents'] as const).includes(activeTab as 'hub' | 'focus' | 'agents')
    || (activeTab === 'management' && mgmtSubTab === 'salarii')
  );
  return {
    options, regionals, stores, agents, activeCount, hasMobileFilters,
    reset: () => setFilters(defaultAppFilters()),
  };
}

export type MainLayoutFilterModel = ReturnType<typeof useMainLayoutFilters>;
