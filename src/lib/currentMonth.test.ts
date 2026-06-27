import { describe, expect, it } from 'vitest';
import { selectCurrentMonth } from './currentMonth';

describe('selectCurrentMonth', () => {
  it('uses the latest backend month as the current Hub month', () => {
    expect(selectCurrentMonth(['2026-06', '2026-05', '2026-04'])).toBe('2026-06');
  });

  it('returns an empty month when backend has no completed snapshots', () => {
    expect(selectCurrentMonth([])).toBe('');
  });
});
