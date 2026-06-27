export const RO_MONTHS_SHORT = [
  'Ian',
  'Feb',
  'Mar',
  'Apr',
  'Mai',
  'Iun',
  'Iul',
  'Aug',
  'Sep',
  'Oct',
  'Noi',
  'Dec',
];

export const RO_MONTHS_LONG = [
  'Ianuarie',
  'Februarie',
  'Martie',
  'Aprilie',
  'Mai',
  'Iunie',
  'Iulie',
  'August',
  'Septembrie',
  'Octombrie',
  'Noiembrie',
  'Decembrie',
];

type MonthLabelOptions = {
  month?: 'short' | 'long';
  year?: 'short' | 'full';
  separator?: ' ' | '-';
};

function parseYearMonth(value: string): { year: string; monthIndex: number } | null {
  const [year, month] = value.split('-');
  const monthIndex = Number(month) - 1;
  if (!year || !Number.isInteger(monthIndex) || monthIndex < 0 || monthIndex > 11) {
    return null;
  }
  return { year, monthIndex };
}

export function formatMonthLabel(value: string, options: MonthLabelOptions = {}): string {
  const parsed = parseYearMonth(value);
  if (!parsed) return value;

  const labels = options.month === 'long' ? RO_MONTHS_LONG : RO_MONTHS_SHORT;
  const year = options.year === 'short' ? parsed.year.slice(2) : parsed.year;
  return `${labels[parsed.monthIndex]}${options.separator ?? ' '}${year}`;
}

export function shiftMonth(value: string, offset: number): string {
  const parsed = parseYearMonth(value);
  if (!parsed) return value;

  const date = new Date(Number(parsed.year), parsed.monthIndex + offset, 1);
  const month = String(date.getMonth() + 1).padStart(2, '0');
  return `${date.getFullYear()}-${month}`;
}

export function formatMonthSpanLabel(span?: [number, number, number, number] | null): string {
  if (!span || !Array.isArray(span) || span.length !== 4) return '—';
  const [minYear, minMonth, maxYear, maxMonth] = span;
  const start = formatMonthLabel(`${minYear}-${String(minMonth).padStart(2, '0')}`, {
    year: 'short',
    separator: '-',
  });
  const end = formatMonthLabel(`${maxYear}-${String(maxMonth).padStart(2, '0')}`, {
    year: 'short',
    separator: '-',
  });
  return `${start} → ${end}`;
}
