import { describe, expect, it } from 'vitest';

import { MGMT_SUBTABS, MGMT_SUBTAB_LABELS } from './tabs';

describe('navigation contract', () => {
  it('keeps salaries in Management and removes Grile from Management', () => {
    const ids: string[] = MGMT_SUBTABS.map((tab) => tab.id);
    expect(ids).toEqual([
      'asm',
      'target-calculator',
      'salarii',
      'pnl',
    ]);
    expect(MGMT_SUBTAB_LABELS.salarii).toBe('Salarii');
    expect(ids).not.toContain('grile');
  });
});
