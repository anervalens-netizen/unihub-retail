import { describe, expect, it } from 'vitest';

import { defaultAppFilters } from './filterValues';
import { buildCurrentRetailContextState, buildCurrentSavedViewState } from './retailContextState';

const hubFilters = { ...defaultAppFilters(), firma: 'Arsis' };
const focusFilters = { ...defaultAppFilters(), rm: 'RM Est' };
const agentsFilters = { ...defaultAppFilters(), agent: ['Agent A'] };

function base() {
  return {
    activeTab: 'hub' as const,
    currentMonth: '2026-09',
    focusFilterMonth: '2026-08',
    hubHistoryMonths: ['2026-08'],
    hubFilters,
    focusFilters,
    agentsFilters,
    hubSection: 'history' as const,
    campaignSection: 'focus' as const,
    agentsSection: undefined,
    managementSubtab: 'asm' as const,
    hasManagementAccess: true,
  };
}

describe('retail context projection', () => {
  it('uses the selected single Hub History month', () => {
    expect(buildCurrentRetailContextState(base())).toEqual({
      tab: 'hub', period: '2026-08', filters: hubFilters, hubSection: 'history',
    });
  });

  it('uses Focus month/filters and canonical section', () => {
    expect(buildCurrentRetailContextState({ ...base(), activeTab: 'focus' })).toEqual({
      tab: 'focus', period: '2026-08', filters: focusFilters, campaignSection: 'focus',
    });
  });

  it('defaults Agents section and uses agent filters', () => {
    expect(buildCurrentRetailContextState({ ...base(), activeTab: 'agents' })).toEqual({
      tab: 'agents', period: '2026-09', filters: agentsFilters, agentsSection: 'overview',
    });
  });

  it('uses agent filters only for Management salaries in canonical URL projection', () => {
    expect(buildCurrentRetailContextState({ ...base(), activeTab: 'management', managementSubtab: 'salarii' })).toEqual({
      tab: 'management', period: '2026-09', filters: agentsFilters, managementSubtab: 'salarii',
    });
    expect(buildCurrentRetailContextState({ ...base(), activeTab: 'management', managementSubtab: 'asm' })?.filters).toEqual(hubFilters);
  });

  it('does not expose Settings, unavailable periods or unauthorized Management', () => {
    expect(buildCurrentRetailContextState({ ...base(), activeTab: 'settings' })).toBeNull();
    expect(buildCurrentRetailContextState({ ...base(), currentMonth: '' })).toBeNull();
    expect(buildCurrentRetailContextState({ ...base(), activeTab: 'management', hasManagementAccess: false })).toBeNull();
  });

  it('refuses Saved Views that schema v1 cannot represent exactly', () => {
    expect(buildCurrentSavedViewState({ ...base(), hubHistoryMonths: ['2026-07', '2026-08'] })).toBeNull();
    expect(buildCurrentSavedViewState({ ...base(), hubSection: 'visits' })).toBeNull();
    expect(buildCurrentSavedViewState({ ...base(), activeTab: 'agents', agentsSection: 'grile' })).toBeNull();
    expect(buildCurrentSavedViewState({ ...base(), activeTab: 'agents', agentsSection: 'analysis' })).toBeNull();
    expect(buildCurrentSavedViewState({ ...base(), activeTab: 'management', managementSubtab: 'asm' })).toBeNull();
    expect(buildCurrentSavedViewState({ ...base(), activeTab: 'management', managementSubtab: 'salarii' })).toBeNull();
    expect(buildCurrentSavedViewState(base())?.period).toBe('2026-08');
  });
});
