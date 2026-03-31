import React, { Suspense, lazy, useEffect, useState } from 'react';
import { MainLayout, type AppFilters } from './components/MainLayout';
import { getCurrentUser, logout } from './api/auth';
import { getAvailableMonths } from './api/filters';
import type { AuthUser } from './api/types';
import { defaultAppFilters } from './lib/filterValues';

const PinScreen = lazy(() =>
  import('./components/PinScreen').then((module) => ({ default: module.PinScreen }))
);
const Campaigns = lazy(() =>
  import('./components/Campaigns').then((module) => ({ default: module.Campaigns }))
);
const Dashboard = lazy(() =>
  import('./components/Dashboard').then((module) => ({ default: module.Dashboard }))
);
const Agents = lazy(() =>
  import('./components/Agents').then((module) => ({ default: module.Agents }))
);
const AIChat = lazy(() => import('./components/AIChat'));
const Settings = lazy(() =>
  import('./components/Settings').then((module) => ({ default: module.Settings }))
);

type ActiveTab = 'hub' | 'focus' | 'agents' | 'ai' | 'settings';
type CampaignsSection = 'campaigns' | 'focus';

const defaultFilters: AppFilters = defaultAppFilters();

export default function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [user, setUser] = useState<AuthUser | null>(null);
  const [activeTab, setActiveTab] = useState<ActiveTab>('hub');
  const [campaignsSection, setCampaignsSection] = useState<CampaignsSection>('campaigns');
  const [theme, setTheme] = useState('light');
  const [isFilterOpen, setIsFilterOpen] = useState(false);
  const [hubFilters, setHubFilters] = useState<AppFilters>(defaultFilters);
  const [focusFilters, setFocusFilters] = useState<AppFilters>(defaultFilters);
  const [agentsFilters, setAgentsFilters] = useState<AppFilters>(defaultFilters);
  const [currentMonth, setCurrentMonth] = useState('');
  const [months, setMonths] = useState<string[]>([]);
  const [bootstrapping, setBootstrapping] = useState(true);

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
    let mounted = true;
    async function bootstrap() {
      const token = localStorage.getItem('unihub_token');
      if (!token) {
        setBootstrapping(false);
        return;
      }
      try {
        const [currentUser, availableMonths] = await Promise.all([
          getCurrentUser(),
          getAvailableMonths(),
        ]);
        if (!mounted) return;
        setUser(currentUser);
        setMonths(availableMonths);
        setCurrentMonth((previous) => previous || availableMonths[0] || '');
        setIsAuthenticated(true);
      } catch {
        logout();
        setIsAuthenticated(false);
        setUser(null);
      } finally {
        if (mounted) {
          setBootstrapping(false);
        }
      }
    }

    void bootstrap();

    const handleLogout = () => {
      logout();
      setUser(null);
      setIsAuthenticated(false);
    };

    const handleNavigate = (event: Event) => {
      const detail = (event as CustomEvent<{ tab?: ActiveTab; section?: CampaignsSection }>).detail;
      if (detail?.tab) {
        setActiveTab(detail.tab);
      }
      if (detail?.section) {
        setCampaignsSection(detail.section);
      }
    };

    window.addEventListener('unihub:logout', handleLogout);
    window.addEventListener('unihub:navigate', handleNavigate as EventListener);
    return () => {
      mounted = false;
      window.removeEventListener('unihub:logout', handleLogout);
      window.removeEventListener('unihub:navigate', handleNavigate as EventListener);
    };
  }, []);

  const handleAuthenticated = async (currentUser: AuthUser) => {
    const availableMonths = await getAvailableMonths();
    setUser(currentUser);
    setMonths(availableMonths);
    setCurrentMonth(availableMonths[0] || '');
    setIsAuthenticated(true);
  };

  const handleLogout = () => {
    logout();
    setUser(null);
    setIsAuthenticated(false);
  };

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

  const content = bootstrapping ? (
    <div className="flex h-full items-center justify-center text-sm font-semibold text-slate-500">
      Se incarca sesiunea...
    </div>
  ) : !isAuthenticated ? (
    <Suspense fallback={screenFallback}>
      <PinScreen onAuthenticated={handleAuthenticated} />
    </Suspense>
  ) : (
    <MainLayout
      user={user}
      activeTab={activeTab}
      setActiveTab={setActiveTab}
      isFilterOpen={isFilterOpen}
      setIsFilterOpen={setIsFilterOpen}
      filters={activeFilters}
      setFilters={setActiveFilters}
      filterMonth={currentMonth}
      onLogout={handleLogout}
      theme={theme}
      setTheme={setTheme}
    >
      <Suspense fallback={screenFallback}>
        {activeTab === 'hub' && currentMonth && (
          <Dashboard currentMonth={currentMonth} months={months} filters={hubFilters} user={user} />
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
          <Agents currentMonth={currentMonth} months={months} filters={agentsFilters} user={user} />
        )}
        {activeTab === 'ai' && <AIChat />}
        {activeTab === 'settings' && (
          <Settings
            theme={theme}
            setTheme={setTheme}
            user={user}
            activeMonth={currentMonth}
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

  return content;
}
