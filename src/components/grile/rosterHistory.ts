import type { CalendarData } from '../../api/grileCalendar';
import { getCurrentYearMonth } from '../../lib/dates';
type Agent = CalendarData['roster'][number];
export function homeOn(agent: Agent, date: string) {
  let home = agent.home_site_code;
  for (const transfer of [...(agent.transfers ?? [])].sort((a, b) => a.effective_from.localeCompare(b.effective_from) || a.roster_revision - b.roster_revision)) {
    if (transfer.effective_from <= date) home = transfer.home_site_code;
  }
  return home;
}
export function rosterDate(month: string) {
  if (month === getCurrentYearMonth()) return new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Bucharest', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
  return `${month}-31`;
}
export function currentRoster(data: CalendarData) {
  return data.roster.map(r => ({ ...r, home_site_code: homeOn(r, rosterDate(data.month)) }));
}
