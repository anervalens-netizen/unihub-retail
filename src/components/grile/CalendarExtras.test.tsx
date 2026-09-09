// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { leaveChanges, SupplementEditor } from './CalendarExtras';
import type { CalendarData } from '../../api/grileCalendar';
const api=vi.hoisted(() => ({ saveCalendarDays: vi.fn().mockResolvedValue([]) }));
vi.mock('../../api/grileCalendar', () => api);
afterEach(() => { cleanup(); vi.clearAllMocks(); });
const data: CalendarData={ month:'2026-09', projection_revision:'r', roster:[{agent_code:'A',home_site_code:'S1',active:true,revision:1,month:'2026-09',regional:null,display_name:null,identity_status:'unavailable'}], days:[{agent_code:'A',site_code:'S1',work_date:'2026-09-04',revision:3,status:'work',supplemental:false}],store_hours:[],attendance:[],attendance_by_store:{},attendance_days:[] };
it('writes leave on weekdays only using observed revisions', () => {
  expect(leaveChanges(data,'S1','A','2026-09-03','2026-09-07')).toEqual([
    expect.objectContaining({work_date:'2026-09-03',status:'leave',expected_revision:0,supplemental:false}),
    expect.objectContaining({work_date:'2026-09-04',status:'leave',expected_revision:3,supplemental:false}),
    expect.objectContaining({work_date:'2026-09-07',status:'leave',expected_revision:0,supplemental:false}),
  ]);
});
it('rejects visitors and assignments in another store before leave submission', () => {
  expect(() => leaveChanges(data,'S2','A','2026-09-03','2026-09-07')).toThrow('bază');
  expect(() => leaveChanges({...data,days:[{...data.days[0]!,site_code:'S2'}]},'S1','A','2026-09-03','2026-09-07')).toThrow('alt magazin');
});
it('never enables paid supplemental work until the manager explicitly checks it', async () => {
  const store={site_code:'S1',locatie:'Alpha',firma:'Firma',regional:'RM',asm:''};
  const client=new QueryClient({defaultOptions:{queries:{retry:false},mutations:{retry:false}}});
  render(<QueryClientProvider client={client}><SupplementEditor data={data} stores={[store]} fixedStore={store} /></QueryClientProvider>);
  await userEvent.click(screen.getByText('Programează o zi suplimentară'));
  await userEvent.selectOptions(screen.getByRole('combobox',{name:'Agent'}),'A');
  await userEvent.type(screen.getByLabelText('Data'),'2026-09-04');
  expect(screen.getByRole('button',{name:'Salvează suplimentarul'})).toBeDisabled();
  await userEvent.click(screen.getByRole('checkbox'));
  await userEvent.click(screen.getByRole('button',{name:'Salvează suplimentarul'}));
  expect(api.saveCalendarDays).toHaveBeenCalledWith('2026-09',[expect.objectContaining({agent_code:'A',site_code:'S1',work_date:'2026-09-04',supplemental:true,expected_revision:3})]);
});
