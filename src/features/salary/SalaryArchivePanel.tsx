import { useState } from 'react';
import { SegmentedTabs } from '../../components/common/SegmentedTabs';
import { SalaryHistorySummaryPanel } from './SalaryHistorySummaryPanel';
import type { AppFilters } from '../../lib/appFilters';
import { getCurrentYearMonth } from '../../lib/dates';
import { ALL_FIRMS, ALL_SCOPE } from '../../lib/filterValues';
const controlClass='min-h-9 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-900';
export function SalaryArchivePanel({globalFilters}:{globalFilters?:AppFilters}) {
 const [view,setView]=useState<'overview'|'stores'|'agents'>('overview');
 const [search,setSearch]=useState('');
 const [year,setYear]=useState('');
 const [month,setMonth]=useState('');
 const currentYear=Number(getCurrentYearMonth().slice(0,4));
 const sites=globalFilters?.magazin.length?globalFilters.magazin:undefined;
 const company=globalFilters?.firma&&globalFilters.firma!==ALL_FIRMS?globalFilters.firma:undefined;
 const regional=globalFilters?.rm&&globalFilters.rm!==ALL_SCOPE?globalFilters.rm:undefined;
 return <section aria-label="Istoric state oficiale HR" className="mx-4 space-y-4 pb-4">
  <SegmentedTabs ariaLabel="Vizualizare istoric salarii" level="secondary" options={[{value:'overview',label:'Overview'},{value:'stores',label:'Magazine'},{value:'agents',label:'Agenți'}]} value={view} onChange={setView} />
  <p className="rounded-xl bg-indigo-50 px-3 py-2 text-xs text-indigo-800 dark:bg-indigo-950/30 dark:text-indigo-200">State oficiale HR, inclusiv foști angajați fără cod ERP. Listele sunt agregate; apasă pe un magazin sau nume pentru istoricul lunar și documentele sursă.</p>
  <div className="flex flex-wrap items-end gap-3">
   <label className="grid gap-1 text-xs">Nume din HR<input aria-label="Caută nume în istoricul HR" type="search" maxLength={120} value={search} onChange={e=>setSearch(e.target.value)} placeholder="Caută după nume..." className={controlClass}/></label>
   <label className="grid gap-1 text-xs">An<select aria-label="An istoric HR" value={year} onChange={e=>setYear(e.target.value)} className={controlClass}><option value="">Toți anii</option>{Array.from({length:Math.max(0,currentYear-2015+1)},(_,i)=>currentYear-i).map(value=><option key={value} value={value}>{value}</option>)}</select></label>
   <label className="grid gap-1 text-xs">Lună<select aria-label="Lună istoric HR" value={month} onChange={e=>setMonth(e.target.value)} className={controlClass}><option value="">Toate lunile</option>{Array.from({length:12},(_,i)=>i+1).map(value=><option key={value} value={value}>{String(value).padStart(2,'0')}</option>)}</select></label>
  </div>
  {!!globalFilters?.agent.length&&<p className="text-xs text-slate-500">Pentru foștii angajați folosește numele din HR; filtrul de cod ERP nu se aplică istoricului.</p>}
  <SalaryHistorySummaryPanel view={view} filters={{year:year?Number(year):undefined,month:month?Number(month):undefined,search:search.trim()||undefined,site_code:sites,company_name:sites?undefined:company,regional:sites?undefined:regional}} />
 </section>;
}
