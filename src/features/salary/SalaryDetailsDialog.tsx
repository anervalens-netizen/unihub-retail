import { useEffect, useRef, useState } from 'react';
import { SalaryAgentBarChart } from '../../components/SalaryAgentBarChart';
import { fetchSalaryArchive, fetchSalaryArchiveSummary, type SalaryArchiveQuery, type SalaryArchiveResponse, type SalaryArchiveSummary } from '../../api/salaryArchive';
import { getApiErrorMessage } from '../../api/client';
export interface SalaryDetailSelection {title:string;filters:SalaryArchiveQuery}
const money=new Intl.NumberFormat('ro-RO',{style:'currency',currency:'RON'});
export function SalaryDetailsDialog({selection,onClose}:{selection:SalaryDetailSelection|null;onClose:()=>void}) {
 const ref=useRef<HTMLDialogElement>(null);
 const [page,setPage]=useState(0);
 const [data,setData]=useState<{key:string;rows:SalaryArchiveResponse;summary:SalaryArchiveSummary}|null>(null);
 const [error,setError]=useState('');
 const scope=selection?JSON.stringify(selection.filters):'';
 const key=scope+':'+page;
 useEffect(()=>{if(selection){if(!ref.current?.open)ref.current?.showModal();}else ref.current?.close();},[selection]);
 useEffect(()=>{setPage(0);},[scope]);
 useEffect(()=>{
  if(!scope)return;
  const controller=new AbortController();setError('');
  const filters=JSON.parse(scope) as SalaryArchiveQuery;
  void Promise.all([fetchSalaryArchive({...filters,limit:50,offset:page*50},controller.signal),fetchSalaryArchiveSummary(filters,controller.signal)]).then(([rows,summary])=>{if(!controller.signal.aborted)setData({key,rows,summary});}).catch((e:unknown)=>{if(!controller.signal.aborted)setError(getApiErrorMessage(e,'Detaliile nu au putut fi încărcate.'));});
  return ()=>controller.abort();
 },[scope,key,page]);
 const ready=data?.key===key?data:null;
 return <dialog aria-labelledby="salary-detail-title" ref={ref} onCancel={onClose} onClose={onClose} className="fixed inset-y-0 left-auto right-0 m-0 ml-auto h-dvh max-h-dvh w-full max-w-2xl overflow-y-auto bg-white p-0 text-slate-800 shadow-2xl backdrop:bg-black/40 dark:bg-slate-900 dark:text-slate-100">
  <header className="sticky top-0 z-10 flex items-center justify-between border-b bg-white px-6 py-4 dark:bg-slate-900"><div><h2 id="salary-detail-title" className="text-lg font-bold">{selection?.title}</h2><p className="text-xs text-slate-500">Istoric salarial · net + bonuri</p></div><button type="button" onClick={onClose} aria-label="Închide detaliile salariale" className="rounded-lg px-3 py-2">✕</button></header>
  <div className="space-y-4 p-6">{error?<p role="alert">{error}</p>:!ready?<p role="status">Se încarcă detaliile...</p>:<>
   <div className="grid grid-cols-3 gap-3">{[['Total selectat',money.format(ready.summary.total)],['Luni',ready.summary.months],['Înregistrări',ready.summary.rows]].map(([label,value])=><div key={label} className="glass rounded-xl p-3"><p className="text-xs text-slate-500">{label}</p><p className="font-bold">{value}</p></div>)}</div>
   <p className="text-xs text-slate-500">Totalul folosește înregistrările selectate. Gruparea după nume și firmă este doar pentru consultare; nu modifică identitatea persoanelor. {ready.summary.excluded_rows} rânduri excluse din total.</p>
   <h3 className="font-semibold">Evoluție lunară</h3><SalaryAgentBarChart data={ready.summary.monthly.map(row=>({year:Number(row.period.slice(0,4)),month:Number(row.period.slice(5,7)),total_salary:row.total,company_name:row.company_name,site_code:null,locatie:null}))} /><div className="max-h-48 overflow-auto">{ready.summary.monthly.map(row=><div key={row.period+row.company_name} className="flex justify-between border-b py-1 text-sm"><span>{row.period} · {row.company_name}</span><span>{money.format(row.total)}</span></div>)}</div>
   <h3 className="font-semibold">Detalii din statele HR</h3><div className="overflow-x-auto"><table className="w-full text-sm"><thead><tr>{['Lună','Nume','Magazin','Sumă','Sursă'].map(x=><th className="p-2 text-left" key={x}>{x}</th>)}</tr></thead><tbody>{ready.rows.items.map((row,i)=><tr key={row.source_file+row.source_row+i} className="border-t"><td className="p-2">{row.period??'Neclarificată'}</td><td className="p-2">{row.full_name}<p className="text-xs text-slate-500">{row.company_name}</p></td><td className="p-2">{row.location}</td><td className="p-2 whitespace-nowrap">{row.total_amount===null?'Neclarificată':money.format(row.total_amount)}{!row.selected&&<p className="text-xs text-amber-700">Versiune nealeasă</p>}</td><td className="p-2 text-xs">{row.source_file}{selection?.filters.data_source !== 'recorded' && <p>{row.source_sheet} · rând {row.source_row}</p>}</td></tr>)}</tbody></table></div>
   <div className="flex items-center justify-between"><span className="text-xs">{ready.rows.total_rows ? page*50+1 : 0}–{Math.min((page+1)*50,ready.rows.total_rows)} / {ready.rows.total_rows}</span><div className="flex gap-3"><button disabled={page===0} onClick={()=>setPage(page-1)} className="rounded-lg border px-3 py-2 disabled:opacity-40">Înapoi</button><button disabled={(page+1)*50>=ready.rows.total_rows} onClick={()=>setPage(page+1)} className="rounded-lg border px-3 py-2 disabled:opacity-40">Înainte</button></div></div>
  </>}</div>
 </dialog>;
}
