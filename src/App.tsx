import { Suspense, lazy, useEffect, useMemo, useRef, useState } from 'react';
import { MainLayout } from './components/MainLayout';
import { ErrorBoundary } from './components/ErrorBoundary';

import { defaultAppFilters, normalizeAppFilters } from './lib/filterValues';
import type { AppFilters } from './lib/appFilters';
import { MGMT_SUBTABS, type ManagementTab, type TabId } from './lib/tabs';
import { sanitizeActiveTab } from './lib/navigationAccess';
import {
  loadAgentsScreen,
  loadCampaignsScreen,
  loadDashboardScreen,
  loadManagementScreen,
  loadSettingsScreen,
} from './screenLoaders';
import { useAuth } from './auth/AuthContext';
import { setUnauthorizedHandler } from './api/client';
import { canAccessManagement } from './auth/permissions';
import { pnlPermissionIsPending, shouldResetPnlSubtab } from './auth/pnlAccess';
import { usePnlCapability } from './auth/usePnlCapability';
import { selectCurrentMonth } from './lib/currentMonth';
import { parseInsightDeepLink } from './lib/insightDeepLink';
import { usePersistentState } from './lib/usePersistentState';
import { useAvailableMonths } from './hooks/useAvailableMonths';
import {
  reportFrontendBootstrapFailure,
  type FrontendBootstrapFailureReason,
} from './lib/frontendMetrics';
import { AvailableMonthsStatus } from './components/AvailableMonthsStatus';

const Campaigns = lazy(loadCampaignsScreen);
const Dashboard = lazy(loadDashboardScreen);
const Agents = lazy(loadAgentsScreen);
const Settings = lazy(loadSettingsScreen);
const Management = lazy(loadManagementScreen);

type ActiveTab = TabId;
type CampaignsSection = 'incentive' | 'promo' | 'concurs' | 'premium' | 'focus';
const CAMPAIGNS_SECTIONS: CampaignsSection[] = ['incentive', 'promo', 'concurs', 'premium', 'focus'];

const FILTER_STORAGE_KEYS = {
  hub: 'unihub_hub_filters',
  focus: 'unihub_focus_filters',
  agents: 'unihub_agents_filters',
} as const;
const MANAGEMENT_SUBTAB_STORAGE_KEY = 'unihub_management_subtab';
const HUB_SECTION_STORAGE_KEY = 'unihub_hub_section';
const CURRENT_MONTH_STORAGE_KEY = 'unihub_current_month';

type HubSection = 'current' | 'history' | 'visits';
const HUB_SECTIONS: HubSection[] = ['current', 'history', 'visits'];

function parseHubSection(value: string): HubSection {
  return HUB_SECTIONS.includes(value as HubSection) ? (value as HubSection) : 'current';
}

function parseManagementSubTab(value: string): ManagementTab {
  const isKnownSubTab = MGMT_SUBTABS.some((tab) => tab.id === value);
  return isKnownSubTab ? value as ManagementTab : 'asm';
}

function parseCampaignsSection(value: string): CampaignsSection {
  if (value === 'campaigns') return 'incentive'; // migrare din vechea grupare Campanii
  return CAMPAIGNS_SECTIONS.includes(value as CampaignsSection)
    ? (value as CampaignsSection)
    : 'incentive';
}

function loadSavedFilters(key: string, overrides: Partial<AppFilters> = {}): AppFilters {
  const saved = localStorage.getItem(key);
  if (!saved) return { ...defaultAppFilters(), ...overrides };
  try {
    return { ...normalizeAppFilters(JSON.parse(saved)), ...overrides };
  } catch {
    return { ...defaultAppFilters(), ...overrides };
  }
}

export default function App() {
  const insightDeepLink = useMemo(() => parseInsightDeepLink(window.location), []);
  const { isAuthenticated, isLoading: isAuthLoading, login, logout, user } = useAuth();
  const hasManagementAccess = canAccessManagement(user?.profile);
  const verifiedSubject = typeof user?.profile.sub === 'string' ? user.profile.sub : undefined;
  const { permissionPending: isPnlCapabilityPending, hasPnlAccess } = usePnlCapability(
    isAuthenticated,
    verifiedSubject,
    hasManagementAccess,
  );
  const isPnlPermissionPending = pnlPermissionIsPending(
    isAuthLoading,
    isPnlCapabilityPending,
  );

  useEffect(() => {
    setUnauthorizedHandler(() => {
      void login();
    });
  }, [login]);

  const [activeTab, setActiveTab] = usePersistentState<ActiveTab>(
    'unihub_active_tab',
    insightDeepLink?.tab ?? 'hub',
    {
      deserialize: (raw) => sanitizeActiveTab(raw, hasManagementAccess),
    },
  );
  const [campaignsSection, setCampaignsSection] = usePersistentState<CampaignsSection>(
    'unihub_campaigns_section',
    insightDeepLink?.campaignSection ?? 'incentive',
    { deserialize: parseCampaignsSection },
  );
  const [theme, setTheme] = usePersistentState('unihub_theme', 'light');
  const [isFilterOpen, setIsFilterOpen] = useState(false);
  const [hubSection, setHubSection] = usePersistentState<HubSection>(
    HUB_SECTION_STORAGE_KEY,
    insightDeepLink?.hubSection ?? 'current',
    { deserialize: parseHubSection },
  );
  const [hubFilters, setHubFilters] = useState<AppFilters>(() =>
    loadSavedFilters(FILTER_STORAGE_KEYS.hub, insightDeepLink?.filters),
  );
  const [focusFilters, setFocusFilters] = useState<AppFilters>(() =>
    loadSavedFilters(FILTER_STORAGE_KEYS.focus, insightDeepLink?.filters),
  );
  const [agentsFilters, setAgentsFilters] = useState<AppFilters>(() =>
    loadSavedFilters(FILTER_STORAGE_KEYS.agents, insightDeepLink?.filters),
  );
  const [currentMonth, setCurrentMonth] = useState('');
  const [focusFilterMonth, setFocusFilterMonth] = useState('');
  const availableMonths = useAvailableMonths(
    isAuthenticated,
    user?.profile.sub ?? 'anonymous',
  );
  const { months, status: monthsStatus, isLoading: isMonthsLoading, setMonths, retry: retryMonths } = availableMonths;
  const lastBootstrapFailure = useRef<FrontendBootstrapFailureReason | null>(null);
  useEffect(() => {
    const reason: FrontendBootstrapFailureReason | null =
      monthsStatus === 'unavailable' || monthsStatus === 'session_expired'
        ? monthsStatus
        : monthsStatus === 'stale'
          ? 'stale_cache'
          : null;
    if (reason && lastBootstrapFailure.current !== reason) {
      reportFrontendBootstrapFailure(reason);
    }
    lastBootstrapFailure.current = reason;
  }, [monthsStatus]);
  const [mgmtSubTab, setMgmtSubTab] = usePersistentState<ManagementTab>(
    MANAGEMENT_SUBTAB_STORAGE_KEY,
    insightDeepLink?.managementSubtab ?? 'asm',
    { deserialize: parseManagementSubTab },
  );

  const insightDeepLinkApplied = useRef(false);
  useEffect(() => {
    if (!insightDeepLink || insightDeepLinkApplied.current) return;
    insightDeepLinkApplied.current = true;
    setActiveTab(insightDeepLink.tab);
    if (insightDeepLink.hubSection) setHubSection(insightDeepLink.hubSection);
    if (insightDeepLink.campaignSection) setCampaignsSection(insightDeepLink.campaignSection);
    if (insightDeepLink.managementSubtab) setMgmtSubTab(insightDeepLink.managementSubtab);
  }, [
    insightDeepLink,
    setActiveTab,
    setCampaignsSection,
    setHubSection,
    setMgmtSubTab,
  ]);

  useEffect(() => {
    if (!hasManagementAccess && activeTab === 'management') {
      setActiveTab('hub');
    }
  }, [activeTab, hasManagementAccess, setActiveTab]);

  useEffect(() => {
    if (shouldResetPnlSubtab(isPnlPermissionPending, hasPnlAccess, mgmtSubTab)) {
      setMgmtSubTab('asm');
    }
  }, [hasPnlAccess, isPnlPermissionPending, mgmtSubTab, setMgmtSubTab]);

  useEffect(() => {
    // Luna in curs se rescrie la bootstrap cu cea mai recenta luna disponibila.
    if (currentMonth) localStorage.setItem(CURRENT_MONTH_STORAGE_KEY, currentMonth);
  }, [currentMonth]);

  useEffect(() => {
    if (!currentMonth) return;
    setFocusFilterMonth((previous) => (
      previous && months.includes(previous) ? previous : currentMonth
    ));
  }, [currentMonth, months]);

  useEffect(() => {
    localStorage.setItem(FILTER_STORAGE_KEYS.hub, JSON.stringify(hubFilters));
  }, [hubFilters]);

  useEffect(() => {
    localStorage.setItem(FILTER_STORAGE_KEYS.focus, JSON.stringify(focusFilters));
  }, [focusFilters]);

  useEffect(() => {
    localStorage.setItem(FILTER_STORAGE_KEYS.agents, JSON.stringify(agentsFilters));
  }, [agentsFilters]);

  useEffect(() => {
    const root = document.documentElement;
    root.className = '';
    if (theme === 'dark') {
      root.classList.add('dark');
    } else if (theme === 'light-mint') {
      root.classList.add('theme-mint');
    } else if (theme === 'light-olive') {
      root.classList.add('theme-olive');
    }
  }, [theme]);

  useEffect(() => {
    if (!isAuthenticated || !months.length) return;
    setCurrentMonth((previous) => (
      insightDeepLink?.period && months.includes(insightDeepLink.period)
        ? insightDeepLink.period
        : previous && months.includes(previous) ? previous : selectCurrentMonth(months)
    ));
  }, [
    insightDeepLink?.period,
    isAuthenticated,
    months,
  ]);



  const activeFilters =
    activeTab === 'focus'
      ? focusFilters
      : activeTab === 'agents' || (activeTab === 'management' && mgmtSubTab === 'salarii')
        ? agentsFilters
        : hubFilters;
  const setActiveFilters =
    activeTab === 'focus'
      ? setFocusFilters
      : activeTab === 'agents' || (activeTab === 'management' && mgmtSubTab === 'salarii')
        ? setAgentsFilters
        : setHubFilters;
  const activeFilterMonth = activeTab === 'focus'
    ? (focusFilterMonth || currentMonth)
    : currentMonth;
  const screenFallback = (
    <div className="flex h-full items-center justify-center text-sm font-semibold text-slate-500">
      Se incarca ecranul...
    </div>
  );

  if (isAuthLoading || isMonthsLoading) {
    return (
      <div className="flex h-full items-center justify-center text-sm font-semibold text-slate-500">
        Se incarca...
      </div>
    );
  }

  if (!isAuthenticated) {
    return (
      <div className="flex h-full items-center justify-center flex-col gap-4">
        <p className="text-sm font-semibold text-slate-500">Nu ești autentificat.</p>
        <button onClick={login} className="px-4 py-2 bg-blue-600 text-white rounded">Login</button>
      </div>
    );
  }

  if (monthsStatus === 'empty' || monthsStatus === 'unavailable' || monthsStatus === 'session_expired') {
    return <AvailableMonthsStatus status={monthsStatus} onRetry={() => { void retryMonths(); }} />;
  }

  const staleMonthsBanner = monthsStatus === 'stale' ? (
    <div className="mb-3 flex items-center justify-between gap-3 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:border-amber-900/50 dark:bg-amber-950/20 dark:text-amber-200">
      <span>Datele lunilor sunt din ultima încărcare validă și pot fi învechite.</span>
      <button type="button" onClick={() => { void retryMonths(); }} className="font-bold underline">Reîncearcă</button>
    </div>
  ) : null;

  return (
    <MainLayout
      activeTab={activeTab}
      setActiveTab={setActiveTab}
      isFilterOpen={isFilterOpen}
      setIsFilterOpen={setIsFilterOpen}
      filters={activeFilters}
      setFilters={setActiveFilters}
      filterMonth={activeFilterMonth}
      theme={theme}
      setTheme={setTheme}
      showFilterButton={!(activeTab === 'hub' && hubSection === 'visits')}
      mgmtSubTab={mgmtSubTab}
      userEmail={user?.profile.email ?? undefined}
      onLogout={logout}
      canAccessManagement={hasManagementAccess}
    >
      {staleMonthsBanner}
      <Suspense fallback={screenFallback}>
        {activeTab === 'hub' && currentMonth && (
          <Dashboard
            currentMonth={currentMonth}
            months={months}
            filters={hubFilters}
            initialSection={hubSection}
            onSectionChange={setHubSection}
          />
        )}
        {activeTab === 'focus' && currentMonth && (
          <Campaigns
            currentMonth={currentMonth}
            months={months}
            filters={focusFilters}
            preferredSection={campaignsSection}
            onSectionChange={setCampaignsSection}
            onFilterMonthChange={setFocusFilterMonth}
          />
        )}
        {activeTab === 'agents' && currentMonth && (
          <Agents
            currentMonth={currentMonth}
            months={months}
            filters={agentsFilters}
            preferredSection={insightDeepLink?.agentsSection}
            preferredGrileMonth={insightDeepLink?.period}
          />
        )}
        {activeTab === 'management' && (
          <ErrorBoundary
            title="Secțiunea Management nu a putut fi afișată"
            description="Datele din celelalte secțiuni sunt în siguranță. Reîncearcă încărcarea ecranului Management."
          >
            <Management
              activeSubTab={mgmtSubTab}
              setActiveSubTab={setMgmtSubTab}
              hasPnlAccess={hasPnlAccess}
              currentMonth={currentMonth}
              salaryFilters={agentsFilters}
            />
          </ErrorBoundary>
        )}
        {activeTab === 'settings' && (
          <Settings
            theme={theme}
            setTheme={setTheme}
            onImportCompleted={(month) => {
              setMonths((previous) => {
                const next = previous.includes(month) ? previous : [...previous, month];
                return next.sort().reverse();
              });
              setCurrentMonth(month);
            }}
          />
        )}
      </Suspense>
    </MainLayout>
  );
}
