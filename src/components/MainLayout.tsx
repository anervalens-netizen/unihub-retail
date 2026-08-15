import type { ReactNode } from 'react';

import type { AppFilters } from '../lib/appFilters';
import type { ManagementTab, TabId } from '../lib/tabs';
import { cn } from '../lib/utils';
import { DesktopSidebar } from './DesktopSidebar';
import { DesktopTopBar } from './DesktopTopBar';
import { MobileBottomNavigation, MobileFilterSheet, MobileFloatingFilter } from './MainLayoutMobile';
import { useMainLayoutFilters } from './useMainLayoutFilters';

interface MainLayoutProps {
  children: ReactNode;
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

export function MainLayout({
  children, activeTab, setActiveTab, isFilterOpen, setIsFilterOpen, filters, setFilters,
  filterMonth, theme, setTheme, showFilterButton = true, mgmtSubTab, errorCount = 0,
  userEmail, onLogout, canAccessManagement = true,
}: MainLayoutProps) {
  const filterModel = useMainLayoutFilters({
    filterMonth, filters, setFilters, activeTab, mgmtSubTab, showFilterButton,
  });
  return <div className="flex h-dvh overflow-hidden bg-transparent">
    <DesktopSidebar activeTab={activeTab} setActiveTab={setActiveTab} theme={theme} setTheme={setTheme} errorCount={errorCount} canAccessManagement={canAccessManagement} />
    <div className="flex min-h-0 min-w-0 flex-1 flex-col">
      <DesktopTopBar activeTab={activeTab} mgmtSubTab={mgmtSubTab} showFilterButton={showFilterButton} onOpenFilter={() => setIsFilterOpen(true)} filters={filters} userEmail={userEmail} onLogout={onLogout} />
      <main className={cn('min-h-0 flex-1', 'overflow-y-auto pb-24 lg:pb-6')}><div className="mx-auto w-full max-w-6xl lg:max-w-[1600px]">{children}</div></main>
    </div>
    <MobileFilterSheet open={isFilterOpen} onOpenChange={setIsFilterOpen} filters={filters} setFilters={setFilters} model={filterModel} />
    <MobileBottomNavigation activeTab={activeTab} setActiveTab={setActiveTab} errorCount={errorCount} canAccessManagement={canAccessManagement} />
    {filterModel.hasMobileFilters && <MobileFloatingFilter count={filterModel.activeCount} onOpen={() => setIsFilterOpen(true)} />}
  </div>;
}
