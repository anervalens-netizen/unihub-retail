import type { AppFilters } from './appFilters';
import { ALL_FIRMS, ALL_SCOPE } from './filterValues';
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

export interface RetailContextUrlState {
  tab: TabId;
  period?: string;
  filters: AppFilters;
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
const CONTEXT_SOURCES = new Set(['insight', 'retail']);
const MAX_FILTER_VALUE_LENGTH = 180;
const MAX_SELECTION_ITEMS = 50;
const TAB_PATHS: Record<TabId, string> = {
  hub: '/hub',
  focus: '/focus',
  agents: '/agenti',
  management: '/management',
  settings: '/settings',
};

function bounded(value: string | null | undefined, maximum: number): string | undefined {
  const normalized = value?.trim();
  return normalized && normalized.length <= maximum ? normalized : undefined;
}

function canonicalSelection(values: Iterable<string>): string[] {
  const result: string[] = [];
  const seen = new Set<string>();
  for (const raw of values) {
    const value = bounded(raw, MAX_FILTER_VALUE_LENGTH);
    if (!value || seen.has(value)) continue;
    seen.add(value);
    result.push(value);
    if (result.length >= MAX_SELECTION_ITEMS) break;
  }
  return result;
}

function filterValue(params: URLSearchParams, key: string, alias?: string): string | undefined {
  return bounded(params.get(key) ?? (alias ? params.get(alias) : null), MAX_FILTER_VALUE_LENGTH);
}

function repeatedValues(params: URLSearchParams, key: string, alias?: string): string[] {
  return canonicalSelection([
    ...params.getAll(key),
    ...(alias ? params.getAll(alias) : []),
  ]);
}

function appendFilters(params: URLSearchParams, filters: AppFilters) {
  const firma = bounded(filters.firma, MAX_FILTER_VALUE_LENGTH);
  const rm = bounded(filters.rm, MAX_FILTER_VALUE_LENGTH);
  if (firma && firma !== ALL_FIRMS) params.set('firma', firma);
  if (rm && rm !== ALL_SCOPE) params.set('rm', rm);
  canonicalSelection(filters.magazin).forEach((value) => params.append('magazin', value));
  canonicalSelection(filters.agent).forEach((value) => params.append('agent', value));
}

export function buildRetailContextUrl(state: RetailContextUrlState): string {
  const params = new URLSearchParams();
  params.set('source_context', 'retail');

  if (state.tab !== 'settings') {
    const period = bounded(state.period, 7);
    if (period && MONTH.test(period)) params.set('period', period);
    appendFilters(params, state.filters);
  }

  if (state.tab === 'hub') params.set('section', state.hubSection ?? 'current');
  else if (state.tab === 'focus') params.set('section', state.campaignSection ?? 'incentive');
  else if (state.tab === 'agents') params.set('section', state.agentsSection ?? 'overview');
  else if (state.tab === 'management') params.set('subtab', state.managementSubtab ?? 'asm');

  return `${TAB_PATHS[state.tab]}?${params.toString()}`;
}

export function parseInsightDeepLink(location: Pick<Location, 'pathname' | 'search'>): InsightDeepLink | null {
  const params = new URLSearchParams(location.search);
  const sourceContext = params.get('source_context') ?? '';
  if (!CONTEXT_SOURCES.has(sourceContext)) return null;

  const path = location.pathname.replace(/\/+$/, '') || '/';
  let tab: TabId;
  if (path === '/hub' || path === '/') tab = 'hub';
  else if (path === '/focus') tab = 'focus';
  else if (path === '/agenti' || path === '/agents') tab = 'agents';
  else if (path === '/management' || path === '/management/pnl') tab = 'management';
  else if (path === '/settings') tab = 'settings';
  else return null;

  if (tab === 'settings') return { tab, filters: {} };

  const periodValue = bounded(params.get('period'), 7);
  const period = periodValue && MONTH.test(periodValue) ? periodValue : undefined;
  const firma = filterValue(params, 'firma', 'firm');
  const rm = filterValue(params, 'rm', 'regional');
  const explicitStores = repeatedValues(params, 'magazin', 'store');
  const storeList = bounded(params.get('stores'), 2_000)
    ?.split(',') ?? [];
  const magazin = explicitStores.length > 0 ? explicitStores : canonicalSelection(storeList);
  const agents = repeatedValues(params, 'agent');
  const filters: Partial<AppFilters> = sourceContext === 'retail'
    ? {
        firma: firma ?? ALL_FIRMS,
        rm: rm ?? ALL_SCOPE,
        magazin,
        agent: agents,
      }
    : {
        ...(firma ? { firma } : {}),
        ...(rm ? { rm } : {}),
        ...(magazin.length ? { magazin } : {}),
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
