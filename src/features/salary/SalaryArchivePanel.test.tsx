// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { SalaryArchivePanel } from './SalaryArchivePanel';
const api=vi.hoisted(()=>({summary:vi.fn(),rows:vi.fn()}));
vi.mock('../../api/salaryArchive',()=>({fetchSalaryArchiveSummary:api.summary,fetchSalaryArchive:api.rows}));
const data={total:6000,rows:2,months:2,excluded_rows:0,monthly:[{period:'2026-06',company_name:'Mobiup',total:3000,rows:1},{period:'2026-07',company_name:'Mobiup',total:3000,rows:1}],stores:[{location_unmapped:false,site_code:'TEST',location:'Magazin test',company_name:'Mobiup',total:6000,months:2,rows:2}],agents:[{full_name:'Agent test',company_name:'Mobiup',total:6000,months:2,rows:2,avg_salary:3000}]};
beforeEach(()=>{
 vi.clearAllMocks();api.summary.mockResolvedValue(data);api.rows.mockResolvedValue({total_rows:1,items:[{period:'2026-07',company_name:'Mobiup',full_name:'Agent test',site_code:'TEST',location:'Magazin test',total_amount:3000,identity_status:'missing_identifier',review_reasons:[],candidate_person_id:null,source_file:'sursa.xls',source_sheet:'Iulie',source_row:2,selected:true,pnl_eligible:true,already_recorded:false}]});
 HTMLDialogElement.prototype.showModal=function(){this.setAttribute('open','');};
 HTMLDialogElement.prototype.close=function(){this.removeAttribute('open');};
});
describe('SalaryArchivePanel',()=>{
 it('shows aggregated names first and source rows only after opening a detail dialog',async()=>{
  render(<SalaryArchivePanel/>);
  fireEvent.click(screen.getByRole('tab',{name:'Agenți'}));
  const name=await screen.findByRole('button',{name:'Agent test'});
  expect(api.rows).not.toHaveBeenCalled();
  expect(screen.queryByText('sursa.xls')).toBeNull();
  fireEvent.click(name);
  await screen.findByText('sursa.xls');
  expect(api.rows.mock.calls.at(-1)?.[0]).toMatchObject({name_exact:'Agent test',source_company:'Mobiup',offset:0});
  fireEvent.click(screen.getByRole('button',{name:'Închide detaliile salariale'}));
  await waitFor(()=>expect(screen.queryByRole('dialog')).toBeNull());
 });
 it('keeps store and company scopes exact in the detail query',async()=>{
  render(<SalaryArchivePanel globalFilters={{firma:'Mobicell',rm:'Manager',magazin:['TEST'],agent:[]}}/>);
  fireEvent.click(screen.getByRole('tab',{name:'Magazine'}));
  fireEvent.click(await screen.findByRole('button',{name:'Magazin test'}));
  await waitFor(()=>expect(api.rows).toHaveBeenCalled());
  expect(api.rows.mock.calls.at(-1)?.[0]).toMatchObject({site_code:['TEST'],source_company:'Mobiup'});
  expect(api.rows.mock.calls.at(-1)?.[0].regional).toBeUndefined();
  expect(api.rows.mock.calls.at(-1)?.[0].company_name).toBeUndefined();
 });
});
