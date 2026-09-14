// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { CompensationEditor } from './CompensationEditor';
const api = vi.hoisted(() => ({ saveEpay: vi.fn().mockResolvedValue({}) }));
vi.mock('../../api/grileCalendar', () => api);
afterEach(() => { cleanup(); vi.clearAllMocks(); });
const value = { month: '2026-09', agent_code: 'AG1', revision: 4, salary_base: 2600, vouchers: 480, sim_quantity: 7, epay_under_50: null, epay_over_50: null, incentive: 100, adjustment: 25 };
function mount(writable = true) { render(<QueryClientProvider client={new QueryClient({ defaultOptions: { mutations: { retry: false } } })}><CompensationEditor value={value} writable={writable} /></QueryClientProvider>); }
it('defaults to zero, offers only zero through fifteen and never writes automatic compensation', async () => {
  mount();
  expect(screen.getByLabelText('E-pay <50 lei cantitate')).toHaveValue('0');
  await userEvent.selectOptions(screen.getByLabelText('E-pay <50 lei cantitate'), '3');
  expect(screen.queryByRole('spinbutton')).not.toBeInTheDocument();
  expect(screen.getAllByRole('option')).toHaveLength(32);
  await userEvent.selectOptions(screen.getByLabelText('E-pay ≥50 lei cantitate'), '15');
  await userEvent.click(screen.getByRole('button', { name: 'Salvează E-pay' }));
  expect(api.saveEpay).toHaveBeenCalledWith('2026-09', 'AG1', { epay_under_50: 3, epay_over_50: 15, expected_revision: 4 });
});
it('keeps read-only quantities visible and disabled', () => {
  mount(false);
  expect(screen.getByLabelText('E-pay <50 lei cantitate')).toBeDisabled();
  expect(screen.queryByRole('button')).not.toBeInTheDocument();
});
