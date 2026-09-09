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
export type CalendarStore = Awaited<ReturnType<typeof calendarStores>>[number] & { cleanupOnly?: boolean; virtualBase?: boolean };

export async function saveStoreHours(month: string, site: string, body: import('./generated/contracts').RetailStoreHoursInput) {
  const response = await client.put(`/api/grile/calendar/${encodeURIComponent(month)}/store-hours/${encodeURIComponent(site)}`, body);
  return decodeRetail('save_store_hours_api_grile_calendar__month__store_hours__site_code__put', response.data);
}
export async function downloadAttendance(month: string, revision: string) {
  const { downloadBlob } = await import('../lib/download');
  const response = await client.get<Blob>(`/api/grile/calendar/${encodeURIComponent(month)}/attendance.zip`, { params: { expected_revision: revision }, responseType: 'blob', timeoutMs: 120_000 });
  downloadBlob(response.data, `Pontaje-provizorii-${month}.zip`);
}

export const readEarnings = (month: string, signal?: AbortSignal) => generatedGet('read_earnings_api_grile_calendar__month__earnings_get', { pathParams: { month }, signal });

export async function downloadEarnings(month: string, revision: string) {
  const { downloadBlob } = await import('../lib/download');
  const response = await client.get<Blob>(`/api/grile/calendar/${encodeURIComponent(month)}/earnings.zip`, { params: { expected_revision: revision }, responseType: 'blob', timeoutMs: 120_000 });
  downloadBlob(response.data, `Grile-pontaje-provizorii-${month}.zip`);
}

export async function saveCompensation(month: string, code: string, body: import('./generated/contracts').RetailCompensationInput) {
  const response = await client.put(`/api/grile/calendar/${encodeURIComponent(month)}/compensation/${encodeURIComponent(code)}`, body);
  return decodeRetail('save_compensation_api_grile_calendar__month__compensation__agent_code__put', response.data);
}
