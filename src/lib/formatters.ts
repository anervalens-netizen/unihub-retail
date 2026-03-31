export function formatCurrency(value: number) {
  return new Intl.NumberFormat('ro-RO', {
    style: 'currency',
    currency: 'RON',
    maximumFractionDigits: 0,
  }).format(Number(value));
}

export function formatInt(value: number) {
  return new Intl.NumberFormat('ro-RO').format(Number(value));
}

export function formatPercent(value: number | null) {
  if (value === null || Number.isNaN(value)) {
    return '-';
  }
  return `${Number(value).toFixed(2)}%`;
}
