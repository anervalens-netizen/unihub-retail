import { beforeEach, describe, expect, it, vi } from 'vitest';

const get = vi.fn();
const post = vi.fn();
const del = vi.fn();

vi.mock('./client', () => ({
  client: { get, post, delete: del },
}));

import {
  createSavedView,
  deleteSavedView,
  listSavedViews,
  toRetailContextUrlState,
  toSavedViewApiState,
} from './savedViews';

const filters = { firma: 'Arsis', rm: 'RM Est', magazin: ['M1'], agent: ['A1'] };
const saved = {
  id: 7,
  module_id: 'hub' as const,
  name: 'Istoric Est',
  state: { tab: 'hub' as const, period: '2026-09', filters, section: 'history' },
  schema_version: 1 as const,
  created_at: '2026-09-11T10:00:00Z',
  updated_at: '2026-09-11T10:00:00Z',
};

describe('saved views API client', () => {
  beforeEach(() => {
    get.mockReset();
    post.mockReset();
    del.mockReset();
  });

  it('maps canonical URL state to the backend contract and back', () => {
    const state = {
      tab: 'hub' as const,
      period: '2026-09',
      filters,
      hubSection: 'history' as const,
    };
    expect(toSavedViewApiState(state)).toEqual(saved.state);
    expect(toRetailContextUrlState(saved.state)).toEqual(state);
  });

  it('maps the remaining module-specific context fields', () => {
    expect(toSavedViewApiState({ tab: 'focus', period: '2026-09', filters, campaignSection: 'promo' }).section).toBe('promo');
    expect(toSavedViewApiState({ tab: 'agents', period: '2026-09', filters }).section).toBe('overview');
    expect(toSavedViewApiState({ tab: 'management', period: '2026-09', filters, managementSubtab: 'salarii' }).subtab).toBe('salarii');
    expect(() => toSavedViewApiState({ tab: 'settings', filters })).toThrow(/Settings/);
  });

  it('lists, creates and deletes through the canonical API client', async () => {
    get.mockResolvedValue({ data: { items: [saved] } });
    post.mockResolvedValue({ data: saved });
    del.mockResolvedValue({ data: { ok: true } });

    await expect(listSavedViews()).resolves.toEqual([saved]);
    await expect(createSavedView('Istoric Est', {
      tab: 'hub', period: '2026-09', filters, hubSection: 'history',
    })).resolves.toEqual(saved);
    await expect(deleteSavedView(7)).resolves.toBeUndefined();

    expect(get).toHaveBeenCalledWith('/api/saved-views', { signal: undefined });
    expect(post).toHaveBeenCalledWith('/api/saved-views', {
      name: 'Istoric Est',
      state: saved.state,
    });
    expect(del).toHaveBeenCalledWith('/api/saved-views/7');
  });

  it('fails closed when delete is not acknowledged', async () => {
    del.mockResolvedValue({ data: { ok: false } });
    await expect(deleteSavedView(7)).rejects.toThrow(/not acknowledged/);
  });
});
