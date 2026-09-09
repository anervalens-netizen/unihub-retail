// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { CompensationEditor } from './CompensationEditor';
const api=vi.hoisted(()=>({saveCompensation:vi.fn().mockResolvedValue({})}));
vi.mock('../../api/grileCalendar',()=>api);
afterEach(()=>{cleanup();vi.clearAllMocks();});
const value={month:'2026-09',agent_code:'AG1',revision:4,salary_base:2600,vouchers:480,sim_quantity:null,epay_under_50:null,epay_over_50:null,incentive:null,adjustment:null};
function mount(writable=true){render(<QueryClientProvider client={new QueryClient({defaultOptions:{mutations:{retry:false}}})}><CompensationEditor value={value} writable={writable}/></QueryClientProvider>);}
it('keeps missing quantities blank until explicit manager confirmation and sends the observed revision',async()=>{
  mount();await userEvent.click(screen.getByText('Completări de manager'));
  expect(screen.getByLabelText('SIM · cantitate')).toHaveValue(null);
  await userEvent.type(screen.getByLabelText('SIM · cantitate'),'2');
  await userEvent.click(screen.getByRole('button',{name:'Confirmă câmpurile goale ca zero'}));
  await userEvent.click(screen.getByRole('button',{name:'Salvează completările'}));
  expect(api.saveCompensation).toHaveBeenCalledWith('2026-09','AG1',{salary_base:2600,vouchers:480,sim_quantity:2,epay_under_50:0,epay_over_50:0,incentive:0,adjustment:0,expected_revision:4});
});
it('does not offer editing to read-only users',()=>{mount(false);expect(screen.queryByText('Completări de manager')).not.toBeInTheDocument();});
