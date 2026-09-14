// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, it, vi } from 'vitest';
import { CalendarDayEditor } from './CalendarDayEditor';
import { calendarDayAt, conflictingCalendarDay, dayChanges } from './calendarModel';
import type { CalendarData } from '../../api/grileCalendar';
afterEach(cleanup);
const store={site_code:'S1',locatie:'Store 1',firma:'Firm',regional:'R',asm:''};
const other={...store,site_code:'S2'};
const data: CalendarData={month:'2026-09',projection_revision:'',attendance:[],attendance_days:[],attendance_by_store:{},store_hours:[],closures:[],roster:[
 {month:'2026-09',agent_code:'TL1',home_site_code:'TL',regional:'R',active:true,revision:1,display_name:null,transfers:[],identity_status:'unavailable'},
 {month:'2026-09',agent_code:'A1',home_site_code:'S1',regional:null,active:true,revision:1,display_name:null,transfers:[],identity_status:'unavailable'},
],days:[{agent_code:'TL1',site_code:'S2',work_date:'2026-09-10',status:'work',supplemental:true,revision:8},{agent_code:'A1',site_code:'S1',work_date:'2026-09-10',status:'work',supplemental:false,revision:3}]};

it('saves the screenshot scenario without cancelling the other TL location',async()=>{
 const onSave=vi.fn();
 render(<CalendarDayEditor data={data} store={store} stores={[store,other]} date="2026-09-10" busy={false} writable onSave={onSave}/>);
 await userEvent.selectOptions(screen.getByLabelText('Agent pentru zi'),'TL1');
 expect(screen.queryByRole('alert')).not.toBeInTheDocument();
 expect(screen.getByRole('button',{name:'Salvează ziua'})).toBeEnabled();
 await userEvent.click(screen.getByRole('button',{name:'Salvează ziua'}));
 expect(onSave).toHaveBeenCalledWith([
  {agent_code:'A1',site_code:'S1',work_date:'2026-09-10',status:'cancelled',supplemental:false,expected_revision:3},
  {agent_code:'TL1',site_code:'S1',work_date:'2026-09-10',status:'work',supplemental:true,expected_revision:0},
 ]);
});
it('uses the selected store revision when cancelling or replacing a shared TL assignment',()=>{
 const both={...data,days:[data.days[0]!,{...data.days[0]!,site_code:'S1',revision:2}]};
 expect(calendarDayAt(both,'TL1','2026-09-10','S1')?.revision).toBe(2);
 expect(dayChanges(both,{agent_code:'TL1',site_code:'S1',work_date:'2026-09-10',status:'cancelled',supplemental:false})).toEqual([
  {agent_code:'TL1',site_code:'S1',work_date:'2026-09-10',status:'cancelled',supplemental:false,expected_revision:2},
 ]);
 expect(dayChanges(both,{agent_code:'A1',site_code:'S1',work_date:'2026-09-10',status:'work',supplemental:false})[0]).toMatchObject({agent_code:'TL1',site_code:'S1',status:'cancelled',expected_revision:2});
});
it('keeps the conflict for ordinary agents and makes the same exception available to supplementary editors',async()=>{
 expect(conflictingCalendarDay(data,'TL1','2026-09-10','S1')).toBeUndefined();
 expect(conflictingCalendarDay(data,'A1','2026-09-10','S2')?.site_code).toBe('S1');
 render(<CalendarDayEditor data={data} store={other} stores={[store,other]} date="2026-09-10" busy={false} writable onSave={vi.fn()}/>);
 await userEvent.selectOptions(screen.getByLabelText('Agent pentru zi'),'A1');
 expect(screen.getByRole('alert')).toHaveTextContent('S1');
 expect(screen.getByRole('button',{name:'Salvează ziua'})).toBeDisabled();
});
