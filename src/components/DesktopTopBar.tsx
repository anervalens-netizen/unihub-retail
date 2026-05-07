import { Filter, LogOut } from 'lucide-react';
import type { AppFilters } from './MainLayout';
import { TAB_LABELS, MGMT_SUBTAB_LABELS, type ManagementTab } from '../lib/tabs';
import { ALL_FIRMS, ALL_SCOPE, ALL_STORES } from '../lib/filterValues';
import { cn } from '../lib/utils';

interface Props {
  activeTab: string;
  mgmtSubTab: ManagementTab;
  showFilterButton: boolean;
  onOpenFilter: () => void;
  filters: AppFilters;
  userEmail?: string;
  onLogout?: () => void;
}

const FILTER_TABS = new Set(['hub', 'focus', 'agents']);

export function DesktopTopBar({ activeTab, mgmtSubTab, showFilterButton, onOpenFilter, filters, userEmail, onLogout }: Props) {
  const breadcrumb =
    activeTab === 'management'
      ? `Management › ${MGMT_SUBTAB_LABELS[mgmtSubTab] ?? ''}`
      : (TAB_LABELS[activeTab] ?? activeTab);

  const activeFilterCount = [filters.firma, filters.rm, filters.magazin, filters.agent].filter(
    (v) => v !== ALL_FIRMS && v !== ALL_SCOPE && v !== ALL_STORES
  ).length;

  const showFilter = showFilterButton && FILTER_TABS.has(activeTab);

  return (
    <div className="hidden lg:flex items-center justify-between h-14 px-6 shrink-0 border-b border-[var(--glass-border)] bg-[var(--glass-bg)] backdrop-blur-md sticky top-0 z-30">
      <span className="text-sm font-semibold text-slate-700 dark:text-slate-200 tracking-tight">
        {breadcrumb}
      </span>

      <div className="flex items-center gap-3">
        {userEmail && (
          <span className="text-xs text-slate-500 dark:text-slate-400 truncate max-w-[180px]">
            {userEmail}
          </span>
        )}
        {showFilter && (
          <button
            onClick={onOpenFilter}
            className={cn(
              'flex items-center gap-1.5 rounded-xl border px-3 py-1.5 text-xs font-medium transition-colors',
              activeFilterCount > 0
                ? 'border-indigo-300 bg-indigo-50 text-indigo-700 dark:border-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-300'
                : 'border-slate-200 bg-slate-50 text-slate-600 hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-800/60 dark:text-slate-400 dark:hover:bg-slate-700/60'
            )}
          >
            <Filter size={13} />
            Filtre
            {activeFilterCount > 0 && (
              <span className="ml-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-indigo-500 px-1 text-[9px] font-bold text-white">
                {activeFilterCount}
              </span>
            )}
          </button>
        )}
        {onLogout && (
          <button
            onClick={onLogout}
            className="flex items-center gap-1 rounded-xl border border-red-200 bg-red-50 px-3 py-1.5 text-xs font-medium text-red-700 hover:bg-red-100 transition-colors dark:border-red-800 dark:bg-red-900/30 dark:text-red-300 dark:hover:bg-red-800/40"
          >
            <LogOut size={13} />
            Logout
          </button>
        )}
      </div>
    </div>
  );
}
