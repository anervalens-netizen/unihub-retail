// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, it, vi } from 'vitest';
import type { CalendarData } from '../../api/grileCalendar';
const api = vi.hoisted(() => ({ confirmCalendarAgent: vi.fn() }));
vi.mock('../../api/grileCalendar', () => api);
import { TeamLeaderRoster } from './TeamLeaderRoster';
afterEach(() => { cleanup(); vi.resetAllMocks(); });
const data: CalendarData = { month: '2026-09', roster: [], days: [], attendance: [], attendance_days: [], attendance_by_store: {}, store_hours: [], projection_revision: 'r1' };
function mount(calendar = data, writable = true) {
  return render(<QueryClientProvider client={new QueryClient()}><TeamLeaderRoster month="2026-09" data={calendar} stores={[{ site_code: 'A', locatie: 'A', firma: 'F', regional: 'R1', asm: '' }]} writable={writable} /></QueryClientProvider>);
}
it('creates the first TL without a POS candidate or fictitious store', async () => {
  mount();
  await userEvent.type(screen.getByLabelText('Cod Team Leader'), 'LEADER');
  await userEvent.selectOptions(screen.getByLabelText('Manager regional TL'), 'R1');
  await userEvent.click(screen.getByRole('button', { name: 'Salvează Team Leader' }));
  await waitFor(() => expect(api.confirmCalendarAgent).toHaveBeenCalledWith('2026-09', 'LEADER', { home_site_code: 'TL', regional: 'R1', active: true, expected_revision: 0 }));
});
it('deactivates an existing TL using the selected revision', async () => {
  mount({ ...data, roster: [{ month: '2026-09', agent_code: 'LEADER', display_name: null, identity_status: 'unavailable', home_site_code: 'TL', regional: 'R1', active: true, revision: 3 }] });
  await userEvent.selectOptions(screen.getByLabelText('Team Leader confirmat'), 'LEADER');
  await userEvent.click(screen.getByRole('checkbox'));
  await userEvent.click(screen.getByRole('button', { name: 'Salvează Team Leader' }));
  await waitFor(() => expect(api.confirmCalendarAgent).toHaveBeenCalledWith('2026-09', 'LEADER', expect.objectContaining({ active: false, expected_revision: 3 })));
});
it('keeps management read-only without business-write authority', () => {
  mount(data, false);
  expect(screen.queryByRole('button', { name: 'Salvează Team Leader' })).not.toBeInTheDocument();
});
it('retains a retired region while deactivating its existing leader', async () => {
  mount({ ...data, roster: [{ month: '2026-09', agent_code: 'LEADER', display_name: null, identity_status: 'unavailable', home_site_code: 'TL', regional: 'RETIRED', active: true, revision: 3 }] });
  await userEvent.selectOptions(screen.getByLabelText('Team Leader confirmat'), 'LEADER');
  expect(screen.getByLabelText('Manager regional TL')).toHaveValue('RETIRED');
  await userEvent.click(screen.getByRole('checkbox'));
  await userEvent.click(screen.getByRole('button', { name: 'Salvează Team Leader' }));
  await waitFor(() => expect(api.confirmCalendarAgent).toHaveBeenCalledWith('2026-09', 'LEADER', expect.objectContaining({ active: false, regional: 'RETIRED', expected_revision: 3 })));
});
