import type { SeasonalityMode } from '../components/SeasonalityControl';

export function seasonalityModeFromYears(years: number | null | undefined): Exclude<SeasonalityMode, null> {
  return Number(years ?? 1) > 1 ? 'multi' : 'single';
}

export function seasonalityYearsFromMode(mode: Exclude<SeasonalityMode, null>): number {
  return mode === 'multi' ? 3 : 1;
}

export function resolveSeasonalityMode({
  scenarioYears,
  manualMode,
  backendDefaultYears,
}: {
  scenarioYears?: number | null;
  manualMode: Exclude<SeasonalityMode, null> | null;
  backendDefaultYears: number;
}): Exclude<SeasonalityMode, null> {
  if (manualMode !== null) return manualMode;
  if (scenarioYears !== undefined && scenarioYears !== null) {
    return seasonalityModeFromYears(scenarioYears);
  }
  return seasonalityModeFromYears(backendDefaultYears);
}
