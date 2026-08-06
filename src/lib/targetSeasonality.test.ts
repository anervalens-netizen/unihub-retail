import { describe, expect, it } from 'vitest';

import { resolveSeasonalityMode, seasonalityModeFromYears, seasonalityYearsFromMode } from './targetSeasonality';

describe('target seasonality precedence values', () => {
  it('maps backend defaults to the displayed mode', () => {
    expect(seasonalityModeFromYears(1)).toBe('single');
    expect(seasonalityModeFromYears(3)).toBe('multi');
  });

  it('maps the displayed mode to the calculation payload', () => {
    expect(seasonalityYearsFromMode('single')).toBe(1);
    expect(seasonalityYearsFromMode('multi')).toBe(3);
  });

  it('keeps manual selection ahead of scenario and backend defaults', () => {
    expect(resolveSeasonalityMode({ manualMode: 'single', scenarioYears: 3, backendDefaultYears: 3 })).toBe('single');
    expect(resolveSeasonalityMode({ manualMode: null, scenarioYears: 1, backendDefaultYears: 3 })).toBe('single');
    expect(resolveSeasonalityMode({ manualMode: null, scenarioYears: null, backendDefaultYears: 3 })).toBe('multi');
  });
});
