// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest';
import { readCalendar, calendarCandidates, calendarStores, saveCalendarDays, confirmCalendarAgent } from './grileCalendar';
afterEach(() => vi.unstubAllGlobals());
it('uses the existing transport, encoded identity and decoded responses', async () => {
  const roster = { month: '2026-09', agent_code: 'AG/1', home_site_code: 'S1', active: true, revision: 1 };
  const fetch = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({ month: '2026-09', roster: [], days: [], attendance: [] })))
    .mockResolvedValueOnce(new Response('[]')).mockResolvedValueOnce(new Response('[]'))
    .mockResolvedValueOnce(new Response('[]')).mockResolvedValueOnce(new Response(JSON.stringify(roster)));
  vi.stubGlobal('fetch', fetch);
  await readCalendar('2026-09'); await calendarCandidates('2026-09'); await calendarStores();
  await saveCalendarDays('2026-09', []);
  expect(await confirmCalendarAgent('2026-09', 'AG/1', { home_site_code: 'S1', active: true, expected_revision: 0 })).toEqual(roster);
  expect(fetch.mock.calls.map(call => call[0])).toEqual(['/api/grile/calendar/2026-09', '/api/grile/calendar/2026-09/candidates', '/api/stores', '/api/grile/calendar/2026-09/days', '/api/grile/calendar/2026-09/roster/AG%2F1']);
  expect(fetch.mock.calls[4]?.[1]).toMatchObject({ method: 'PUT' });
});
it('saves store hours through the API and downloads the chosen revision', async () => {
  const { saveStoreHours, downloadAttendance } = await import('./grileCalendar');
  const hours = { site_code: 'S1', opens: '09:00', closes: '22:00', break_minutes: 60, revision: 2 };
  const fetch = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify(hours)))
    .mockResolvedValueOnce(new Response('zip', { headers: { 'Content-Type': 'application/zip' } }));
  vi.stubGlobal('fetch', fetch);
  const create = vi.fn().mockReturnValue('blob:synthetic');
  vi.stubGlobal('URL', class extends URL { static createObjectURL = create; static revokeObjectURL = vi.fn(); });
  const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
  try {
    expect(await saveStoreHours('2026-09', 'S1', { opens: '09:00', closes: '22:00', break_minutes: 60, expected_revision: 1 })).toEqual(hours);
    await downloadAttendance('2026-09', 'a'.repeat(64));
    expect(fetch.mock.calls[0]?.[0]).toBe('/api/grile/calendar/2026-09/store-hours/S1');
    expect(fetch.mock.calls[1]?.[0]).toContain('attendance.zip?expected_revision=' + 'a'.repeat(64));
    expect(create).toHaveBeenCalledOnce();
  } finally { click.mockRestore(); }
});
