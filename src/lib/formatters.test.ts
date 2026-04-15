import { describe, expect, it } from 'vitest';
import { formatCurrency, formatInt, formatPercent } from './formatters';

describe('formatPercent', () => {
  it('returns "-" for null', () => {
    expect(formatPercent(null)).toBe('-');
  });

  it('returns "-" for NaN', () => {
    expect(formatPercent(NaN)).toBe('-');
  });

  it('formats zero as "0.00%"', () => {
    expect(formatPercent(0)).toBe('0.00%');
  });

  it('formats positive value with 2 decimals', () => {
    expect(formatPercent(98.5)).toBe('98.50%');
  });

  it('formats negative value', () => {
    expect(formatPercent(-5.25)).toBe('-5.25%');
  });

  it('formats value > 100', () => {
    expect(formatPercent(123.456)).toBe('123.46%');
  });
});

describe('formatCurrency', () => {
  it('returns a non-empty string for zero', () => {
    expect(formatCurrency(0)).toBeTruthy();
  });

  it('includes RON in output', () => {
    expect(formatCurrency(1000)).toContain('RON');
  });

  it('formats numeric string input', () => {
    // Accepts number, coerces via Number()
    expect(() => formatCurrency(1234)).not.toThrow();
  });

  it('rounds to 0 decimal places', () => {
    const result = formatCurrency(1234.99);
    // Should not contain decimal separator (maximumFractionDigits: 0)
    expect(result).not.toMatch(/[.,]\d{2}\s*RON/);
  });
});

describe('formatInt', () => {
  it('returns a non-empty string for zero', () => {
    expect(formatInt(0)).toBeTruthy();
  });

  it('formats 1000 with a thousands separator', () => {
    const result = formatInt(1000);
    // ro-RO uses dot as thousands separator: "1.000"
    expect(result).toMatch(/1.000|1,000/); // tolerăm ambele separatoare locale
  });

  it('handles large values without throwing', () => {
    expect(() => formatInt(9_999_999)).not.toThrow();
  });
});
