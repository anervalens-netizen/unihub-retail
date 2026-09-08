import { client } from './client';
import { generatedGet, generatedPatch } from './generated/client';
import { decodeRetail } from './generated/decoded';
import type { RetailCalendarDayInput, RetailRosterInput } from './generated/contracts';

export const readCalendar = (month: string, signal?: AbortSignal) => generatedGet('read_calendar_api_grile_calendar__month__get', { pathParams: { month }, signal });
export const calendarCandidates = (month: string, signal?: AbortSignal) => generatedGet('candidates_api_grile_calendar__month__candidates_get', { pathParams: { month }, signal });
export const calendarStores = (signal?: AbortSignal) => generatedGet('list_stores_api_stores_get', { signal });
export const saveCalendarDays = (month: string, days: RetailCalendarDayInput[]) => generatedPatch('save_days_api_grile_calendar__month__days_patch', { days }, { pathParams: { month } });
export async function confirmCalendarAgent(month: string, code: string, body: RetailRosterInput) {
  const response = await client.put(`/api/grile/calendar/${encodeURIComponent(month)}/roster/${encodeURIComponent(code)}`, body);
  return decodeRetail('save_roster_api_grile_calendar__month__roster__agent_code__put', response.data);
}
export type CalendarData = Awaited<ReturnType<typeof readCalendar>>;
export type CalendarStore = Awaited<ReturnType<typeof calendarStores>>[number];
