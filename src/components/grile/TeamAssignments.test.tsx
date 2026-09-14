// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { TeamAssignments } from './TeamAssignments';
const api=vi.hoisted(()=>({calendarStores:vi.fn(),readCalendar:vi.fn(),calendarCandidates:vi.fn(),saveStoreTeam:vi.fn()}));
vi.mock('../../api/grileCalendar',()=>api);
vi.mock('../../auth/AuthContext',()=>({useAuth:()=>({user:{profile:{groups:['unihub-manager']}}})}));
beforeEach(()=>{
 api.calendarStores.mockResolvedValue([{site_code:'A',locatie:'Alpha',regional:'R',firma:'Mobiup'}]);
 api.readCalendar.mockResolvedValue({month:'2026-09',projection_revision:'a'.repeat(64),roster:[['AG','Ana','A'],['BG','Bogdan','A'],['CG','Cătălin','B']].map(([agent_code,display_name,home_site_code])=>({agent_code,display_name,home_site_code,active:true,revision:4,transfers:[]})),days:[]});
 api.calendarCandidates.mockResolvedValue([]);api.saveStoreTeam.mockResolvedValue({});
});
afterEach(()=>{cleanup();vi.clearAllMocks();});
it('prefills the pair, searches inside dropdown and atomically saves both with delayed activation',async()=>{
 render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false},mutations:{retry:false}}})}><TeamAssignments month="2026-09"/></QueryClientProvider>);
 await userEvent.click(await screen.findByRole('button',{name:'Editează'}));
 expect(screen.getByRole('combobox',{name:'Agent 1'})).toHaveTextContent('Ana');
 expect(screen.getByRole('combobox',{name:'Agent 2'})).toHaveTextContent('Bogdan');
 expect(screen.queryByLabelText('Caută agent')).not.toBeInTheDocument();
 fireEvent.change(screen.getByLabelText('Alocare efectivă de la'),{target:{value:'2026-09-10'}});
 await userEvent.click(screen.getByRole('combobox',{name:'Agent 2'}));
 expect(screen.queryByRole('option',{name:/Ana/})).not.toBeInTheDocument();
 await userEvent.type(screen.getByLabelText('Filtrează Agent 2'),'catalin');
 expect(screen.queryByRole('option',{name:/Bogdan/})).not.toBeInTheDocument();
 await userEvent.click(screen.getByRole('option',{name:/Cătălin/}));
 fireEvent.change(screen.getByLabelText('Cod locație activ din · opțional'),{target:{value:'2026-09-15'}});
 await userEvent.click(screen.getByRole('button',{name:'Salvează cei doi agenți'}));
 await waitFor(()=>expect(api.saveStoreTeam).toHaveBeenCalledWith('2026-09','A',{agent_codes:['AG','CG'],effective_from:'2026-09-10',location_code_active_from:'2026-09-15',expected_revision:'a'.repeat(64)}));
});
