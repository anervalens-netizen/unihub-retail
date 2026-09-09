// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, it, vi } from 'vitest';
import { CalendarDayEditor } from './CalendarDayEditor';
import type { CalendarData } from '../../api/grileCalendar';
afterEach(cleanup);
const store = { site_code: 'S1', locatie: 'Store 1', firma: 'Firm', regional: 'R', asm: '' };
const other = { ...store, site_code: 'S2' };
const data: CalendarData = { attendance_by_store: {}, attendance_days: [], store_hours: [], projection_revision: '', month: '2026-09', attendance: [], roster: [
  { regional: null, display_name: null, identity_status: 'unavailable', month: '2026-09', agent_code: 'A', home_site_code: 'S1', active: true, revision: 1 },
  { regional: null, display_name: null, identity_status: 'unavailable', month: '2026-09', agent_code: 'B', home_site_code: 'S2', active: true, revision: 1 },
], days: [{ agent_code: 'A', work_date: '2026-09-01', site_code: 'S1', status: 'work', supplemental: false, revision: 3 }] };
const props = { data, store, stores: [store, other], date: '2026-09-01', busy: false, writable: true };
it('records a TL absence at the virtual base without offering a work day', async () => {
  const onSave = vi.fn();
  const leader = { ...data.roster[0]!, agent_code: 'LEADER', home_site_code: 'TL', regional: 'R' };
  render(<CalendarDayEditor {...props} store={{ ...store, site_code: 'TL', regional: '', virtualBase: true }} data={{ ...data, roster: [leader], days: [] }} onSave={onSave} />);
  await userEvent.selectOptions(screen.getByLabelText('Agent pentru zi'), 'LEADER');
  expect(screen.queryByRole('option', { name: 'Lucrează' })).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: 'Salvează ziua' }));
  expect(onSave).toHaveBeenCalledWith([{ agent_code: 'LEADER', site_code: 'TL', work_date: '2026-09-01', status: 'leave', supplemental: false, expected_revision: 0 }]);
});
it('offers a virtual TL only within the confirmed region and permits normally paid work', async () => {
  const onSave = vi.fn();
  const leader = { ...data.roster[0]!, agent_code: 'LEADER', home_site_code: 'TL', regional: 'R' };
  render(<CalendarDayEditor {...props} data={{ ...data, roster: [...data.roster, leader, { ...leader, agent_code: 'OTHER-TL', regional: 'OTHER' }] }} onSave={onSave} />);
  expect(screen.queryByRole('option', { name: /OTHER-TL/ })).not.toBeInTheDocument();
  await userEvent.selectOptions(screen.getByLabelText('Agent pentru zi'), 'LEADER');
  expect(screen.getByRole('checkbox')).not.toBeChecked();
  expect(screen.getByRole('checkbox')).toBeEnabled();
  await userEvent.click(screen.getByRole('button', { name: 'Salvează ziua' }));
  expect(onSave.mock.calls[0]![0][1]).toMatchObject({ agent_code: 'LEADER', site_code: 'S1', supplemental: false });
});
it('uses the original edit revision even if a background read changes', async () => {
  const onSave = vi.fn();
  const { rerender } = render(<CalendarDayEditor {...props} onSave={onSave} />);
  rerender(<CalendarDayEditor {...props} data={{ ...data, days: data.days.map(d => ({ ...d, revision: 4 })) }} onSave={onSave} />);
  await userEvent.selectOptions(screen.getByLabelText('Tip zi'), 'leave');
  await userEvent.click(screen.getByRole('button', { name: 'Salvează ziua' }));
  expect(onSave.mock.calls[0]![0][0]).toMatchObject({ status: 'leave', expected_revision: 3 });
});
it('allows a normal shift swap at another home store', async () => {
  const onSave = vi.fn();
  render(<CalendarDayEditor {...props} onSave={onSave} />);
  await userEvent.selectOptions(screen.getByLabelText('Agent pentru zi'), 'B');
  expect(screen.getByRole('checkbox')).not.toBeChecked();
  await userEvent.click(screen.getByRole('button', { name: 'Salvează ziua' }));
  expect(onSave.mock.calls[0]![0][1]).toMatchObject({ agent_code: 'B', supplemental: false });
});
it('does not move a day already assigned at another location', async () => {
  render(<CalendarDayEditor {...props} data={{ ...data, days: [...data.days, { ...data.days[0]!, agent_code: 'B', site_code: 'S2' }] }} onSave={vi.fn()} />);
  await userEvent.selectOptions(screen.getByLabelText('Agent pentru zi'), 'B');
  expect(screen.getByRole('button', { name: 'Salvează ziua' })).toBeDisabled();
  expect(screen.getByRole('alert')).toHaveTextContent('S2');
});
it('does not allow read-only users to save', () => {
  render(<CalendarDayEditor {...props} writable={false} onSave={vi.fn()} />);
  expect(screen.getByRole('button', { name: 'Salvează ziua' })).toBeDisabled();
});
it('cancels supplemental work at the assigned store while preserving its revision', async () => {
  const onSave = vi.fn();
  render(<CalendarDayEditor {...props} data={{ ...data, days: [{ ...data.days[0]!, agent_code: 'B', supplemental: true }] }} onSave={onSave} />);
  await userEvent.selectOptions(screen.getByLabelText('Tip zi'), 'cancelled');
  await userEvent.click(screen.getByRole('button', { name: 'Salvează ziua' }));
  expect(onSave).toHaveBeenCalledWith([{ agent_code: 'B', work_date: '2026-09-01', site_code: 'S1', status: 'cancelled', supplemental: false, expected_revision: 3 }]);
});
it('allows cleanup of an unavailable-store supplement even when the home is absent', async () => {
  const onSave = vi.fn();
  render(<CalendarDayEditor {...props} store={{ ...store, regional: '', cleanupOnly: true }} stores={[]} data={{ ...data, days: [{ ...data.days[0]!, agent_code: 'B', supplemental: true }] }} onSave={onSave} />);
  await userEvent.click(screen.getByRole('button', { name: 'Salvează ziua' }));
  expect(onSave).toHaveBeenCalledWith([expect.objectContaining({ agent_code: 'B', site_code: 'S1', status: 'cancelled', expected_revision: 3 })]);
});
it('does not inherit another occupants supplemental classification', async () => {
  const onSave = vi.fn();
  const homeData = { ...data, roster: data.roster.map(r => ({ ...r, home_site_code: 'S1' })), days: [{ ...data.days[0]!, supplemental: true }] };
  render(<CalendarDayEditor {...props} data={homeData} onSave={onSave} />);
  expect(screen.getByRole('checkbox')).toBeChecked();
  await userEvent.selectOptions(screen.getByLabelText('Agent pentru zi'), 'B');
  expect(screen.getByRole('checkbox')).not.toBeChecked();
  await userEvent.click(screen.getByRole('button', { name: 'Salvează ziua' }));
  expect(onSave.mock.calls[0]![0][1]).toMatchObject({ agent_code: 'B', supplemental: false });
});

it('lets a manager explicitly mark away work as a paid supplement', async () => {
  const onSave = vi.fn();
  render(<CalendarDayEditor {...props} onSave={onSave} />);
  await userEvent.selectOptions(screen.getByLabelText('Agent pentru zi'), 'B');
  await userEvent.click(screen.getByRole('checkbox'));
  await userEvent.click(screen.getByRole('button', { name: 'Salvează ziua' }));
  expect(onSave.mock.calls[0]![0][1]).toMatchObject({ agent_code: 'B', supplemental: true });
});
