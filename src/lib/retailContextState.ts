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
  const period = input.activeTab === 'focus'
    ? input.focusFilterMonth || input.currentMonth
    : input.currentMonth;

  if (input.activeTab === 'hub') {
    return { tab: 'hub', period, filters, hubSection: input.hubSection };
  }
  if (input.activeTab === 'focus') {
    return { tab: 'focus', period, filters, campaignSection: input.campaignSection };
  }
  if (input.activeTab === 'agents') {
    return {
      tab: 'agents',
      period,
      filters,
      agentsSection: input.agentsSection ?? 'overview',
    };
  }
  return {
    tab: 'management',
    period,
    filters,
    managementSubtab: input.managementSubtab,
  };
}
