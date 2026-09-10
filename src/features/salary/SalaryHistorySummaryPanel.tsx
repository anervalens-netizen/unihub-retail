import { useEffect, useState } from 'react';
import { fetchSalaryArchiveSummary, type SalaryArchiveQuery, type SalaryArchiveSummary } from '../../api/salaryArchive';
import { getApiErrorMessage } from '../../api/client';
const money = new Intl.NumberFormat('ro-RO', {style:'currency',currency:'RON',maximumFractionDigits:2});
export function SalaryHistorySummaryPanel({view,filters}:{view:'overview'|'stores';filters:SalaryArchiveQuery}) {
  const key=JSON.stringify(filters);
  const [state,setState]=useState<{key:string;data:SalaryArchiveSummary|null;error:string}>({key:'',data:null,error:''});
  useEffect(()=>{
    const controller=new AbortController();
    const timer=setTimeout(()=>{
      void fetchSalaryArchiveSummary(JSON.parse(key) as SalaryArchiveQuery,controller.signal)
        .then(data=>{if(!controller.signal.aborted)setState({key,data,error:''});})
        .catch((error:unknown)=>{if(!controller.signal.aborted)setState({key,data:null,error:getApiErrorMessage(error,'Istoricul nu a putut fi încărcat.')});});
    },250);
    return ()=>{clearTimeout(timer);controller.abort();};
  },[key]);
  if(state.key!==key)return <p role="status" className="p-6 text-center text-sm">Se încarcă sumarul istoricului...</p>;
  if(state.error)return <p role="alert" className="rounded-xl bg-amber-50 p-3 text-amber-900">{state.error}</p>;
  const data=state.data;
  if(!data)return null;
  const periods=[...new Set(data.monthly.map(row=>row.period))];
  const byMonth=periods.map(period=>({period,mobiup:data.monthly.filter(row=>row.period===period&&row.company_name==='Mobiup').reduce((sum,row)=>sum+row.total,0),mobicell:data.monthly.filter(row=>row.period===period&&row.company_name==='Mobicell').reduce((sum,row)=>sum+row.total,0),rows:data.monthly.filter(row=>row.period===period).reduce((sum,row)=>sum+row.rows,0)}));
  const max=Math.max(1,...byMonth.map(row=>row.mobiup+row.mobicell));
  const cell='p-3 border-t border-slate-100 dark:border-slate-800';
  return <div className="space-y-4">
    <p className="text-xs text-slate-500">Totaluri din versiunile selectate ale statelor HR, pentru toate rândurile filtrate. Versiunile nealese și rândurile fără sumă, lună sau firmă clară sunt excluse. Acoperirea poate fi parțială; lunile lipsă nu reprezintă zero. Aceste totaluri nu se adună cu sinteza existentă.</p>
    {view==='overview' ? <>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">{[['Net + bonuri',money.format(data.total)],['Înregistrări',data.rows.toLocaleString('ro-RO')],['Luni cu documente',data.months],['Rânduri excluse',data.excluded_rows.toLocaleString('ro-RO')]].map(([label,value])=><div key={label} className="glass rounded-xl p-4"><p className="text-xs text-slate-500">{label}</p><p className="mt-1 text-xl font-semibold">{value}</p></div>)}</div>
      <div className="glass overflow-x-auto rounded-2xl"><table className="w-full text-sm"><caption className="p-3 text-left font-semibold">Evoluția lunară a salariilor din statele HR</caption><thead><tr>{['Lună','Mobiup','Mobicell','Total','Înregistrări'].map(label=><th key={label} className="p-3 text-left">{label}</th>)}</tr></thead><tbody>{byMonth.map(row=><tr key={row.period}><td className={cell}>{row.period}</td><td className={cell}>{data.monthly.some(item=>item.period===row.period&&item.company_name==='Mobiup')?money.format(row.mobiup):'Fără document'}</td><td className={cell}>{data.monthly.some(item=>item.period===row.period&&item.company_name==='Mobicell')?money.format(row.mobicell):'Fără document'}</td><td className={cell}><span>{money.format(row.mobiup+row.mobicell)}</span><div aria-hidden="true" className="mt-1 h-1 rounded bg-indigo-200" style={{width:`${Math.max(0,(row.mobiup+row.mobicell)/max*100)}%`}} /></td><td className={cell}>{row.rows}</td></tr>)}</tbody></table></div>
    </> : <div className="glass overflow-x-auto rounded-2xl"><table className="w-full text-sm"><caption className="p-3 text-left font-semibold">Salarii pe magazine — perioada filtrată</caption><thead><tr>{['Magazin','Firmă','Net + bonuri','Luni','Înregistrări'].map(label=><th key={label} className="p-3 text-left">{label}</th>)}</tr></thead><tbody>{data.stores.map((row,index)=><tr key={`${row.company_name}-${row.site_code}-${row.location}-${index}`}><td className={cell}>{row.location}</td><td className={cell}>{row.company_name}</td><td className={cell}>{money.format(row.total)}</td><td className={cell}>{row.months}</td><td className={cell}>{row.rows}</td></tr>)}</tbody></table></div>}
    {data.rows===0&&<p className="p-6 text-center text-sm">Nu există rânduri selectate pentru filtrele alese.</p>}
  </div>;
}
