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
