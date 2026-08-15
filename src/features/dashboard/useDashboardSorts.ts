import { useMemo } from 'react';

import type { AgentStat, RegionalStat, StoreStat } from '../../api/generated/runtime-types';
import { useSortable } from '../../lib/useSortable';
import {
  AGENT_ASC_SORT_KEYS, REGIONAL_ASC_SORT_KEYS, STORE_ASC_SORT_KEYS,
} from './dashboardColumns';
import type { AgentSortKey, RegionalSortKey, StoreSortKey } from './dashboardTypes';
import { getAgentSortValue, getRegionalSortValue, getStoreSortValue } from './DashboardWidgets';

interface SortRows {
  agents: AgentStat[];
  stores: StoreStat[];
  regionals: RegionalStat[];
  historyAgents: AgentStat[];
  historyStores: StoreStat[];
  historyRegionals: RegionalStat[];
}

function sortState<Key extends string>(sortKey: Key, direction: 'asc' | 'desc') {
  return { key: sortKey, direction };
}

export function useDashboardSorts(rows: SortRows) {
  const currentStore = useSortable<StoreStat, StoreSortKey>({
    rows: rows.stores, key: 'proc_realizare_target', defaultAscKeys: STORE_ASC_SORT_KEYS, getValue: getStoreSortValue,
  });
  const currentAgent = useSortable<AgentStat, AgentSortKey>({
    rows: rows.agents, key: 'total_vanzari', defaultAscKeys: AGENT_ASC_SORT_KEYS, getValue: getAgentSortValue,
  });
  const currentRegional = useSortable<RegionalStat, RegionalSortKey>({
    rows: rows.regionals, key: 'total_vanzari', defaultAscKeys: REGIONAL_ASC_SORT_KEYS, getValue: getRegionalSortValue,
  });
  const historyRegional = useSortable<RegionalStat, RegionalSortKey>({
    rows: rows.historyRegionals, key: 'total_vanzari', defaultAscKeys: REGIONAL_ASC_SORT_KEYS, getValue: getRegionalSortValue,
  });
  const historyStore = useSortable<StoreStat, StoreSortKey>({
    rows: rows.historyStores, key: 'total_vanzari', defaultAscKeys: STORE_ASC_SORT_KEYS, getValue: getStoreSortValue,
  });
  const historyAgent = useSortable<AgentStat, AgentSortKey>({
    rows: rows.historyAgents, key: 'total_vanzari', defaultAscKeys: AGENT_ASC_SORT_KEYS, getValue: getAgentSortValue,
  });
  const states = useMemo(() => ({
    storeSort: sortState(currentStore.sortKey, currentStore.direction),
    agentSort: sortState(currentAgent.sortKey, currentAgent.direction),
    regionalSort: sortState(currentRegional.sortKey, currentRegional.direction),
    historyRegionalSort: sortState(historyRegional.sortKey, historyRegional.direction),
    historyStoreSort: sortState(historyStore.sortKey, historyStore.direction),
    historyAgentSort: sortState(historyAgent.sortKey, historyAgent.direction),
  }), [
    currentAgent.direction, currentAgent.sortKey, currentRegional.direction, currentRegional.sortKey,
    currentStore.direction, currentStore.sortKey, historyAgent.direction, historyAgent.sortKey,
    historyRegional.direction, historyRegional.sortKey, historyStore.direction, historyStore.sortKey,
  ]);
  return { currentStore, currentAgent, currentRegional, historyRegional, historyStore, historyAgent, ...states };
}
