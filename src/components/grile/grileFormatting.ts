import { parseIsoTimestamp } from '../../lib/dates';

const NUMBER = new Intl.NumberFormat('ro-RO');

export function formatGrileNumber(value: number | null | undefined) {
  return value == null ? '—' : NUMBER.format(Math.round(value));
}

export function formatGrileDifference(value: number | null) {
  if (value == null) return '—';
  const rounded = Math.round(value);
  return `${rounded > 0 ? '+' : ''}${NUMBER.format(rounded)}`;
}

export function relativeGrileTime(iso: string | null) {
  if (!iso) return '—';
  const timestamp = parseIsoTimestamp(iso);
  if (timestamp === null) return '—';
  const hours = Math.floor((Date.now() - timestamp) / 3_600_000);
  if (hours < 1) return `${Math.max(1, Math.floor((Date.now() - timestamp) / 60_000))}m`;
  if (hours < 24) return `acum ${hours}h`;
  const days = Math.floor(hours / 24);
  return days === 1 ? 'ieri' : `${days}z`;
}
