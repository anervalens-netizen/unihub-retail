import { useMutation, useQuery } from '@tanstack/react-query';
import { downloadEarnings, readEarnings, type CalendarData, type CalendarStore } from '../../api/grileCalendar';
import { StorePerformance, AgentPerformance } from './GrilePerformance';
import { PersonalSupplements } from './PersonalSupplements';
import { StoreSalesSummary } from './StoreSalesSummary';

const issues: Record<string, string> = {
  missing_published_source: 'Lipsește importul publicat cu dată limită.',
  missing_sales: 'Lipsesc vânzări pentru o zi lucrată; nu sunt considerate zero.',
  missing_positive_target: 'Lipsește un target pozitiv pentru magazin.',
};
export function Earnings({ month, site, calendarRevision, calendar, stores = [], writable = false }: { month: string; site: string; calendarRevision: string; calendar?: CalendarData; stores?: CalendarStore[]; writable?: boolean }) {
  const query = useQuery({ queryKey: ['native-earnings', month, calendarRevision], queryFn: ({ signal }) => readEarnings(month, signal) });
  const download = useMutation({ mutationFn: () => downloadEarnings(month, query.data?.projection_revision ?? '') });
  if (query.isError) return <p role="alert">Câștigurile nu pot fi încărcate. <button onClick={() => void query.refetch()}>Reîncarcă</button></p>;
  if (!query.data || query.isFetching) return <p role="status">Se calculează câștigurile…</p>;
  const data = query.data;
  if (data.calendar_revision !== calendarRevision) return <p role="alert">Calendarul s-a schimbat. Reîncarcă programul pentru a vedea câștigurile aceleiași revizii.</p>;
  const agents = data.agents.filter(agent => agent.home_site_code === site);
  const store = stores.find(s => s.site_code === site) ?? { site_code: site, locatie: site, firma: '', regional: '', asm: '' };
  return <section className="space-y-5">
    <StorePerformance data={data} store={store} />
    {site !== 'TL' && <details><summary className="cursor-pointer text-sm">Vânzări și alocări pe magazin</summary><StoreSalesSummary data={data} site={site} /></details>}
    <div className="grid gap-4 xl:grid-cols-2">{agents.map((agent, index) => <div key={agent.agent_code} className="space-y-2">{agent.issues.map(issue => <p role="alert" key={issue} className="text-sm text-amber-700">{issues[issue] ?? issue}</p>)}{agent.identity_status === 'conflicting' && <p className="text-sm text-amber-700">Codul are identități salariale contradictorii. Este necesară reconcilierea.</p>}<AgentPerformance agent={agent} writable={writable} index={index} /></div>)}</div>
    {!agents.length && <p>Nu există agenți de bază confirmați pentru acest magazin.</p>}
    <PersonalSupplements data={data} calendar={calendar} stores={stores} site={site} writable={writable} />
    {data.unassigned_sales.some(row => row.site_code === site) && <p role="alert">Există vânzări ale magazinului fără persoană alocată în calendar. Completează programul; aceste sume nu au fost atribuite automat.</p>}
    <p className="text-xs text-slate-500">Valori provizorii, până la {data.cutoff ?? 'dată indisponibilă'}. Forecastul folosește media zilelor lucrate și programul rămas. La forecastul salarial se proiectează comisionul magazinului de bază; celelalte componente confirmate rămân la valoarea curentă. V1 rămâne oficial.</p>
    <button disabled={download.isPending} onClick={() => download.mutate()} className="native-primary">Descarcă câștiguri și pontaje ZIP</button>
    <p className="text-xs text-slate-500">ZIP-ul existent exportă toate magazinele: pontajele și componentele de comision/suplimentare. Completările salariale din carduri nu sunt încă incluse în acest export.</p>
    {download.isError && <p role="alert">Exportul nu a reușit sau datele s-au schimbat. <button onClick={() => { download.reset(); void query.refetch(); }}>Reîncarcă câștigurile</button></p>}
  </section>;
}
