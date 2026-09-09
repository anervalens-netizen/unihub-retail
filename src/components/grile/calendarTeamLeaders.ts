import type { CalendarStore } from '../../api/grileCalendar';

// Owner-confirmed store responsibility from the September 2026 schedules.
// Visiting shifts do not change the Team Leader responsible for a store.
const confirmedTeams = [
  { code: 'LAUR', label: 'Laurențiu Cernat', sites: ['PRKLK', 'CRFFEER', 'MCRFBAL', 'MEGAMALL', 'PROM', 'MC-MEGAMALL', 'PROMEN'] },
  { code: 'VDELIA', label: 'Delia Vacalie', sites: ['AUCHMIL2', 'SUNPLZ', 'UNIRII', 'COTROCENI', 'CORALEX', 'AUCHTRIC', 'AUCHMILI', 'AFICOTRO'] },
  { code: 'DAVIDDA', label: 'TL Constanța', sites: ['CCTCIT', 'CTCORA', 'CTVIVO', 'CTCRFTOM', 'CTCITYPRK', 'CTAUCH'] },
];

export function calendarTeamGroups(stores: CalendarStore[]) {
  const groups = confirmedTeams.map(team => ({ ...team, stores: stores.filter(store => store.regional === 'Andrei Stancu' && team.sites.includes(store.site_code)) }));
  const assigned = new Set(groups.flatMap(group => group.stores.map(store => store.site_code)));
  const remaining = stores.filter(store => !assigned.has(store.site_code));
  return [...groups, { code: '', label: 'Fără Team Leader alocat', sites: [], stores: remaining }].filter(group => group.stores.length);
}
