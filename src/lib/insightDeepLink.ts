import type { AppFilters } from './appFilters';
import type { ManagementTab, TabId } from './tabs';

export type InsightHubSection = 'current' | 'history' | 'visits';
export type InsightCampaignSection = 'incentive' | 'promo' | 'concurs' | 'premium' | 'focus';
export type InsightAgentsSection = 'overview' | 'grile' | 'analysis';

export interface InsightDeepLink {
  tab: TabId;
  period?: string;
  filters: Partial<AppFilters>;
  hubSection?: InsightHubSection;
  campaignSection?: InsightCampaignSection;
  agentsSection?: InsightAgentsSection;
  managementSubtab?: ManagementTab;
}

const MONTH = /^\d{4}-(0[1-9]|1[0-2])$/;
const HUB_SECTIONS = new Set<InsightHubSection>(['current', 'history', 'visits']);
const CAMPAIGN_SECTIONS = new Set<InsightCampaignSection>([
  'incentive',
  'promo',
  'concurs',
  'premium',
  'focus',
]);
const AGENTS_SECTIONS = new Set<InsightAgentsSection>(['overview', 'grile', 'analysis']);
const MANAGEMENT_SUBTABS = new Set<ManagementTab>(['asm', 'target-calculator', 'salarii', 'pnl']);

function bounded(value: string | null, maximum: number): string | undefined {
  const normalized = value?.trim();
  return normalized && normalized.length <= maximum ? normalized : undefined;
}

function filterValue(params: URLSearchParams, key: string, alias?: string): string | undefined {
  return bounded(params.get(key) ?? (alias ? params.get(alias) : null), 180);
}

export function parseInsightDeepLink(location: Pick<Location, 'pathname' | 'search'>): InsightDeepLink | null {
  const params = new URLSearchParams(location.search);
  if (params.get('source_context') !== 'insight') return null;

  const path = location.pathname.replace(/\/+$/, '') || '/';
  let tab: TabId;
  if (path === '/hub' || path === '/') tab = 'hub';
  else if (path === '/focus') tab = 'focus';
  else if (path === '/agenti' || path === '/agents') tab = 'agents';
  else if (path === '/management' || path === '/management/pnl') tab = 'management';
  else return null;

  const periodValue = bounded(params.get('period'), 7);
  const period = periodValue && MONTH.test(periodValue) ? periodValue : undefined;
  const firma = filterValue(params, 'firma', 'firm');
  const rm = filterValue(params, 'rm', 'regional');
  const explicitStores = [
    ...params.getAll('magazin'),
    ...params.getAll('store'),
  ].map((value) => value.trim()).filter(Boolean);
  const storeList = bounded(params.get('stores'), 2_000)
    ?.split(',')
    .map((value) => value.trim())
    .filter(Boolean);
  const magazin = Array.from(new Set(explicitStores.length > 0 ? explicitStores : storeList));
  const agents = Array.from(new Set(
    params.getAll('agent').map((value) => value.trim()).filter(Boolean),
  ));
  const filters: Partial<AppFilters> = {
    ...(firma ? { firma } : {}),
    ...(rm ? { rm } : {}),
    ...(magazin?.length ? { magazin } : {}),
    ...(agents.length ? { agent: agents } : {}),
  };
  const section = bounded(params.get('section'), 40);
  const subtab = bounded(params.get('subtab'), 40);

  if (tab === 'hub') {
    const hubSection = HUB_SECTIONS.has(section as InsightHubSection)
      ? (section as InsightHubSection)
      : 'current';
    return { tab, filters, hubSection, ...(period ? { period } : {}) };
  }
  if (tab === 'focus') {
    const campaignSection = CAMPAIGN_SECTIONS.has(section as InsightCampaignSection)
      ? (section as InsightCampaignSection)
      : 'focus';
    return { tab, filters, campaignSection, ...(period ? { period } : {}) };
  }
  if (tab === 'agents') {
    const agentsSection = AGENTS_SECTIONS.has(section as InsightAgentsSection)
      ? (section as InsightAgentsSection)
      : 'overview';
    return { tab, filters, agentsSection, ...(period ? { period } : {}) };
  }
  const requestedSubtab = path === '/management/pnl' ? 'pnl' : subtab;
  const managementSubtab = MANAGEMENT_SUBTABS.has(requestedSubtab as ManagementTab)
    ? (requestedSubtab as ManagementTab)
    : 'asm';
  return { tab, filters, managementSubtab, ...(period ? { period } : {}) };
}
