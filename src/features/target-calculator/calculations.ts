import type { TargetScenario, TargetScenarioRow } from './api';
import { percentChangeValue, recalculateVisibleScenario, sum } from './model';

export { percentChangeValue, recalculateVisibleScenario, sum };

export function scenarioWorkflowStep(scenario: TargetScenario | null): 1 | 2 | 3 | 4 {
  if (!scenario) return 1;
  if (scenario.status === 'finalized') return 4;
  return scenario.manual_adjustments_count === 0 && scenario.pending_final_count === scenario.store_count ? 2 : 3;
}

export function rowsForRegional(
  rows: TargetScenarioRow[],
  regional: string,
): TargetScenarioRow[] {
  return regional === 'all' ? rows : rows.filter((row) => row.regional === regional);
}
