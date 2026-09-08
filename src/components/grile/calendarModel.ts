import type { RetailCalendarDayInput } from '../../api/generated/contracts';
import type { CalendarData } from '../../api/grileCalendar';

export const dayLabels = { work: 'Lucrează', leave: 'Concediu', off: 'Liber', cancelled: 'Anulat' };

export function monthDays(month: string) {
  const start = new Date(`${month}-01T12:00:00Z`);
  const count = new Date(Date.UTC(start.getUTCFullYear(), start.getUTCMonth() + 1, 0)).getUTCDate();
  return { offset: (start.getUTCDay() + 6) % 7, dates: Array.from({ length: count }, (_, i) => `${month}-${String(i + 1).padStart(2, '0')}`) };
}

// Every affected person/day carries the revision seen when the editor opened.
export function dayChanges(data: CalendarData, input: Omit<RetailCalendarDayInput, 'expected_revision'>): RetailCalendarDayInput[] {
  const existing = data.days.find(d => d.agent_code === input.agent_code && d.work_date === input.work_date);
  const changes: RetailCalendarDayInput[] = [];
  if (input.status === 'work') {
    const occupant = data.days.find(d => d.work_date === input.work_date && d.site_code === input.site_code && d.status === 'work' && d.agent_code !== input.agent_code);
    if (occupant) changes.push({ ...occupant, status: 'cancelled', supplemental: false, expected_revision: occupant.revision });
  }
  changes.push({ ...input, expected_revision: existing?.revision ?? 0 });
  // Response-only revision must never leak into extra=forbid request bodies.
  return changes.map(({ work_date, agent_code, site_code, status, supplemental, expected_revision }) => ({ work_date, agent_code, site_code, status, supplemental, expected_revision }));
}
