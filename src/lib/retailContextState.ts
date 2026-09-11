import type { AppFilters } from './appFilters';
import type {
  InsightAgentsSection,
  InsightCampaignSection,
  InsightHubSection,
  RetailContextUrlState,
} from './insightDeepLink';
import type { ManagementTab, TabId } from './tabs';

export interface CurrentRetailContextInput {
  activeTab: TabId;
  currentMonth: string;
  focusFilterMonth: string;
  hubHistoryMonths: string[];
  hubFilters: AppFilters;
  focusFilters: AppFilters;
  agentsFilters: AppFilters;
  hubSection: InsightHubSection;
  campaignSection: InsightCampaignSection;
  agentsSection?: InsightAgentsSection;
  managementSubtab: ManagementTab;
  hasManagementAccess: boolean;
}

export function buildCurrentRetailContextState(
  input: CurrentRetailContextInput,
): RetailContextUrlState | null {
  if (!input.currentMonth || input.activeTab === 'settings') return null;
  if (input.activeTab === 'management' && !input.hasManagementAccess) return null;
  const filters = input.activeTab === 'focus'
    ? input.focusFilters
    : input.activeTab === 'agents'
      || (input.activeTab === 'management' && input.managementSubtab === 'salarii')
      ? input.agentsFilters
      : input.hubFilters;
  const historyPeriod = input.hubHistoryMonths.length === 1 ? input.hubHistoryMonths[0] : input.currentMonth;
  const period = input.activeTab === 'focus'
    ? input.focusFilterMonth || input.currentMonth
    : input.activeTab === 'hub' && input.hubSection === 'history'
      ? historyPeriod
      : input.currentMonth;
  if (input.activeTab === 'hub') return { tab: 'hub', period, filters, hubSection: input.hubSection };
  if (input.activeTab === 'focus') return { tab: 'focus', period, filters, campaignSection: input.campaignSection };
  if (input.activeTab === 'agents') return { tab: 'agents', period, filters, agentsSection: input.agentsSection ?? 'overview' };
  return { tab: 'management', period, filters, managementSubtab: input.managementSubtab };
}

export function buildCurrentSavedViewState(
  input: CurrentRetailContextInput,
): RetailContextUrlState | null {
  if (input.activeTab === 'management') return null;
  if (input.activeTab === 'hub' && input.hubSection === 'visits') return null;
  if (input.activeTab === 'hub' && input.hubSection === 'history' && input.hubHistoryMonths.length !== 1) return null;
  if (input.activeTab === 'agents' && (input.agentsSection === 'grile' || input.agentsSection === 'analysis')) return null;
  return buildCurrentRetailContextState(input);
}
