// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { ApiError } from '../../api/client';
const api = vi.hoisted(() => ({ readCalendar: vi.fn(), calendarStores: vi.fn(), calendarCandidates: vi.fn(), confirmCalendarAgent: vi.fn(), saveCalendarDays: vi.fn() }));
const auth = vi.hoisted(() => ({ profile: { groups: ['unihub-manager'] } }));
vi.mock('../../api/grileCalendar', () => api);
vi.mock('../../auth/AuthContext', () => ({ useAuth: () => ({ user: auth }) }));
import { NativeCalendar } from './NativeCalendar';
const store = { site_code: 'S1', locatie: 'Magazin Alpha', regional: 'Manager R', firma: 'Firm', asm: '' };
const roster = [{ month: '2026-09', agent_code: 'AG1', home_site_code: 'S1', active: true, revision: 1 }];
const day = { agent_code: 'AG1', work_date: '2026-09-01', site_code: 'S1', status: 'work', supplemental: false, revision: 1 };
beforeEach(() => {
  vi.resetAllMocks();
  auth.profile.groups = ['unihub-manager'];
  HTMLDialogElement.prototype.showModal = function () { this.open = true; };
  HTMLDialogElement.prototype.close = function () { this.open = false; };
  api.calendarStores.mockResolvedValue([store]);
  api.calendarCandidates.mockResolvedValue([{ agent_code: 'AG2', site_codes: ['S1'], needs_active_confirmation: true }]);
  api.readCalendar.mockResolvedValue({ month: '2026-09', roster, days: [day], attendance: [] });
});
afterEach(cleanup);
function mount() { return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}><NativeCalendar initialMonth="2026-09" /></QueryClientProvider>); }
async function openStore() { await userEvent.click(await screen.findByRole('button', { name: /Magazin Alpha/ })); }
it('opens grouped store, shows attendance, and reopens calendar', async () => {
  mount(); await openStore();
  expect(screen.getByRole('dialog')).toHaveAccessibleName('Magazin Alpha');
  await userEvent.click(screen.getByRole('button', { name: 'Pontaj' }));
  expect(screen.getByRole('table')).toHaveTextContent('AG1');
  await userEvent.click(screen.getByLabelText('Închide magazinul'));
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  await openStore();
  expect(screen.getByRole('button', { name: 'Editează 2026-09-01' })).toBeInTheDocument();
});
it('saves leave and reloads the shared calendar', async () => {
  mount(); await openStore();
  await userEvent.click(screen.getByRole('button', { name: 'Editează 2026-09-01' }));
  await userEvent.selectOptions(screen.getByLabelText('Tip zi'), 'leave');
  api.saveCalendarDays.mockResolvedValue([]);
  api.readCalendar.mockResolvedValue({ month: '2026-09', roster, days: [{ ...day, status: 'leave', revision: 2 }], attendance: [] });
  await userEvent.click(screen.getByRole('button', { name: 'Salvează ziua' }));
  await waitFor(() => expect(api.saveCalendarDays).toHaveBeenCalledWith('2026-09', [expect.objectContaining({ agent_code: 'AG1', status: 'leave', expected_revision: 1 })]));
  await waitFor(() => expect(screen.queryByRole('button', { name: 'Salvează ziua' })).not.toBeInTheDocument());
  expect(screen.getByRole('button', { name: 'Editează 2026-09-01' })).toHaveTextContent('Concediu');
});
it('requires explicit reload after a conflict', async () => {
  mount(); await openStore();
  await userEvent.click(screen.getByRole('button', { name: 'Editează 2026-09-01' }));
  api.saveCalendarDays.mockRejectedValue(new ApiError(409, 'stale', null));
  await userEvent.click(screen.getByRole('button', { name: 'Salvează ziua' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Programul s-a schimbat');
  expect(screen.getByRole('button', { name: 'Salvează ziua' })).toBeDisabled();
  await userEvent.click(screen.getByRole('button', { name: 'Reîncarcă programul' }));
  await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument());
});
it('confirms a candidate explicitly at the selected home store', async () => {
  mount(); await openStore();
  await userEvent.click(screen.getByText('Confirmă agenții și magazinul de bază'));
  await userEvent.selectOptions(screen.getByLabelText('Cod agent pentru confirmare'), 'AG2');
  api.confirmCalendarAgent.mockResolvedValue({});
  await userEvent.click(screen.getByRole('button', { name: 'Confirmă în Magazin Alpha' }));
  await waitFor(() => expect(api.confirmCalendarAgent).toHaveBeenCalledWith('2026-09', 'AG2', { home_site_code: 'S1', active: true, expected_revision: 0 }));
});
it('blocks agents and keeps HR read-only', async () => {
  auth.profile.groups = ['unihub-agent'];
  const view = mount();
  expect(screen.getByText(/echipei de management/)).toBeInTheDocument();
  expect(api.readCalendar).not.toHaveBeenCalled();
  view.unmount(); auth.profile.groups = ['unihub-hr']; mount(); await openStore();
  expect(screen.getByText('Mod consultare.')).toBeInTheDocument();
  expect(api.calendarCandidates).not.toHaveBeenCalled();
});
it('does not turn a failed month load into an empty editable schedule', async () => {
  api.readCalendar.mockRejectedValue(new Error('offline'));
  mount();
  expect(await screen.findByRole('alert')).toHaveTextContent('nu poate fi încărcat');
  expect(screen.queryByRole('button', { name: /Magazin Alpha/ })).not.toBeInTheDocument();
});
it('corrects an existing home store using the selected roster revision', async () => {
  api.readCalendar.mockResolvedValue({ month: '2026-09', roster: [{ ...roster[0], home_site_code: 'S2', revision: 4 }], days: [], attendance: [] });
  mount(); await openStore();
  await userEvent.click(screen.getByText('Confirmă agenții și magazinul de bază'));
  await userEvent.selectOptions(screen.getByLabelText('Cod agent pentru confirmare'), 'AG1');
  api.confirmCalendarAgent.mockResolvedValue({});
  await userEvent.click(screen.getByRole('button', { name: 'Confirmă în Magazin Alpha' }));
  await waitFor(() => expect(api.confirmCalendarAgent).toHaveBeenCalledWith('2026-09', 'AG1', { home_site_code: 'S1', active: true, expected_revision: 4 }));
});
it('deactivates and reactivates confirmed agents through revision-fenced updates', async () => {
  api.readCalendar.mockResolvedValue({ month: '2026-09', roster, days: [], attendance: [] });
  mount(); await openStore();
  await userEvent.click(screen.getByText('Confirmă agenții și magazinul de bază'));
  await userEvent.selectOptions(screen.getByLabelText('Cod agent pentru confirmare'), 'AG1');
  await userEvent.click(screen.getByLabelText('Activ în această lună'));
  api.confirmCalendarAgent.mockResolvedValue({});
  api.readCalendar.mockResolvedValue({ month: '2026-09', roster: [{ ...roster[0], active: false, revision: 2 }], days: [], attendance: [] });
  await userEvent.click(screen.getByRole('button', { name: 'Confirmă în Magazin Alpha' }));
  await waitFor(() => expect(api.confirmCalendarAgent).toHaveBeenCalledWith('2026-09', 'AG1', { home_site_code: 'S1', active: false, expected_revision: 1 }));
  await waitFor(() => expect(screen.getByLabelText('Cod agent pentru confirmare')).toHaveValue(''));
  await userEvent.selectOptions(screen.getByLabelText('Cod agent pentru confirmare'), 'AG1');
  await userEvent.click(screen.getByLabelText('Activ în această lună'));
  await userEvent.click(screen.getByRole('button', { name: 'Confirmă în Magazin Alpha' }));
  await waitFor(() => expect(api.confirmCalendarAgent).toHaveBeenLastCalledWith('2026-09', 'AG1', { home_site_code: 'S1', active: true, expected_revision: 2 }));
});
it('closes the old day snapshot after a home-store correction', async () => {
  api.calendarStores.mockResolvedValue([store, { ...store, site_code: 'S2', locatie: 'Magazin Beta' }]);
  api.readCalendar.mockResolvedValue({ month: '2026-09', roster: [{ ...roster[0], home_site_code: 'S2' }], days: [], attendance: [] });
  mount(); await openStore();
  await userEvent.click(screen.getByRole('button', { name: 'Editează 2026-09-01' }));
  await userEvent.selectOptions(screen.getByLabelText('Agent pentru zi'), 'AG1');
  expect(screen.getByLabelText('Suplimentar')).toBeChecked();
  await userEvent.click(screen.getByText('Confirmă agenții și magazinul de bază'));
  await userEvent.selectOptions(screen.getByLabelText('Cod agent pentru confirmare'), 'AG1');
  api.readCalendar.mockResolvedValue({ month: '2026-09', roster: [{ ...roster[0], revision: 2 }], days: [], attendance: [] });
  api.confirmCalendarAgent.mockResolvedValue({});
  await userEvent.click(screen.getByRole('button', { name: 'Confirmă în Magazin Alpha' }));
  await waitFor(() => expect(screen.queryByLabelText('Agent pentru zi')).not.toBeInTheDocument());
  await waitFor(() => expect(screen.getByLabelText('Cod agent pentru confirmare')).toHaveValue(''));
  await userEvent.click(screen.getByRole('button', { name: 'Editează 2026-09-01' }));
  await userEvent.selectOptions(screen.getByLabelText('Agent pentru zi'), 'AG1');
  expect(screen.getByLabelText('Suplimentar')).not.toBeChecked();
});
it('keeps unavailable scheduled stores accessible only for cancellation', async () => {
  api.calendarStores.mockResolvedValue([]);
  mount();
  await userEvent.click(await screen.findByRole('button', { name: /S1 · doar corectări/ }));
  expect(screen.getByText(/Magazin indisponibil pentru programări noi/)).toBeInTheDocument();
  expect(screen.queryByText('Confirmă agenții și magazinul de bază')).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Editează 2026-09-02' })).toBeDisabled();
  await userEvent.click(screen.getByRole('button', { name: 'Editează 2026-09-01' }));
  expect(screen.getByLabelText('Tip zi')).toHaveValue('cancelled');
  expect(screen.queryByRole('option', { name: 'Lucrează' })).not.toBeInTheDocument();
  api.saveCalendarDays.mockResolvedValue([]);
  await userEvent.click(screen.getByRole('button', { name: 'Salvează ziua' }));
  await waitFor(() => expect(api.saveCalendarDays).toHaveBeenCalledWith('2026-09', [{ agent_code: 'AG1', work_date: '2026-09-01', site_code: 'S1', status: 'cancelled', supplemental: false, expected_revision: 1 }]));
});
it('keeps date switching locked until a slow day save completes', async () => {
  let finish!: (value: unknown[]) => void;
  api.saveCalendarDays.mockImplementation(() => new Promise(resolve => { finish = resolve; }));
  mount(); await openStore();
  await userEvent.click(screen.getByRole('button', { name: 'Editează 2026-09-01' }));
  await userEvent.click(screen.getByRole('button', { name: 'Salvează ziua' }));
  const otherDate = screen.getByRole('button', { name: 'Editează 2026-09-02' });
  expect(otherDate).toBeDisabled();
  await userEvent.click(otherDate);
  expect(screen.getByText('Program pentru 2026-09-01')).toBeInTheDocument();
  expect(api.saveCalendarDays).toHaveBeenCalledTimes(1);
  expect(screen.queryByText('Confirmă agenții și magazinul de bază')).not.toBeInTheDocument();
  finish([]);
  await waitFor(() => expect(otherDate).not.toBeDisabled());
  await userEvent.click(otherDate);
  expect(screen.getByText('Program pentru 2026-09-02')).toBeInTheDocument();
});
