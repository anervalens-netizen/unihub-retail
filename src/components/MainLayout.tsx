import { useEffect, useMemo, useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { Bot, Briefcase, Filter, LayoutDashboard, LogOut, Moon, Settings, Sparkles, Sun, SunMoon, Users, X } from 'lucide-react';
import { getFilterOptions } from '../api/filters';
import type { AuthUser, FilterOptions } from '../api/types';
import { ALL_FIRMS, ALL_SCOPE, ALL_STORES, defaultAppFilters } from '../lib/filterValues';
import { cn } from '../lib/utils';
import { canAccessTab, type Role, type TabId } from '../lib/roles';

export interface AppFilters {
  firma: string;
  rm: string;
  asm: string;
  magazin: string;
  agent: string;
}

interface FilterValueOption {
  label: string;
  value: string;
}

interface MainLayoutProps {
  children: React.ReactNode;
  user: AuthUser | null;
  activeTab: string;
  setActiveTab: (tab: 'hub' | 'focus' | 'agents' | 'management' | 'ai' | 'settings') => void;
  isFilterOpen: boolean;
  setIsFilterOpen: (open: boolean) => void;
  filters: AppFilters;
  setFilters: (filters: AppFilters) => void;
  filterMonth: string;
  onLogout: () => void;
  theme: string;
  setTheme: (theme: string) => void;
  showFilterButton?: boolean;
}

const ALL_TABS = [
  { id: 'hub', icon: LayoutDashboard, label: 'Hub' },
  { id: 'focus', icon: Sparkles, label: 'Focus' },
  { id: 'agents', icon: Users, label: 'Agenti' },
  { id: 'management', icon: Briefcase, label: 'Management' },
  { id: 'ai', icon: Bot, label: 'AI' },
  { id: 'settings', icon: Settings, label: 'Setari' },
] as const;

const emptyOptions: FilterOptions = {
  firme: [],
  regionali: [],
  asmi: [],
  magazine: [],
  agenti: [],
};

export function MainLayout({
  children,
  user,
  activeTab,
  setActiveTab,
  isFilterOpen,
  setIsFilterOpen,
  filters,
  setFilters,
  filterMonth,
  onLogout,
  theme,
  setTheme,
  showFilterButton = true,
}: MainLayoutProps) {
  const [filterOptions, setFilterOptions] = useState<FilterOptions>(emptyOptions);

  const userRole: Role = (user?.role as Role) ?? 'tl';
  const isAdmin = userRole === 'admin';
  const visibleTabs = useMemo(
    () =>
      isAdmin
        ? [...ALL_TABS]
        : ALL_TABS.filter((tab) => canAccessTab(userRole, tab.id as TabId)),
    [isAdmin, userRole]
  );

  useEffect(() => {
    if (!filterMonth) return;
    getFilterOptions(filterMonth)
      .then(setFilterOptions)
      .catch(() => setFilterOptions(emptyOptions));
  }, [filterMonth]);

  useEffect(() => {
    if (!visibleTabs.some((t) => t.id === activeTab)) {
      setActiveTab(visibleTabs[0]?.id);
    }
  }, [userRole, visibleTabs, activeTab, setActiveTab]);

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

  const filteredAsms = useMemo(() => {
    return Array.from(
      new Set(
        filterOptions.magazine
          .filter((item) => (filters.firma === ALL_FIRMS || item.firma === filters.firma))
          .filter((item) => (filters.rm === ALL_SCOPE || item.regional === filters.rm))
          .map((item) => item.asm)
      )
    ).sort();
  }, [filterOptions, filters.firma, filters.rm]);

  const filteredStores = useMemo(() => {
    return filterOptions.magazine
      .filter((item) => (filters.firma === ALL_FIRMS || item.firma === filters.firma))
      .filter((item) => (filters.rm === ALL_SCOPE || item.regional === filters.rm))
      .filter((item) => (filters.asm === ALL_SCOPE || item.asm === filters.asm))
      .sort((a, b) => a.locatie.localeCompare(b.locatie));
  }, [filterOptions, filters.firma, filters.rm, filters.asm]);

  const filteredAgents = useMemo(() => {
    const uniqueAgents = new Map<string, (typeof filterOptions.agenti)[number]>();
    filterOptions.agenti
      .filter((item) => (filters.firma === ALL_FIRMS || item.firma === filters.firma))
      .filter((item) => (filters.rm === ALL_SCOPE || item.regional === filters.rm))
      .filter((item) => (filters.asm === ALL_SCOPE || item.asm === filters.asm))
      .filter((item) => (filters.magazin === ALL_STORES || item.site_code === filters.magazin))
      .forEach((item) => {
        uniqueAgents.set(item.agent, item);
      });

    return Array.from(uniqueAgents.values())
      .map((item) => item.agent)
      .sort((a, b) => a.localeCompare(b));
  }, [filterOptions, filters.firma, filters.rm, filters.asm, filters.magazin]);

  const resetFilters = () => {
    setFilters(defaultAppFilters());
  };

  return (
    <div className="flex h-dvh flex-col overflow-hidden bg-transparent">
      {activeTab === 'settings' && (
        <div className="mx-auto flex w-full max-w-6xl items-center justify-between px-4 pt-7">
          <div>
            <div className="text-[11px] font-bold uppercase tracking-[0.22em] text-slate-500">
              UniHub
            </div>
            <div className="text-sm font-semibold">{user?.full_name ?? user?.username}</div>
          </div>
          <div className="flex items-center gap-1.5">
            <ThemeSwitcher theme={theme} setTheme={setTheme} />
            <button
              onClick={onLogout}
              aria-label="Delogare"
              className="flex h-10 w-10 items-center justify-center rounded-2xl bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900"
            >
              <LogOut size={16} />
            </button>
          </div>
        </div>
      )}

      {activeTab === 'settings' ? <div className="px-4 py-3" /> : null}

      <main
        className={cn(
          'flex-1 min-h-0',
          activeTab === 'ai' ? 'overflow-hidden pb-[4.75rem]' : 'overflow-y-auto pb-24'
        )}
      >
        {children}
      </main>

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
              className="fixed inset-x-0 bottom-0 z-50 mx-auto max-w-lg rounded-t-4xl bg-white p-4 shadow-2xl dark:bg-slate-900"
            >
              <div className="mb-4 flex items-center justify-between">
                <h3 className="text-lg font-bold">Filtre active</h3>
                <button
                  onClick={() => setIsFilterOpen(false)}
                  aria-label="Inchide"
                  className="flex h-8 w-8 items-center justify-center rounded-full bg-slate-100 dark:bg-slate-800"
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
                      asm: ALL_SCOPE,
                      magazin: ALL_STORES,
                      agent: ALL_SCOPE,
                    })
                  }
                />
                <FilterSelect
                  label="Regional"
                  value={filters.rm}
                  values={[
                    { label: ALL_SCOPE, value: ALL_SCOPE },
                    ...filteredRegionals.map((item) => ({ label: item, value: item })),
                  ]}
                  onChange={(value) =>
                    setFilters({
                      ...filters,
                      rm: value,
                      asm: ALL_SCOPE,
                      magazin: ALL_STORES,
                      agent: ALL_SCOPE,
                    })
                  }
                />
                <FilterSelect
                  label="ASM"
                  value={filters.asm}
                  values={[
                    { label: ALL_SCOPE, value: ALL_SCOPE },
                    ...filteredAsms.map((item) => ({ label: item, value: item })),
                  ]}
                  onChange={(value) =>
                    setFilters({
                      ...filters,
                      asm: value,
                      magazin: ALL_STORES,
                      agent: ALL_SCOPE,
                    })
                  }
                />
                <FilterSelect
                  label="Magazin"
                  value={filters.magazin}
                  values={[
                    { label: ALL_STORES, value: ALL_STORES },
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
                <FilterSelect
                  label="Agent"
                  value={filters.agent}
                  values={[
                    { label: ALL_SCOPE, value: ALL_SCOPE },
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

      <div className="fixed inset-x-0 bottom-0 z-30 mx-auto max-w-6xl p-3">
        <div className="glass flex items-center justify-around rounded-2xl p-1.5">
          {visibleTabs.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={cn(
                  'relative flex h-12 w-14 flex-col items-center justify-center rounded-xl transition-all',
                  isActive ? 'text-indigo-600 dark:text-indigo-400' : 'text-slate-500'
                )}
              >
                {isActive && (
                  <motion.div
                    layoutId="active-tab"
                    className="absolute inset-0 rounded-xl bg-indigo-100 dark:bg-indigo-500/20"
                  />
                )}
                <Icon size={18} className="relative z-10 mb-0.5" />
                <span className="relative z-10 text-[9px] font-semibold">{tab.label}</span>
              </button>
            );
          })}
        </div>
      </div>

      {showFilterButton && (['hub', 'focus', 'agents'] as const).includes(activeTab as 'hub' | 'focus' | 'agents') && (
        <button
          onClick={() => setIsFilterOpen(true)}
          aria-label="Filtre"
          className="fixed bottom-20 right-4 z-40 flex h-12 w-12 items-center justify-center rounded-full border border-indigo-200/50 bg-indigo-500/18 text-indigo-700 shadow-lg shadow-indigo-500/10 backdrop-blur-xl transition hover:bg-indigo-500/24 dark:border-indigo-400/20 dark:bg-indigo-400/14 dark:text-indigo-200 dark:hover:bg-indigo-400/20"
        >
          <Filter size={18} />
        </button>
      )}
    </div>
  );
}

function ThemeSwitcher({ theme, setTheme }: { theme: string; setTheme: (theme: string) => void }) {
  const themes = [
    { id: 'light', icon: Sun, label: 'Light' },
    { id: 'light-mint', icon: SunMoon, label: 'Mint' },
    { id: 'light-olive', icon: SunMoon, label: 'Olive' },
    { id: 'dark', icon: Moon, label: 'Dark' },
  ];

  return (
    <div className="flex items-center gap-1 rounded-2xl bg-slate-100 p-1 dark:bg-slate-800">
      {themes.map((item) => {
        const Icon = item.icon;
        const isActive = theme === item.id;
        return (
          <button
            key={item.id}
            onClick={() => setTheme(item.id)}
            className={cn(
              'flex h-8 w-8 items-center justify-center rounded-xl text-xs transition-all',
              isActive
                ? 'bg-white text-indigo-600 shadow-sm dark:bg-slate-700 dark:text-indigo-400'
                : 'text-slate-400 hover:text-slate-600 dark:hover:text-slate-300'
            )}
            title={item.label}
          >
            <Icon size={14} />
          </button>
        );
      })}
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
