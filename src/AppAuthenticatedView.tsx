import { lazy, Suspense } from 'react';

import { ErrorBoundary } from './components/ErrorBoundary';
import { MainLayout } from './components/MainLayout';
import {
  loadAgentsScreen, loadCampaignsScreen, loadDashboardScreen, loadManagementScreen, loadSettingsScreen,
} from './screenLoaders';
import type { AppController } from './useAppController';

const Campaigns = lazy(loadCampaignsScreen);
const Dashboard = lazy(loadDashboardScreen);
const Agents = lazy(loadAgentsScreen);
const Settings = lazy(loadSettingsScreen);
const Management = lazy(loadManagementScreen);

export function AppAuthenticatedView({ controller }: { controller: AppController }) {
  const { auth, data, navigation } = controller;
  const activeFilters = navigation.activeTab === 'focus' ? data.focusFilters
    : navigation.activeTab === 'agents' || (navigation.activeTab === 'management' && navigation.mgmtSubTab === 'salarii')
      ? data.agentsFilters : data.hubFilters;
  const setActiveFilters = navigation.activeTab === 'focus' ? data.setFocusFilters
    : navigation.activeTab === 'agents' || (navigation.activeTab === 'management' && navigation.mgmtSubTab === 'salarii')
      ? data.setAgentsFilters : data.setHubFilters;
  const activeFilterMonth = navigation.activeTab === 'focus' ? data.focusFilterMonth || data.currentMonth : data.currentMonth;
  const staleBanner = data.availableMonths.status === 'stale' ? <div className="mb-3 flex items-center justify-between gap-3 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:border-amber-900/50 dark:bg-amber-950/20 dark:text-amber-200"><span>Datele lunilor sunt din ultima încărcare validă și pot fi învechite.</span><button type="button" onClick={() => { void data.availableMonths.retry(); }} className="font-bold underline">Reîncearcă</button></div> : null;
  return <MainLayout
    activeTab={navigation.activeTab} setActiveTab={navigation.setActiveTab}
    isFilterOpen={controller.isFilterOpen} setIsFilterOpen={controller.setIsFilterOpen}
    filters={activeFilters} setFilters={setActiveFilters} filterMonth={activeFilterMonth}
    theme={navigation.theme} setTheme={navigation.setTheme}
    showFilterButton={!(navigation.activeTab === 'hub' && navigation.hubSection === 'visits')}
    mgmtSubTab={navigation.mgmtSubTab} userEmail={auth.user?.profile.email ?? undefined}
    onLogout={auth.logout} canAccessManagement={controller.hasManagementAccess}
  >
    {staleBanner}
    <AppScreens controller={controller} />
  </MainLayout>;
}

function AppScreens({ controller }: { controller: AppController }) {
  const { data, navigation } = controller;
  return <Suspense fallback={<div className="flex h-full items-center justify-center text-sm font-semibold text-slate-500">Se incarca ecranul...</div>}>
    {navigation.activeTab === 'hub' && data.currentMonth && <Dashboard currentMonth={data.currentMonth} months={data.availableMonths.months} filters={data.hubFilters} initialSection={navigation.hubSection} onSectionChange={navigation.setHubSection} />}
    {navigation.activeTab === 'focus' && data.currentMonth && <Campaigns currentMonth={data.currentMonth} months={data.availableMonths.months} filters={data.focusFilters} preferredSection={navigation.campaignsSection} onSectionChange={navigation.setCampaignsSection} onFilterMonthChange={data.setFocusFilterMonth} />}
    {navigation.activeTab === 'agents' && data.currentMonth && <Agents currentMonth={data.currentMonth} months={data.availableMonths.months} filters={data.agentsFilters} preferredSection={controller.deepLink?.agentsSection} preferredGrileMonth={controller.deepLink?.period} />}
    {navigation.activeTab === 'management' && <ErrorBoundary title="Secțiunea Management nu a putut fi afișată" description="Datele din celelalte secțiuni sunt în siguranță. Reîncearcă încărcarea ecranului Management."><Management activeSubTab={navigation.mgmtSubTab} setActiveSubTab={navigation.setMgmtSubTab} hasPnlAccess={controller.hasPnlAccess} currentMonth={data.currentMonth} salaryFilters={data.agentsFilters} /></ErrorBoundary>}
    {navigation.activeTab === 'settings' && <Settings theme={navigation.theme} setTheme={navigation.setTheme} onImportCompleted={(month) => {
      data.availableMonths.setMonths((previous) => {
        const next = previous.includes(month) ? previous : [...previous, month];
        return next.sort().reverse();
      });
      data.setCurrentMonth(month);
    }} />}
  </Suspense>;
}
