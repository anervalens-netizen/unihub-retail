import { describe, expect, it } from 'vitest';

import { rowsForRegional, scenarioWorkflowStep } from './calculations';
import type { TargetScenario, TargetScenarioRow } from './api';

describe('Target Calculator view calculations', () => {
  it('keeps the workflow state machine aligned with the scenario lifecycle', () => {
    expect(scenarioWorkflowStep(null)).toBe(1);
    expect(scenarioWorkflowStep({
      status: 'draft', manual_adjustments_count: 0, pending_final_count: 2, store_count: 2,
    } as TargetScenario)).toBe(2);
    expect(scenarioWorkflowStep({
      status: 'draft', manual_adjustments_count: 1, pending_final_count: 1, store_count: 2,
    } as TargetScenario)).toBe(3);
    expect(scenarioWorkflowStep({ status: 'finalized' } as TargetScenario)).toBe(4);
  });

  it('filters only the requested manager without changing the source row order', () => {
    const rows = [
      { site_code: 'A', regional: 'Nord' },
      { site_code: 'B', regional: 'Sud' },
      { site_code: 'C', regional: 'Nord' },
    ] as TargetScenarioRow[];

    expect(rowsForRegional(rows, 'all')).toBe(rows);
    expect(rowsForRegional(rows, 'Nord').map((row) => row.site_code)).toEqual(['A', 'C']);
  });
});
