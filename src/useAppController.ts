import { useEffect, useMemo, useRef, useState } from 'react';

import { setUnauthorizedHandler } from './api/client';
import { useAuth } from './auth/AuthContext';
import { canAccessManagement } from './auth/permissions';
import { pnlPermissionIsPending, shouldResetPnlSubtab } from './auth/pnlAccess';
import { usePnlCapability } from './auth/usePnlCapability';
import { useAvailableMonths } from './hooks/useAvailableMonths';
import type { AppFilters } from './lib/appFilters';
import { selectCurrentMonth } from './lib/currentMonth';
import { defaultAppFilters, normalizeAppFilters } from './lib/filterValues';
import { reportFrontendBootstrapFailure, type FrontendBootstrapFailureReason } from './lib/frontendMetrics';
import { parseInsightDeepLink } from './lib/insightDeepLink';
import { sanitizeActiveTab } from './lib/navigationAccess';
import { usePersistentState } from './lib/usePersistentState';
import { MGMT_SUBTABS, type ManagementTab, type TabId } from './lib/tabs';

export type CampaignsSection = 'incentive' | 'promo' | 'concurs' | 'premium' | 'focus';
export type HubSection = 'current' | 'history' | 'visits';
const CAMPAIGNS_SECTIONS: CampaignsSection[] = ['incentive', 'promo', 'concurs', 'premium', 'focus'];
const HUB_SECTIONS: HubSection[] = ['current', 'history', 'visits'];
const FILTER_KEYS = { hub: 'unihub_hub_filters', focus: 'unihub_focus_filters', agents: 'unihub_agents_filters' } as const;

function parseHubSection(value: string): HubSection { return HUB_SECTIONS.includes(value as HubSection) ? value as HubSection : 'current'; }
function parseManagementSubTab(value: string): ManagementTab { return MGMT_SUBTABS.some((tab) => tab.id === value) ? value as ManagementTab : 'asm'; }
function parseCampaignsSection(value: string): CampaignsSection {
  if (value === 'campaigns') return 'incentive';
  return CAMPAIGNS_SECTIONS.includes(value as CampaignsSection) ? value as CampaignsSection : 'incentive';
}
function loadSavedFilters(key: string, overrides: Partial<AppFilters> = {}) {
  const saved = sessionStorage.getItem(key);
  if (!saved) return { ...defaultAppFilters(), ...overrides };
  try { return { ...normalizeAppFilters(JSON.parse(saved)), ...overrides }; }
  catch { return { ...defaultAppFilters(), ...overrides }; }
}

function useAppNavigation(
  deepLink: ReturnType<typeof parseInsightDeepLink>,
  hasManagementAccess: boolean,
  pnlPending: boolean,
  hasPnlAccess: boolean,
) {
  const [activeTab, setActiveTab] = usePersistentState<TabId>('unihub_active_tab', deepLink?.tab ?? 'hub', {
    deserialize: (raw) => sanitizeActiveTab(raw, hasManagementAccess),
  });
  const [campaignsSection, setCampaignsSection] = usePersistentState<CampaignsSection>('unihub_campaigns_section', deepLink?.campaignSection ?? 'incentive', { deserialize: parseCampaignsSection });
  const [theme, setTheme] = usePersistentState('unihub_theme', 'light');
  const [hubSection, setHubSection] = usePersistentState<HubSection>('unihub_hub_section', deepLink?.hubSection ?? 'current', { deserialize: parseHubSection });
  const [mgmtSubTab, setMgmtSubTab] = usePersistentState<ManagementTab>('unihub_management_subtab', deepLink?.managementSubtab ?? 'asm', { deserialize: parseManagementSubTab });
  const deepLinkApplied = useRef(false);
  useEffect(() => {
    if (!deepLink || deepLinkApplied.current) return;
    deepLinkApplied.current = true;
    setActiveTab(deepLink.tab);
    if (deepLink.hubSection) setHubSection(deepLink.hubSection);
    if (deepLink.campaignSection) setCampaignsSection(deepLink.campaignSection);
    if (deepLink.managementSubtab) setMgmtSubTab(deepLink.managementSubtab);
  }, [deepLink, setActiveTab, setCampaignsSection, setHubSection, setMgmtSubTab]);
  useEffect(() => {
    if (!hasManagementAccess && activeTab === 'management') setActiveTab('hub');
  }, [activeTab, hasManagementAccess, setActiveTab]);
  useEffect(() => {
    if (shouldResetPnlSubtab(pnlPending, hasPnlAccess, mgmtSubTab)) setMgmtSubTab('asm');
  }, [hasPnlAccess, mgmtSubTab, pnlPending, setMgmtSubTab]);
  useEffect(() => {
    document.documentElement.className = '';
    if (theme === 'dark') document.documentElement.classList.add('dark');
    else if (theme === 'light-mint') document.documentElement.classList.add('theme-mint');
    else if (theme === 'light-olive') document.documentElement.classList.add('theme-olive');
  }, [theme]);
  return { activeTab, setActiveTab, campaignsSection, setCampaignsSection, theme, setTheme, hubSection, setHubSection, mgmtSubTab, setMgmtSubTab };
}

function useAppData(
  deepLink: ReturnType<typeof parseInsightDeepLink>,
  authenticated: boolean,
  subject: string,
) {
  const [hubFilters, setHubFilters] = useState<AppFilters>(() => loadSavedFilters(FILTER_KEYS.hub, deepLink?.filters));
  const [focusFilters, setFocusFilters] = useState<AppFilters>(() => loadSavedFilters(FILTER_KEYS.focus, deepLink?.filters));
  const [agentsFilters, setAgentsFilters] = useState<AppFilters>(() => loadSavedFilters(FILTER_KEYS.agents, deepLink?.filters));
  const [currentMonth, setCurrentMonth] = useState('');
  const [focusFilterMonth, setFocusFilterMonth] = useState('');
  const availableMonths = useAvailableMonths(authenticated, subject);
  const lastFailure = useRef<FrontendBootstrapFailureReason | null>(null);
  useEffect(() => {
    const status = availableMonths.status;
    const reason: FrontendBootstrapFailureReason | null = status === 'unavailable' || status === 'session_expired'
      ? status : status === 'stale' ? 'stale_cache' : null;
    if (reason && lastFailure.current !== reason) reportFrontendBootstrapFailure(reason);
    lastFailure.current = reason;
  }, [availableMonths.status]);
  useEffect(() => {
    if (currentMonth) sessionStorage.setItem('unihub_current_month', currentMonth);
  }, [currentMonth]);
  useEffect(() => {
    if (currentMonth) setFocusFilterMonth((previous) => previous && availableMonths.months.includes(previous) ? previous : currentMonth);
  }, [availableMonths.months, currentMonth]);
  useEffect(() => { sessionStorage.setItem(FILTER_KEYS.hub, JSON.stringify(hubFilters)); }, [hubFilters]);
  useEffect(() => { sessionStorage.setItem(FILTER_KEYS.focus, JSON.stringify(focusFilters)); }, [focusFilters]);
  useEffect(() => { sessionStorage.setItem(FILTER_KEYS.agents, JSON.stringify(agentsFilters)); }, [agentsFilters]);
  useEffect(() => {
    if (!authenticated || !availableMonths.months.length) return;
    setCurrentMonth((previous) => deepLink?.period && availableMonths.months.includes(deepLink.period)
      ? deepLink.period : previous && availableMonths.months.includes(previous) ? previous : selectCurrentMonth(availableMonths.months));
  }, [authenticated, availableMonths.months, deepLink?.period]);
  return {
    hubFilters, setHubFilters, focusFilters, setFocusFilters, agentsFilters, setAgentsFilters,
    currentMonth, setCurrentMonth, focusFilterMonth, setFocusFilterMonth, availableMonths,
  };
}

export function useAppController() {
  const deepLink = useMemo(() => parseInsightDeepLink(window.location), []);
  const auth = useAuth();
  const hasManagementAccess = canAccessManagement(auth.user?.profile);
  const subject = typeof auth.user?.profile.sub === 'string' ? auth.user.profile.sub : undefined;
  const pnl = usePnlCapability(auth.isAuthenticated, subject, hasManagementAccess);
  const pnlPending = pnlPermissionIsPending(auth.isLoading, pnl.permissionPending);
  const navigation = useAppNavigation(deepLink, hasManagementAccess, pnlPending, pnl.hasPnlAccess);
  const data = useAppData(deepLink, auth.isAuthenticated, auth.user?.profile.sub ?? 'anonymous');
  useEffect(() => { setUnauthorizedHandler(() => { void auth.login(); }); }, [auth.login]);
  const [isFilterOpen, setIsFilterOpen] = useState(false);
  return { deepLink, auth, hasManagementAccess, hasPnlAccess: pnl.hasPnlAccess, navigation, data, isFilterOpen, setIsFilterOpen };
}

export type AppController = ReturnType<typeof useAppController>;
