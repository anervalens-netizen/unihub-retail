export function getMonthEndDate(month: string): string {
  const [year = 0, monthIndex = 1] = month.split('-').map(Number);
  const lastDay = new Date(year, monthIndex, 0).getDate();
  return `${month}-${String(lastDay).padStart(2, '0')}`;
}

export function displayStoreName(storeName: string | null | undefined): string {
  if (!storeName) return '';
  return storeName.includes(' - ') ? storeName.split(' - ').slice(1).join(' - ') : storeName;
}

export function achievementColor(ach: number | null): string {
  if (ach === null || ach === undefined) return 'text-slate-400';
  if (ach >= 1) return 'text-emerald-600 font-black';
  if (ach >= 0.9) return 'text-amber-500 font-semibold';
  return 'text-red-500';
}

export function achievementLabel(ach: number | null): string {
  if (ach === null || ach === undefined) return '—';
  return `${Math.round(ach * 100)}%`;
}
