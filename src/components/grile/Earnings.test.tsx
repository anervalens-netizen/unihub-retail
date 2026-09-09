// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';

const api = vi.hoisted(() => ({ readEarnings: vi.fn(), downloadEarnings: vi.fn() }));
vi.mock('../../api/grileCalendar', () => api);
import { Earnings } from './Earnings';

function response() {
  return { projection_revision: 'earnings-revision', calendar_revision: 'revision-1', cutoff: '2026-09-03', selling_days: { A: 3 }, unassigned_sales: [], agents: [{
    agent_code: 'AG1', home_site_code: 'A', home_work_days: 2, home_target: '2000', home_sales: '1600', home_commission: '48', away_commission: '24', supplemental_pay: '150', known_earnings: '222', issues: [], days: [{ work_date: '2026-09-03', site_code: 'B', sales: '790', daily_target: '1000', commission: '24', supplemental: true, supplemental_pay: '150', away: true, issue: null }],
  }] };
}
beforeEach(() => { vi.resetAllMocks(); api.readEarnings.mockResolvedValue(response()); });
afterEach(cleanup);
function mount(revision = 'revision-1') {
  return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><Earnings month="2026-09" site="A" calendarRevision={revision} /></QueryClientProvider>);
}
it('shows home earnings including the other store and the provisional salary boundary', async () => {
  mount();
  expect(await screen.findByText('222 lei')).toBeInTheDocument();
  expect(screen.getByText(/3 zile de funcționare/)).toBeInTheDocument();
  expect(screen.getByText(/nu reprezintă salariul oficial/)).toBeInTheDocument();
  await userEvent.click(screen.getByText('Detalii pe zile și locații'));
  expect(screen.getByRole('table')).toHaveTextContent('B');
  expect(screen.getByRole('table')).toHaveTextContent('790 lei');
});
it('includes the TL and unassigned sales in the physical store total', async () => {
  const data = response();
  const day = data.agents[0]!.days[0]!;
  api.readEarnings.mockResolvedValue({ ...data, agents: [{ ...data.agents[0], agent_code: 'LEADER', home_site_code: 'TL', days: [{ ...day, site_code: 'A', sales: '790.25' }] }], unassigned_sales: [{ site_code: 'A', sale_date: '2026-09-02', sales: '10.75' }] });
  mount();
  expect(await screen.findByText('801 lei')).toBeInTheDocument();
  expect(screen.getByText(/LEADER · 2026-09-03/)).toBeInTheDocument();
  expect(screen.queryByText('222 lei')).not.toBeInTheDocument();
});
it('rejects a different calendar revision without showing stale money', async () => {
  mount('revision-2');
  expect(await screen.findByRole('alert')).toHaveTextContent('Calendarul s-a schimbat');
  expect(screen.queryByText('222 lei')).not.toBeInTheDocument();
});
it('shows missing input instead of zero earnings', async () => {
  const data = response();
  api.readEarnings.mockResolvedValue({ ...data, agents: [{ ...data.agents[0], home_sales: null, home_commission: null, known_earnings: null, issues: ['missing_sales'] }] });
  mount();
  expect(await screen.findByRole('alert')).toHaveTextContent('nu sunt considerate zero');
  expect(screen.getAllByText('Indisponibil')).toHaveLength(3);
});
it('retries a failed read without writing business data', async () => {
  api.readEarnings.mockRejectedValueOnce(new Error('offline'));
  mount();
  await userEvent.click(await screen.findByRole('button', { name: 'Reîncarcă' }));
  expect(await screen.findByText('222 lei')).toBeInTheDocument();
});
it('reports unassigned store sales and agents from another home stay outside this grid', async () => {
  const data = response();
  api.readEarnings.mockResolvedValue({ ...data, agents: [{ ...data.agents[0], home_site_code: 'B' }], unassigned_sales: [{ site_code: 'A', sale_date: '2026-09-04', sales: '40' }] });
  mount();
  expect(await screen.findByRole('alert')).toHaveTextContent('fără persoană alocată');
  expect(screen.queryByText('222 lei')).not.toBeInTheDocument();
});
it('shows confirmed names alongside stable codes and explains identity conflicts', async () => {
  const data = response();
  api.readEarnings.mockResolvedValue({ ...data, agents: [
    { ...data.agents[0], display_name: 'Synthetic Name', identity_status: 'confirmed' },
    { ...data.agents[0], agent_code: 'AG2', identity_status: 'conflicting' },
  ] });
  mount();
  expect(await screen.findByRole('heading', { name: 'Synthetic Name · AG1' })).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: 'AG2' })).toBeInTheDocument();
  expect(screen.getByText(/identități salariale contradictorii/)).toBeInTheDocument();
});

it('downloads the earnings revision and offers reload on a stale export', async () => {
  api.downloadEarnings.mockRejectedValueOnce(new Error('conflict'));
  mount();
  await userEvent.click(await screen.findByRole('button', { name: 'Descarcă câștiguri și pontaje ZIP' }));
  expect(api.downloadEarnings).toHaveBeenCalledWith('2026-09', 'earnings-revision');
  await userEvent.click(await screen.findByRole('button', { name: 'Reîncarcă câștigurile' }));
  expect(api.readEarnings).toHaveBeenCalledTimes(2);
});
