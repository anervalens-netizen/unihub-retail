import { expect, it } from 'vitest';
import { calendarTeamGroups } from './calendarTeamLeaders';
it('keeps confirmed ownership independent of visiting shifts and retains unassigned stores', () => {
  const make=(site_code: string, regional='Andrei Stancu')=>({site_code,regional,locatie:site_code,firma:'Firma',asm:''});
  const groups=calendarTeamGroups([make('PRKLK'),make('AFICOTRO'),make('CTCITYPRK'),make('UNKNOWN'),make('CTVIVO','Other manager')]);
  expect(groups.map(g=>[g.code,g.stores.map(s=>s.site_code)])).toEqual([['LAUR',['PRKLK']],['VDELIA',['AFICOTRO']],['DAVIDDA',['CTCITYPRK']],['',['UNKNOWN','CTVIVO']]]);
  expect(calendarTeamGroups([])).toEqual([]);
});
