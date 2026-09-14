// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, it, vi } from 'vitest';
import { CalendarDayEditor } from './CalendarDayEditor';
import type { CalendarData } from '../../api/grileCalendar';

afterEach(cleanup);
const store = { site_code: 'S1', locatie: 'Store 1', firma: 'Firm', regional: 'R', asm: '' };
const other = { ...store, site_code: 'S2' };
const data: CalendarData = {
  attendance_by_store: {}, attendance_days: [], closures: [], store_hours: [], projection_revision: '', month: '2026-09',
  attendance: [], roster: [
    { regional: null, display_name: null, transfers: [], identity_status: 'unavailable', month: '2026-09', agent_code: 'A', home_site_code: 'S1', active: true, revision: 1 },
    { regional: null, display_name: null, transfers: [], identity_status: 'unavailable', month: '2026-09', agent_code: 'B', home_site_code: 'S2', active: true, revision: 1 },
  ],
  days: [{ agent_code: 'A', work_date: '2026-09-01', site_code: 'S1', status: 'work', supplemental: false, revision: 3 }],
};
const props = { data, store, stores: [store, other], date: '2026-09-01', busy: false, writable: true };

it('saves an explicit agent assignment with the opened revision', async () => {
  const onSave = vi.fn();
  render(<CalendarDayEditor {...props} data={{ ...data, days: [] }} onSave={onSave} />);
  await userEvent.selectOptions(screen.getByLabelText('Agent pentru zi'), 'A');
  await userEvent.click(screen.getByRole('button', { name: 'Salvează ziua' }));
  expect(onSave).toHaveBeenCalledWith([{ agent_code: 'A', site_code: 'S1', work_date: '2026-09-01', status: 'work', supplemental: false, expected_revision: 0 }]);
});

it('closes an unassigned day through the closure callback', async () => {
  const onCloseDay = vi.fn();
  render(<CalendarDayEditor {...props} data={{ ...data, days: [] }} onSave={vi.fn()} onCloseDay={onCloseDay} />);
  await userEvent.click(screen.getByRole('button', { name: 'Închide ziua' }));
  expect(onCloseDay).toHaveBeenCalledWith({ work_date: '2026-09-01', site_code: 'S1', closed: true, expected_revision: 0 }, undefined);
});

it('uses the original revision and prevents conflicting assignments', async () => {
  const onSave = vi.fn();
  render(<CalendarDayEditor {...props} data={{ ...data, days: [...data.days, { ...data.days[0]!, agent_code: 'B', site_code: 'S2' }] }} onSave={onSave} />);
  await userEvent.selectOptions(screen.getByLabelText('Agent pentru zi'), 'B');
  expect(screen.getByRole('button', { name: 'Salvează ziua' })).toBeDisabled();
  expect(screen.getByRole('alert')).toHaveTextContent('S2');
});

it('keeps read-only users from saving', () => {
  render(<CalendarDayEditor {...props} writable={false} onSave={vi.fn()} />);
  expect(screen.getByRole('button', { name: 'Salvează ziua' })).toBeDisabled();
});

it('automatically marks an external agent as a paid supplement', async () => {
  const onSave = vi.fn();
  render(<CalendarDayEditor {...props} data={{ ...data, days: [] }} onSave={onSave} />);
  await userEvent.selectOptions(screen.getByLabelText('Agent pentru zi'), 'B');
  await userEvent.click(screen.getByRole('button', { name: 'Salvează ziua' }));
  expect(onSave).toHaveBeenCalledWith([{ agent_code: 'B', site_code: 'S1', work_date: '2026-09-01', status: 'work', supplemental: true, expected_revision: 0 }]);
});

it('submits TL absence status instead of a physical work assignment', async () => {
  const onSave = vi.fn();
  const leader = { ...data.roster[0]!, agent_code: 'LEADER', home_site_code: 'TL', regional: 'R' };
  const tl = { site_code: 'TL', locatie: 'Team Leaders', firma: '', regional: 'R', asm: '', virtualBase: true };
  render(<CalendarDayEditor {...props} store={tl} stores={[tl, store]} data={{ ...data, roster: [leader], days: [] }} onSave={onSave} />);
  await userEvent.selectOptions(screen.getByLabelText('Agent pentru zi'), 'LEADER');
  await userEvent.selectOptions(screen.getByLabelText('Tip absență TL'), 'off');
  await userEvent.click(screen.getByRole('button', { name: 'Salvează ziua' }));
  expect(onSave).toHaveBeenCalledWith([{ agent_code: 'LEADER', site_code: 'TL', work_date: '2026-09-01', status: 'off', supplemental: false, expected_revision: 0 }]);
});
it('limits virtual TL roster entries to the confirmed region', () => {
  const leader = { ...data.roster[0]!, agent_code: 'LEADER', home_site_code: 'TL', regional: 'R' };
  const otherLeader = { ...leader, agent_code: 'OTHER-TL', regional: 'OTHER' };
  render(<CalendarDayEditor {...props} data={{ ...data, roster: [leader, otherLeader], days: [] }} onSave={vi.fn()} />);
  expect(screen.getByRole('option', { name: /LEADER/ })).toBeInTheDocument();
  expect(screen.queryByRole('option', { name: /OTHER-TL/ })).not.toBeInTheDocument();
});
