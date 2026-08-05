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

export const EUROPE_BUCHAREST_TIME_ZONE = 'Europe/Bucharest';

type MonthLabelOptions = {
  month?: 'short' | 'long';
  year?: 'short' | 'full';
  separator?: ' ' | '-';
};

type IsoDateFormatOptions = Pick<Intl.DateTimeFormatOptions, 'day' | 'month' | 'year'>;

const YEAR_MONTH_PATTERN = /^(\d{4})-(0[1-9]|1[0-2])$/;
const ISO_DATE_PATTERN = /^(\d{4})-(\d{2})-(\d{2})$/;

function formatParts(value: Date): Record<string, string> {
  return Object.fromEntries(
    new Intl.DateTimeFormat('en-CA', {
      timeZone: EUROPE_BUCHAREST_TIME_ZONE,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    })
      .formatToParts(value)
      .filter(({ type }) => type !== 'literal')
      .map(({ type, value: partValue }) => [type, partValue]),
  );
}

function isValidCalendarDate(year: number, month: number, day: number): boolean {
  const date = new Date(Date.UTC(year, month - 1, day, 12));
  return date.getUTCFullYear() === year && date.getUTCMonth() === month - 1 && date.getUTCDate() === day;
}

function parseIsoCalendarDate(value: string): Date | null {
  const match = ISO_DATE_PATTERN.exec(value);
  if (!match) return null;

  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  if (!isValidCalendarDate(year, month, day)) return null;
  return new Date(Date.UTC(year, month - 1, day, 12));
}

function parseIsoDate(value: string): Date | null {
  const calendarDate = parseIsoCalendarDate(value);
  if (calendarDate) return calendarDate;
  if (!/(?:Z|[+-]\d{2}:?\d{2})$/.test(value)) return null;

  const timestamp = Date.parse(value);
  return Number.isFinite(timestamp) ? new Date(timestamp) : null;
}

export function getCurrentYearMonth(now?: Date): string {
  const parts = formatParts(now ?? new Date());
  return `${parts.year}-${parts.month}`;
}

export function formatIsoDateInput(value: Date = new Date()): string {
  const parts = formatParts(value);
  return `${parts.year}-${parts.month}-${parts.day}`;
}

export function shiftIsoDate(value: string, offset: number): string {
  const date = parseIsoCalendarDate(value);
  if (!date || !Number.isInteger(offset)) return value;

  const shifted = new Date(date.getTime());
  shifted.setUTCDate(shifted.getUTCDate() + offset);
  return [
    shifted.getUTCFullYear(),
    String(shifted.getUTCMonth() + 1).padStart(2, '0'),
    String(shifted.getUTCDate()).padStart(2, '0'),
  ].join('-');
}

export function parseIsoTimestamp(value: string | null | undefined): number | null {
  if (!value) return null;
  const date = parseIsoDate(value);
  return date?.getTime() ?? null;
}

export function formatIsoDate(
  value: string | null | undefined,
  options: IsoDateFormatOptions = { day: 'numeric', month: 'short' },
): string {
  const date = value ? parseIsoDate(value) : null;
  if (!date) return '—';

  return new Intl.DateTimeFormat('ro-RO', {
    ...options,
    timeZone: EUROPE_BUCHAREST_TIME_ZONE,
  }).format(date);
}

export function formatIsoMonth(
  value: string | null | undefined,
  options: IsoDateFormatOptions = { month: 'short', year: '2-digit' },
): string {
  const parsed = value ? parseYearMonth(value) : null;
  if (!parsed) return '—';

  const date = new Date(Date.UTC(Number(parsed.year), parsed.monthIndex, 1, 12));
  return new Intl.DateTimeFormat('ro-RO', {
    ...options,
    timeZone: EUROPE_BUCHAREST_TIME_ZONE,
  }).format(date);
}

function parseYearMonth(value: string): { year: string; monthIndex: number } | null {
  const match = YEAR_MONTH_PATTERN.exec(value);
  const year = match?.[1];
  const month = match?.[2];
  if (!year || !month) return null;
  return { year, monthIndex: Number(month) - 1 };
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

  const date = new Date(Date.UTC(Number(parsed.year), parsed.monthIndex + offset, 1));
  const month = String(date.getUTCMonth() + 1).padStart(2, '0');
  return `${date.getUTCFullYear()}-${month}`;
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
