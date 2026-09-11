import { client } from './client';
import type { AppFilters } from '../lib/appFilters';
import type { RetailContextUrlState } from '../lib/insightDeepLink';

export type SavedViewModule = 'hub' | 'focus' | 'agents' | 'management';

export interface SavedViewApiState {
  tab: SavedViewModule;
  period?: string | null;
  filters: AppFilters;
  section?: string | null;
  subtab?: string | null;
}

export interface SavedViewItem {
  id: number;
  module_id: SavedViewModule;
  name: string;
  state: SavedViewApiState;
  schema_version: 1;
  created_at: string;
  updated_at: string;
}

interface SavedViewListResponse { items: SavedViewItem[] }
interface SavedViewDeleteResponse { ok: boolean }

export function toSavedViewApiState(state: RetailContextUrlState): SavedViewApiState {
  if (state.tab === 'settings') throw new Error('Settings cannot be saved as a view');
  const base = {
    tab: state.tab,
    period: state.period,
    filters: {
      ...state.filters,
      magazin: [...state.filters.magazin],
      agent: [...state.filters.agent],
    },
  };
  if (state.tab === 'hub') return { ...base, section: state.hubSection ?? 'current' };
  if (state.tab === 'focus') return { ...base, section: state.campaignSection ?? 'incentive' };
  if (state.tab === 'agents') return { ...base, section: state.agentsSection ?? 'overview' };
  return { ...base, subtab: state.managementSubtab ?? 'asm' };
}

export function toRetailContextUrlState(state: SavedViewApiState): RetailContextUrlState {
  const base = {
    tab: state.tab,
    period: state.period ?? undefined,
    filters: {
      ...state.filters,
      magazin: [...state.filters.magazin],
      agent: [...state.filters.agent],
    },
  };
  if (state.tab === 'hub') {
    return { ...base, hubSection: state.section as 'current' | 'history' | 'visits' };
  }
  if (state.tab === 'focus') {
    return {
      ...base,
      campaignSection: state.section as 'incentive' | 'promo' | 'concurs' | 'premium' | 'focus',
    };
  }
  if (state.tab === 'agents') {
    return { ...base, agentsSection: state.section as 'overview' | 'grile' | 'analysis' };
  }
  return {
    ...base,
    managementSubtab: state.subtab as 'asm' | 'target-calculator' | 'salarii' | 'pnl',
  };
}

export async function listSavedViews(signal?: AbortSignal): Promise<SavedViewItem[]> {
  const { data } = await client.get<SavedViewListResponse>('/api/saved-views', { signal });
  return data.items;
}

export async function createSavedView(
  name: string,
  state: RetailContextUrlState,
): Promise<SavedViewItem> {
  const { data } = await client.post<SavedViewItem>('/api/saved-views', {
    name,
    state: toSavedViewApiState(state),
  });
  return data;
}

export async function deleteSavedView(viewId: number): Promise<void> {
  const { data } = await client.delete<SavedViewDeleteResponse>(`/api/saved-views/${viewId}`);
  if (!data.ok) throw new Error('Saved view delete was not acknowledged');
}
