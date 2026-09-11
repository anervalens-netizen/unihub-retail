import { lazy, Suspense, type ReactNode } from 'react';

import { getApiErrorMessage } from '../api/client';
import {
  createSavedView, deleteSavedView, listSavedViews, toRetailContextUrlState,
} from '../api/savedViews';
import type { AppFilters } from '../lib/appFilters';
import type { RetailContextUrlState } from '../lib/insightDeepLink';
import type { ManagementTab, TabId } from '../lib/tabs';
import { cn } from '../lib/utils';
import { DesktopSidebar } from './DesktopSidebar';
import { DesktopTopBar } from './DesktopTopBar';
import { MobileBottomNavigation, MobileFilterSheet, MobileFloatingFilter } from './MainLayoutMobile';
import type { SavedViewsApi } from './SavedViewsControl';
import { useMainLayoutFilters } from './useMainLayoutFilters';

const SavedViewsControl = lazy(() => import('./SavedViewsControl').then((module) => ({
  default: module.SavedViewsControl,
})));

/**
 * The shell owns the Saved Views transport deliberately: see `SavedViewsApi`
 * for why this lazy chunk must not import the api client itself.
 */
const SAVED_VIEWS_API: SavedViewsApi = {
  createSavedView, deleteSavedView, getApiErrorMessage, listSavedViews, toRetailContextUrlState,
};

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
  savedViewState?: RetailContextUrlState | null;
  errorCount?: number;
  userEmail?: string;
  onLogout?: () => void;
  canAccessManagement?: boolean;
}

export function MainLayout({
  children, activeTab, setActiveTab, isFilterOpen, setIsFilterOpen, filters, setFilters,
  filterMonth, theme, setTheme, showFilterButton = true, mgmtSubTab, savedViewState,
  errorCount = 0, userEmail, onLogout, canAccessManagement = true,
}: MainLayoutProps) {
  const filterModel = useMainLayoutFilters({
    filterMonth, filters, setFilters, activeTab, mgmtSubTab, showFilterButton,
  });
  const hasSavedViewBrowser = savedViewState !== undefined;
  const desktopSavedViews = hasSavedViewBrowser ? (
    <Suspense fallback={null}>
      <SavedViewsControl currentState={savedViewState} mode="desktop" api={SAVED_VIEWS_API} />
    </Suspense>
  ) : undefined;
  const mobileSavedViews = hasSavedViewBrowser ? (
    <Suspense fallback={null}>
      <SavedViewsControl currentState={savedViewState} mode="mobile" api={SAVED_VIEWS_API} />
    </Suspense>
  ) : undefined;

  return <div className="flex h-dvh overflow-hidden bg-transparent">
    <DesktopSidebar activeTab={activeTab} setActiveTab={setActiveTab} theme={theme} setTheme={setTheme} errorCount={errorCount} canAccessManagement={canAccessManagement} />
    <div className="flex min-h-0 min-w-0 flex-1 flex-col">
      <DesktopTopBar
        activeTab={activeTab}
        mgmtSubTab={mgmtSubTab}
        showFilterButton={showFilterButton}
        onOpenFilter={() => setIsFilterOpen(true)}
        filters={filters}
        savedViews={desktopSavedViews}
        userEmail={userEmail}
        onLogout={onLogout}
      />
      <main className={cn('min-h-0 flex-1', 'overflow-y-auto pb-24 lg:pb-6')}><div className="mx-auto w-full max-w-6xl lg:max-w-[1600px]">{children}</div></main>
    </div>
    <MobileFilterSheet
      open={isFilterOpen}
      onOpenChange={setIsFilterOpen}
      filters={filters}
      setFilters={setFilters}
      model={filterModel}
      showFilters={filterModel.hasMobileFilters}
      savedViews={mobileSavedViews}
    />
    <MobileBottomNavigation activeTab={activeTab} setActiveTab={setActiveTab} errorCount={errorCount} canAccessManagement={canAccessManagement} />
    {(filterModel.hasMobileFilters || hasSavedViewBrowser) && (
      <MobileFloatingFilter
        count={filterModel.activeCount}
        onOpen={() => setIsFilterOpen(true)}
        showFilters={filterModel.hasMobileFilters}
        hasSavedViews={hasSavedViewBrowser}
      />
    )}
  </div>;
}
