export function selectCurrentMonth(availableMonths: readonly string[]): string {
  return availableMonths[0] ?? '';
}
