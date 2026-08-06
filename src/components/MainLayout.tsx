import { useEffect, useMemo, useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { Check, ChevronDown, Filter, Search, X } from 'lucide-react';
import { getFilterOptions } from '../api/filters';
import type { FilterOptions } from '../api/generated/runtime-types';
import { ALL_FIRMS, ALL_SCOPE, ALL_STORES, defaultAppFilters } from '../lib/filterValues';
import { cn } from '../lib/utils';
import { ALL_TABS, type ManagementTab, type TabId } from '../lib/tabs';
import type { AppFilters } from '../lib/appFilters';
import { DesktopSidebar } from './DesktopSidebar';
import { DesktopTopBar } from './DesktopTopBar';


interface FilterValueOption {
  label: string;
  value: string;
}

interface MainLayoutProps {
  children: React.ReactNode;
  activeTab: TabId;
  setActiveTab: (tab: TabId) => void;
  isFilterOpen: boolean;
  setIsFilterOpen: (open: boolean) => void;
  filters: AppFilters;
  setFilters: (filters: AppFilters) => void;
  filterMonth: string;
  theme: string;
  setTheme: (theme: string) => void;
  showFilterButton?: boolean;
  mgmtSubTab: ManagementTab;
  errorCount?: number;
  userEmail?: string;
  onLogout?: () => void;
  canAccessManagement?: boolean;
}

const emptyOptions: FilterOptions = {
  firme: [],
  regionali: [],
  asmi: [],
  magazine: [],
  agenti: [],
};

function selectedValues(value: string, allValue: string): string[] {
  if (!value || value === allValue) return [];
  return value.split(',').map((item) => item.trim()).filter(Boolean);
}

function joinedSelection(values: string[], allValue: string): string {
  return values.length > 0 ? values.join(',') : allValue;
}

export function MainLayout({
  children,
  activeTab,
  setActiveTab,
  isFilterOpen,
  setIsFilterOpen,
  filters,
  setFilters,
  filterMonth,
  theme,
  setTheme,
  showFilterButton = true,
  mgmtSubTab,
  errorCount = 0,
  userEmail,
  onLogout,
  canAccessManagement = true,
}: MainLayoutProps) {
  const [filterOptions, setFilterOptions] = useState<FilterOptions>(emptyOptions);

  useEffect(() => {
    if (!filterMonth) return;
    getFilterOptions(filterMonth)
      .then(setFilterOptions)
      .catch(() => setFilterOptions(emptyOptions));
  }, [filterMonth]);

  const filteredRegionals = useMemo(() => {
    if (filters.firma === ALL_FIRMS) {
      return filterOptions.regionali;
    }
    return Array.from(
      new Set(
        filterOptions.magazine
          .filter((item) => item.firma === filters.firma)
          .map((item) => item.regional)
      )
    ).sort();
  }, [filterOptions, filters.firma]);

  const selectedStores = useMemo(
    () => selectedValues(filters.magazin, ALL_STORES),
    [filters.magazin]
  );

  const filteredStores = useMemo(() => {
    return filterOptions.magazine
      .filter((item) => (filters.firma === ALL_FIRMS || item.firma === filters.firma))
      .filter((item) => (filters.rm === ALL_SCOPE || item.regional === filters.rm))
      .sort((a, b) => a.locatie.localeCompare(b.locatie));
  }, [filterOptions, filters.firma, filters.rm]);

  const filteredAgents = useMemo(() => {
    const uniqueAgents = new Map<string, (typeof filterOptions.agenti)[number]>();
    filterOptions.agenti
      .filter((item) => (filters.firma === ALL_FIRMS || item.firma === filters.firma))
      .filter((item) => (filters.rm === ALL_SCOPE || item.regional === filters.rm))
      .filter((item) => (selectedStores.length === 0 || selectedStores.includes(item.site_code)))
      .forEach((item) => {
        uniqueAgents.set(item.agent, item);
      });

    return Array.from(uniqueAgents.values())
      .map((item) => item.agent)
      .sort((a, b) => a.localeCompare(b));
  }, [filterOptions, filters.firma, filters.rm, selectedStores]);

  const resetFilters = () => {
    setFilters(defaultAppFilters());
  };

  const activeFilterCount = [filters.firma, filters.rm, filters.magazin, filters.agent].filter(
    (value) => value !== ALL_FIRMS && value !== ALL_SCOPE && value !== ALL_STORES
  ).length;
  const hasMobileFilters = showFilterButton && (
    (['hub', 'focus', 'agents'] as const).includes(activeTab as 'hub' | 'focus' | 'agents')
    || (activeTab === 'management' && mgmtSubTab === 'salarii')
  );

  return (
    <div className="flex h-dvh overflow-hidden bg-transparent">
      <DesktopSidebar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        theme={theme}
        setTheme={setTheme}
        errorCount={errorCount}
        canAccessManagement={canAccessManagement}
      />

      <div className="flex flex-col flex-1 min-w-0 min-h-0">
        <DesktopTopBar
          activeTab={activeTab}
          mgmtSubTab={mgmtSubTab}
          showFilterButton={showFilterButton}
          onOpenFilter={() => setIsFilterOpen(true)}
          filters={filters}
          userEmail={userEmail}
          onLogout={onLogout}
        />

        <main
          className={cn(
            'flex-1 min-h-0',
            'overflow-y-auto pb-24 lg:pb-6'
          )}
        >
          {/* Container centrat — layout desktop consistent pe toate taburile
              (ca Focus). Pe mobil nu are efect (viewport < max-w-6xl). */}
          <div className="mx-auto w-full max-w-6xl lg:max-w-[1600px]">
            {children}
          </div>
        </main>
      </div>

      <AnimatePresence>
        {isFilterOpen && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setIsFilterOpen(false)}
              className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-sm"
            />
            <motion.div
              initial={{ y: '100%' }}
              animate={{ y: 0 }}
              exit={{ y: '100%' }}
              transition={{ type: 'spring', damping: 24, stiffness: 180 }}
              className="mobile-filter-sheet fixed inset-x-0 bottom-0 z-50 mx-auto max-h-[88dvh] max-w-lg overflow-y-auto rounded-t-4xl bg-white p-4 shadow-2xl dark:bg-slate-900"
            >
              <div className="mb-4 flex items-center justify-between">
                <h3 className="text-lg font-bold">Filtre active</h3>
                <button
                  onClick={() => setIsFilterOpen(false)}
                  aria-label="Inchide"
                  className="flex h-11 w-11 items-center justify-center rounded-full bg-slate-100 dark:bg-slate-800"
                >
                  <X size={16} />
                </button>
              </div>

              <div className="space-y-3">
                <FilterSelect
                  label="Firma"
                  value={filters.firma}
                  values={[
                    { label: ALL_FIRMS, value: ALL_FIRMS },
                    ...filterOptions.firme.map((item) => ({ label: item, value: item })),
                  ]}
                  onChange={(value) =>
                    setFilters({
                      ...filters,
                      firma: value,
                      rm: ALL_SCOPE,
                      magazin: ALL_STORES,
                      agent: ALL_SCOPE,
                    })
                  }
                />
                <FilterSelect
                  label="Manager"
                  value={filters.rm}
                  values={[
                    { label: ALL_SCOPE, value: ALL_SCOPE },
                    ...filteredRegionals.map((item) => ({ label: item, value: item })),
                  ]}
                  onChange={(value) =>
                    setFilters({
                      ...filters,
                      rm: value,
                      magazin: ALL_STORES,
                      agent: ALL_SCOPE,
                    })
                  }
                />
                <FilterMultiSelect
                  label="Magazin"
                  selectedSummaryLabel="magazine selectate"
                  value={filters.magazin}
                  allLabel={ALL_STORES}
                  allValue={ALL_STORES}
                  values={[
                    ...filteredStores.map((item) => ({
                      label: `${item.locatie} (${item.site_code})`,
                      value: item.site_code,
                    })),
                  ]}
                  onChange={(value) =>
                    setFilters({
                      ...filters,
                      magazin: value,
                      agent: ALL_SCOPE,
                    })
                  }
                />
                <FilterMultiSelect
                  label="Agent"
                  selectedSummaryLabel="agenti selectati"
                  value={filters.agent}
                  allLabel={ALL_SCOPE}
                  allValue={ALL_SCOPE}
                  values={[
                    ...filteredAgents.map((item) => ({ label: item, value: item })),
                  ]}
                  onChange={(value) => setFilters({ ...filters, agent: value })}
                />
              </div>

              <div className="mt-5 flex gap-2">
                <button
                  onClick={resetFilters}
                  className="flex-1 rounded-2xl bg-slate-100 px-4 py-3 text-xs font-bold dark:bg-slate-800"
                >
                  Reseteaza
                </button>
                <button
                  onClick={() => setIsFilterOpen(false)}
                  className="flex-2 rounded-2xl bg-indigo-600 px-4 py-3 text-xs font-bold text-white shadow-lg shadow-indigo-500/30"
                >
                  Aplica
                </button>
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>

      <div className="mobile-bottom-nav lg:hidden fixed inset-x-0 bottom-0 z-30 mx-auto max-w-6xl px-3 pt-2">
        <div className="glass flex items-center justify-around rounded-2xl p-1.5">
          {ALL_TABS.filter((tab) => canAccessManagement || tab.id !== 'management').map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={cn(
                  'relative flex min-h-12 min-w-14 flex-1 flex-col items-center justify-center rounded-xl transition-all',
                  isActive ? 'text-indigo-600 dark:text-indigo-400' : 'text-slate-500'
                )}
              >
                {isActive && (
                  <motion.div
                    layoutId="active-tab"
                    className="absolute inset-0 rounded-xl bg-indigo-100 dark:bg-indigo-500/20"
                  />
                )}
                <div className="relative z-10 mb-0.5">
                  <Icon size={18} />
                  {errorCount > 0 && tab.id === 'settings' && (
                    <span className="absolute -right-2 -top-1.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-500 px-0.5 text-[9px] font-bold text-white">
                      {errorCount > 9 ? '9+' : errorCount}
                    </span>
                  )}
                </div>
                <span className="relative z-10 text-[10px] font-semibold">{tab.label}</span>
              </button>
            );
          })}
        </div>
      </div>

      {hasMobileFilters && (
        <button
          type="button"
          onClick={() => setIsFilterOpen(true)}
          aria-label={activeFilterCount > 0 ? `Filtre, ${activeFilterCount} active` : 'Filtre'}
          className="mobile-floating-filter lg:hidden fixed right-4 z-40 flex h-11 w-11 items-center justify-center rounded-full border-2 border-white/95 bg-indigo-600 text-white shadow-[0_8px_22px_rgba(49,46,129,0.38),0_2px_6px_rgba(15,23,42,0.28)] transition hover:bg-indigo-700 active:translate-y-px active:bg-indigo-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300 focus-visible:ring-offset-2 dark:border-slate-950/80 dark:bg-indigo-500 dark:hover:bg-indigo-400 dark:active:bg-indigo-400 dark:focus-visible:ring-indigo-300 dark:focus-visible:ring-offset-slate-950"
        >
          <Filter size={17} />
          {activeFilterCount > 0 && (
            <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-amber-400 px-1 text-[9px] font-black text-slate-950 ring-2 ring-white dark:bg-amber-300 dark:ring-slate-950">
              {activeFilterCount > 9 ? '9+' : activeFilterCount}
            </span>
          )}
        </button>
      )}

    </div>
  );
}

function FilterSelect({
  label,
  value,
  values,
  onChange,
}: {
  label: string;
  value: string;
  values: FilterValueOption[];
  onChange: (value: string) => void;
}) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-xs font-bold">{label}</span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-3 py-3 text-xs outline-none dark:border-slate-700 dark:bg-slate-800"
      >
        {values.map((item) => (
          <option key={item.value} value={item.value}>
            {item.label}
          </option>
        ))}
      </select>
    </label>
  );
}

function FilterMultiSelect({
  label,
  selectedSummaryLabel,
  value,
  values,
  allLabel,
  allValue,
  onChange,
}: {
  label: string;
  selectedSummaryLabel: string;
  value: string;
  values: FilterValueOption[];
  allLabel: string;
  allValue: string;
  onChange: (value: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState('');
  const selected = selectedValues(value, allValue);
  const filteredValues = values.filter((item) =>
    item.label.toLowerCase().includes(search.trim().toLowerCase())
  );
  const selectedSet = new Set(selected);
  const summary =
    selected.length === 0
      ? allLabel
      : selected.length === 1
        ? values.find((item) => item.value === selected[0])?.label ?? selected[0]
        : `${selected.length} ${selectedSummaryLabel}`;

  const updateSelection = (next: string[]) => {
    onChange(joinedSelection(next, allValue));
  };

  const toggleValue = (itemValue: string) => {
    const next = selectedSet.has(itemValue)
      ? selected.filter((entry) => entry !== itemValue)
      : [...selected, itemValue];
    updateSelection(next);
  };

  return (
    <div className="block">
      <span className="mb-1.5 block text-xs font-bold">{label}</span>
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        className="flex w-full items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-slate-50 px-3 py-3 text-left text-xs outline-none dark:border-slate-700 dark:bg-slate-800"
      >
        <span className="truncate">{summary}</span>
        <ChevronDown size={14} className={cn('shrink-0 transition-transform', open && 'rotate-180')} />
      </button>
      {open && (
        <div className="mt-2 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-xl dark:border-slate-700 dark:bg-slate-900">
          <div className="flex items-center gap-2 border-b border-slate-100 px-3 py-2 dark:border-slate-800">
            <Search size={14} className="text-slate-400" />
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder={`Cauta ${label.toLowerCase()}...`}
              className="min-w-0 flex-1 bg-transparent text-xs outline-none"
            />
          </div>
          <div className="max-h-64 overflow-y-auto py-1">
            <button
              type="button"
              onClick={() => updateSelection([])}
              className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs font-bold text-slate-700 hover:bg-slate-50 dark:text-slate-200 dark:hover:bg-slate-800"
            >
              <span className="flex h-4 w-4 items-center justify-center rounded border border-slate-300 bg-white dark:border-slate-600 dark:bg-slate-900">
                {selected.length === 0 && <Check size={12} />}
              </span>
              {allLabel}
            </button>
            {filteredValues.map((item) => {
              const checked = selectedSet.has(item.value);
              return (
                <button
                  key={item.value}
                  type="button"
                  onClick={() => toggleValue(item.value)}
                  className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs hover:bg-slate-50 dark:hover:bg-slate-800"
                >
                  <span
                    className={cn(
                      'flex h-4 w-4 shrink-0 items-center justify-center rounded border',
                      checked
                        ? 'border-indigo-500 bg-indigo-500 text-white'
                        : 'border-slate-300 bg-white dark:border-slate-600 dark:bg-slate-900'
                    )}
                  >
                    {checked && <Check size={12} />}
                  </span>
                  <span className="truncate">{item.label}</span>
                </button>
              );
            })}
            {filteredValues.length === 0 && (
              <div className="px-3 py-3 text-xs text-slate-500">Niciun rezultat.</div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
