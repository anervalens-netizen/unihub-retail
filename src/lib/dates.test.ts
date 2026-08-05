import { describe, expect, it } from 'vitest';
import {
  formatIsoDate,
  formatIsoDateInput,
  formatIsoMonth,
  formatMonthLabel,
  formatMonthSpanLabel,
  getCurrentYearMonth,
  shiftIsoDate,
  shiftMonth,
} from './dates';

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

  it('uses Europe/Bucharest for current month at a UTC boundary', () => {
    expect(getCurrentYearMonth(new Date('2026-07-31T21:30:00Z'))).toBe('2026-08');
  });

  it('formats ISO dates and months safely in Europe/Bucharest', () => {
    expect(formatIsoDate('2026-07-31')).toBe('31 iul.');
    expect(formatIsoDate('2026-07-31T22:30:00Z')).toBe('1 aug.');
    expect(formatIsoMonth('2026-07', { month: 'long', year: 'numeric' })).toBe('iulie 2026');
    expect(formatIsoDate('2026-02-30')).toBe('—');
    expect(formatIsoMonth('2026-13')).toBe('—');
  });

  it('formats date inputs and calendar shifts independently of host timezone', () => {
    expect(formatIsoDateInput(new Date('2026-07-31T21:30:00Z'))).toBe('2026-08-01');
    expect(shiftIsoDate('2026-03-01', -1)).toBe('2026-02-28');
  });
});
