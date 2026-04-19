import { Suspense, lazy, useEffect, useState } from 'react';
import { MainLayout, type AppFilters } from './components/MainLayout';
import { getUnseenCount } from './api/errors';
import { getAvailableMonths } from './api/filters';
import { defaultAppFilters } from './lib/filterValues';
import type { ManagementTab } from './lib/tabs';

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
const Management = lazy(() =>
  import('./components/Management').then((module) => ({ default: module.Management }))
);

type ActiveTab = 'hub' | 'focus' | 'agents' | 'management' | 'ai' | 'settings';
type CampaignsSection = 'campaigns' | 'focus';

const defaultFilters: AppFilters = defaultAppFilters();

export default function App() {
  const [errorCount, setErrorCount] = useState(0);
  const [activeTab, setActiveTab] = useState<ActiveTab>(() => {
    const saved = localStorage.getItem('unihub_active_tab');
    return (saved as ActiveTab) || 'hub';
  });
  const [campaignsSection, setCampaignsSection] = useState<CampaignsSection>(() => {
    const saved = localStorage.getItem('unihub_campaigns_section');
    return (saved as CampaignsSection) || 'campaigns';
  });
  const [theme, setTheme] = useState(() => localStorage.getItem('unihub_theme') ?? 'light');
  const [isFilterOpen, setIsFilterOpen] = useState(false);
  const [hubSection, setHubSection] = useState<'current' | 'history' | 'visits'>('current');
  const [hubFilters, setHubFilters] = useState<AppFilters>(defaultFilters);
  const [focusFilters, setFocusFilters] = useState<AppFilters>(defaultFilters);
  const [agentsFilters, setAgentsFilters] = useState<AppFilters>(defaultFilters);
  const [currentMonth, setCurrentMonth] = useState('');
  const [months, setMonths] = useState<string[]>([]);
  const [bootstrapping, setBootstrapping] = useState(true);
  const [mgmtSubTab, setMgmtSubTab] = useState<ManagementTab>('asm');

  useEffect(() => {
    localStorage.setItem('unihub_active_tab', activeTab);
  }, [activeTab]);

  useEffect(() => {
    localStorage.setItem('unihub_campaigns_section', campaignsSection);
  }, [campaignsSection]);

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

  useEffect(() => {
    let mounted = true;
    async function bootstrap() {
      try {
        const availableMonths = await getAvailableMonths();
        if (!mounted) return;
        setMonths(availableMonths);
        setCurrentMonth((previous) => previous || availableMonths[0] || '');
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
      const detail = (event as CustomEvent<{ tab?: ActiveTab; section?: CampaignsSection }>).detail;
      if (detail?.tab) {
        setActiveTab(detail.tab);
      }
      if (detail?.section) {
        setCampaignsSection(detail.section);
      }
    };

    window.addEventListener('unihub:navigate', handleNavigate as EventListener);
    return () => {
      mounted = false;
      window.removeEventListener('unihub:navigate', handleNavigate as EventListener);
    };
  }, []);

  useEffect(() => {
    async function poll() {
      try {
        const count = await getUnseenCount();
        setErrorCount(count);
      } catch {
        // silent
      }
    }

    void poll();
    const interval = setInterval(() => { void poll(); }, 60_000);
    return () => clearInterval(interval);
  }, []);

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

  if (bootstrapping) {
    return (
      <div className="flex h-full items-center justify-center text-sm font-semibold text-slate-500">
        Se incarca...
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
      errorCount={errorCount}
    >
      <Suspense fallback={screenFallback}>
        {activeTab === 'hub' && currentMonth && (
          <Dashboard currentMonth={currentMonth} months={months} filters={hubFilters} onSectionChange={setHubSection} />
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
        {activeTab === 'ai' && <AIChat />}
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
            onUnseenCountChange={setErrorCount}
          />
        )}
      </Suspense>
    </MainLayout>
  );
}
