// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AgentTargetEditor } from './AgentTargetEditor';
import type { readEarnings } from '../../api/grileCalendar';
type Agent = Awaited<ReturnType<typeof readEarnings>>['agents'][number];
const api = vi.hoisted(() => ({ saveAgentTarget: vi.fn() }));
vi.mock('../../api/grileCalendar', () => api);
vi.mock('../../api/client', () => ({ getApiErrorMessage: vi.fn((_error, fallback) => fallback) }));
afterEach(() => { cleanup(); vi.clearAllMocks(); });
const agent = { agent_code: 'AG1', display_name: 'Agent One', home_site_code: 'S1', home_sales: 12000, home_target: 10000, performance: { target: 10000 }, target_setting: { agent_code: 'AG1', month: '2026-09', mode: 'automatic', automatic_target: 10000, manual_target: null, revision: 7 } } as unknown as Agent;
function mount(overrides: Partial<{ writable: boolean; value: Agent }> = {}) {
  const queryClient = new QueryClient({ defaultOptions: { mutations: { retry: false }, queries: { retry: false } } });
  render(<QueryClientProvider client={queryClient}><AgentTargetEditor agent={overrides.value ?? agent} writable={overrides.writable ?? true} /></QueryClientProvider>);
  return queryClient;
}
describe('AgentTargetEditor', () => {
  it('opens the editor and saves a positive manual target with month and revision', async () => {
    api.saveAgentTarget.mockResolvedValueOnce({}); mount();
    await userEvent.click(screen.getByRole('button', { name: 'Editează target AG1' }));
    expect(screen.getByRole('form', { name: 'Target agent AG1' })).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText('Mod calcul target'), 'manual');
    await userEvent.clear(screen.getByLabelText('Target lunar în lei'));
    await userEvent.type(screen.getByLabelText('Target lunar în lei'), '12500');
    await userEvent.click(screen.getByRole('button', { name: 'Salvează' }));
    expect(api.saveAgentTarget).toHaveBeenCalledWith('2026-09', 'AG1', { mode: 'manual', manual_target: 12500, expected_revision: 7 });
  });
  it('saves automatic mode with a null manual target', async () => {
    api.saveAgentTarget.mockResolvedValueOnce({});
    const manualAgent = { ...agent, target_setting: { ...agent.target_setting!, mode: 'manual', manual_target: 11000 } } as Agent;
    mount({ value: manualAgent });
    await userEvent.click(screen.getByRole('button', { name: 'Editează target AG1' }));
    await userEvent.selectOptions(screen.getByLabelText('Mod calcul target'), 'automatic');
    await userEvent.click(screen.getByRole('button', { name: 'Salvează' }));
    expect(api.saveAgentTarget).toHaveBeenCalledWith('2026-09', 'AG1', { mode: 'automatic', manual_target: null, expected_revision: 7 });
  });
  it('renders read-only target text without an edit button', () => {
    mount({ writable: false });
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
    expect(screen.getByText('10.000 lei')).toBeInTheDocument();
  });
  it('shows the error and reloads earnings after a failed save', async () => {
    api.saveAgentTarget.mockRejectedValueOnce(new Error('conflict'));
    const queryClient = mount(); const invalidate = vi.spyOn(queryClient, 'invalidateQueries');
    await userEvent.click(screen.getByRole('button', { name: 'Editează target AG1' }));
    await userEvent.click(screen.getByRole('button', { name: 'Salvează' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Salvarea a eșuat.');
    await userEvent.click(screen.getByRole('button', { name: 'Reîncarcă' }));
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['native-earnings', '2026-09'] });
  });
});