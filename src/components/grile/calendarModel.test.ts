import { describe, expect, it } from 'vitest';
import { dayChanges, monthDays } from './calendarModel';
import type { CalendarData } from '../../api/grileCalendar';

const data: CalendarData = { month: '2026-09', roster: [], attendance: [], days: [
  { agent_code: 'A', work_date: '2026-09-01', site_code: 'S1', status: 'work', supplemental: false, revision: 3 },
  { agent_code: 'B', work_date: '2026-09-01', site_code: 'S1', status: 'cancelled', supplemental: false, revision: 7 },
] };
describe('calendar changes', () => {
  it('replaces the occupant atomically and retains cancelled-person revision', () => {
    expect(dayChanges(data, { agent_code: 'B', work_date: '2026-09-01', site_code: 'S1', status: 'work', supplemental: true })).toEqual([
      { agent_code: 'A', work_date: '2026-09-01', site_code: 'S1', status: 'cancelled', supplemental: false, expected_revision: 3 },
      { agent_code: 'B', work_date: '2026-09-01', site_code: 'S1', status: 'work', supplemental: true, expected_revision: 7 },
    ]);
  });
  it('adding leave does not cancel the agent covering the store', () => {
    expect(dayChanges(data, { agent_code: 'B', work_date: '2026-09-01', site_code: 'S1', status: 'leave', supplemental: false })).toHaveLength(1);
  });
  it('creates an absent agent/day with revision zero', () => {
    expect(dayChanges(data, { agent_code: 'C', work_date: '2026-09-02', site_code: 'S1', status: 'off' })[0]!.expected_revision).toBe(0);
  });
  it('aligns Monday weeks and leap years without local timezone conversions', () => {
    expect(monthDays('2026-09')).toMatchObject({ offset: 1 });
    expect(monthDays('2028-02').dates).toHaveLength(29);
    expect(monthDays('2026-02').dates).toHaveLength(28);
  });
});
