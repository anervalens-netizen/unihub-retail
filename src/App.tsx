import { Suspense, lazy, useEffect, useRef, useState } from 'react';
import { MainLayout, type AppFilters } from './components/MainLayout';

import { getAvailableMonths } from './api/filters';
import { defaultAppFilters } from './lib/filterValues';
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
import { setAccessTokenProvider, setUnauthorizedHandler } from './api/client';
import { canAccessManagement } from './auth/permissions';

const Campaigns = lazy(loadCampaignsScreen);
const Dashboard = lazy(loadDashboardScreen);
const Agents = lazy(loadAgentsScreen);
const Settings = lazy(loadSettingsScreen);
const Management = lazy(loadManagementScreen);

type ActiveTab = TabId;
type CampaignsSection = 'incentive' | 'promo' | 'concurs' | 'focus';
const CAMPAIGNS_SECTIONS: CampaignsSection[] = ['incentive', 'promo', 'concurs', 'focus'];

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

function loadHubSection(): HubSection {
  const saved = localStorage.getItem(HUB_SECTION_STORAGE_KEY);
  return HUB_SECTIONS.includes(saved as HubSection) ? (saved as HubSection) : 'current';
}

function loadManagementSubTab(): ManagementTab {
  const saved = localStorage.getItem(MANAGEMENT_SUBTAB_STORAGE_KEY);
  const isKnownSubTab = MGMT_SUBTABS.some((tab) => tab.id === saved);
  return isKnownSubTab ? saved as ManagementTab : 'asm';
}

function loadSavedFilters(key: string): AppFilters {
  const saved = localStorage.getItem(key);
  if (!saved) return defaultAppFilters();
  try {
    return { ...defaultAppFilters(), ...JSON.parse(saved) };
  } catch {
    return defaultAppFilters();
  }
}

export default function App() {
  const { isAuthenticated, isLoading: isAuthLoading, login, logout, getAccessToken, user } = useAuth();
  const hasManagementAccess = canAccessManagement(user?.profile, user?.access_token);

  useEffect(() => {
    setAccessTokenProvider(getAccessToken);
    setUnauthorizedHandler(() => {
      void login();
    });
  }, [getAccessToken, login]);

  const [activeTab, setActiveTab] = useState<ActiveTab>(() => {
    const saved = localStorage.getItem('unihub_active_tab');
    return sanitizeActiveTab(saved, hasManagementAccess);
  });
  const [campaignsSection, setCampaignsSection] = useState<CampaignsSection>(() => {
    const saved = localStorage.getItem('unihub_campaigns_section');
    if (saved === 'campaigns') return 'incentive'; // migrare din vechea grupare Campanii
    return CAMPAIGNS_SECTIONS.includes(saved as CampaignsSection)
      ? (saved as CampaignsSection)
      : 'incentive';
  });
  const [theme, setTheme] = useState(() => localStorage.getItem('unihub_theme') ?? 'light');
  const [isFilterOpen, setIsFilterOpen] = useState(false);
  const [hubSection, setHubSection] = useState<HubSection>(loadHubSection);
  const [hubFilters, setHubFilters] = useState<AppFilters>(() => loadSavedFilters(FILTER_STORAGE_KEYS.hub));
  const [focusFilters, setFocusFilters] = useState<AppFilters>(() => loadSavedFilters(FILTER_STORAGE_KEYS.focus));
  const [agentsFilters, setAgentsFilters] = useState<AppFilters>(() => loadSavedFilters(FILTER_STORAGE_KEYS.agents));
  const [currentMonth, setCurrentMonth] = useState(() => localStorage.getItem(CURRENT_MONTH_STORAGE_KEY) ?? '');
  const [months, setMonths] = useState<string[]>([]);
  const [bootstrapping, setBootstrapping] = useState(true);
  const [mgmtSubTab, setMgmtSubTab] = useState<ManagementTab>(loadManagementSubTab);

  useEffect(() => {
    localStorage.setItem('unihub_active_tab', activeTab);
  }, [activeTab]);

  useEffect(() => {
    if (!hasManagementAccess && activeTab === 'management') {
      setActiveTab('hub');
    }
  }, [activeTab, hasManagementAccess]);

  useEffect(() => {
    localStorage.setItem('unihub_campaigns_section', campaignsSection);
  }, [campaignsSection]);

  useEffect(() => {
    localStorage.setItem(MANAGEMENT_SUBTAB_STORAGE_KEY, mgmtSubTab);
  }, [mgmtSubTab]);

  useEffect(() => {
    localStorage.setItem(HUB_SECTION_STORAGE_KEY, hubSection);
  }, [hubSection]);

  useEffect(() => {
    // Pastreaza luna in care lucram peste refresh (validata in bootstrap fata de lunile disponibile)
    if (currentMonth) localStorage.setItem(CURRENT_MONTH_STORAGE_KEY, currentMonth);
  }, [currentMonth]);

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
    localStorage.setItem('unihub_theme', theme);
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

  const bootstrapRan = useRef(false);

  useEffect(() => {
    // Don't start anything until auth loading is done
    if (isAuthLoading) return;
    // If already ran bootstrap, skip
    if (bootstrapRan.current) return;
    bootstrapRan.current = true;

    // If not authenticated, mark bootstrapping as done immediately
    if (!isAuthenticated) {
      setBootstrapping(false);
      return;
    }

    let mounted = true;
    async function bootstrap() {
      try {
        const availableMonths = await getAvailableMonths();
        if (!mounted) return;
        setMonths(availableMonths);
        // Pastreaza luna salvata daca inca e valida; altfel cade pe cea mai recenta
        setCurrentMonth((previous) =>
          previous && availableMonths.includes(previous) ? previous : availableMonths[0] || '',
        );
      } catch {
        // ignore — empty state OK
      } finally {
        if (mounted) {
          setBootstrapping(false);
        }
      }
    }

    void bootstrap();

    const handleNavigate = (event: Event) => {
      const detail = (event as CustomEvent<{ tab?: ActiveTab; section?: CampaignsSection; subtab?: ManagementTab }>).detail;
      if (detail?.tab) {
        setActiveTab(detail.tab);
      }
      if (detail?.section) {
        setCampaignsSection(detail.section);
      }
      if (detail?.subtab) {
        setMgmtSubTab(detail.subtab);
      }
    };

    window.addEventListener('unihub:navigate', handleNavigate as EventListener);
    return () => {
      mounted = false;
      window.removeEventListener('unihub:navigate', handleNavigate as EventListener);
    };
  }, [isAuthenticated, isAuthLoading]);



  const activeFilters =
    activeTab === 'focus'
      ? focusFilters
      : activeTab === 'agents'
        ? agentsFilters
        : hubFilters;
  const setActiveFilters =
    activeTab === 'focus'
      ? setFocusFilters
      : activeTab === 'agents'
        ? setAgentsFilters
        : setHubFilters;
  const screenFallback = (
    <div className="flex h-full items-center justify-center text-sm font-semibold text-slate-500">
      Se incarca ecranul...
    </div>
  );

  if (isAuthLoading || bootstrapping) {
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

  return (
    <MainLayout
      activeTab={activeTab}
      setActiveTab={setActiveTab}
      isFilterOpen={isFilterOpen}
      setIsFilterOpen={setIsFilterOpen}
      filters={activeFilters}
      setFilters={setActiveFilters}
      filterMonth={currentMonth}
      theme={theme}
      setTheme={setTheme}
      showFilterButton={!(activeTab === 'hub' && hubSection === 'visits')}
      mgmtSubTab={mgmtSubTab}
      setMgmtSubTab={setMgmtSubTab}
      userEmail={user?.profile.email ?? undefined}
      onLogout={logout}
      canAccessManagement={hasManagementAccess}
    >
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
          />
        )}
        {activeTab === 'agents' && currentMonth && (
          <Agents currentMonth={currentMonth} months={months} filters={agentsFilters} />
        )}
        {activeTab === 'management' && (
          <Management
            activeSubTab={mgmtSubTab}
            setActiveSubTab={setMgmtSubTab}
          />
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
