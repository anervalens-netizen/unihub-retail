import { describe, expect, it } from 'vitest';
import { formatMonthLabel, formatMonthSpanLabel, shiftMonth } from './dates';

describe('date helpers', () => {
  it('formats Romanian month labels', () => {
    expect(formatMonthLabel('2026-06')).toBe('Iun 2026');
    expect(formatMonthLabel('2026-06', { year: 'short' })).toBe('Iun 26');
    expect(formatMonthLabel('2026-06', { month: 'long' })).toBe('Iunie 2026');
  });

  it('keeps invalid month labels unchanged', () => {
    expect(formatMonthLabel('custom')).toBe('custom');
    expect(formatMonthLabel('2026-13')).toBe('2026-13');
  });

  it('shifts months across year boundaries', () => {
    expect(shiftMonth('2026-12', 1)).toBe('2027-01');
    expect(shiftMonth('2026-01', -1)).toBe('2025-12');
  });

  it('formats month spans from API tuple shape', () => {
    expect(formatMonthSpanLabel([2025, 11, 2026, 6])).toBe('Noi-25 → Iun-26');
    expect(formatMonthSpanLabel(null)).toBe('—');
  });
});
