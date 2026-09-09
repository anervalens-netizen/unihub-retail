import { useMutation, useQuery } from '@tanstack/react-query';
import { downloadEarnings, readEarnings } from '../../api/grileCalendar';
import { agentLabel } from './calendarModel';
import { StoreSalesSummary } from './StoreSalesSummary';

const money = (value: string | number | null) => value === null ? 'Indisponibil' : `${Number(value).toLocaleString('ro-RO', { maximumFractionDigits: 2 })} lei`;
const issues: Record<string, string> = {
  missing_published_source: 'Lipsește importul publicat cu dată limită.',
  missing_sales: 'Lipsesc vânzări pentru o zi lucrată; nu sunt considerate zero.',
  missing_positive_target: 'Lipsește un target pozitiv pentru magazin.',
};

export function Earnings({ month, site, calendarRevision }: { month: string; site: string; calendarRevision: string }) {
  const query = useQuery({ queryKey: ['native-earnings', month, calendarRevision], queryFn: ({ signal }) => readEarnings(month, signal) });
  const download = useMutation({ mutationFn: () => downloadEarnings(month, query.data?.projection_revision ?? '') });
  if (query.isError) return <p role="alert">Câștigurile nu pot fi încărcate. <button onClick={() => void query.refetch()}>Reîncarcă</button></p>;
  if (!query.data || query.isFetching) return <p role="status">Se calculează câștigurile…</p>;
  const data = query.data;
  if (data.calendar_revision !== calendarRevision) return <p role="alert">Calendarul s-a schimbat. Reîncarcă programul pentru a vedea câștigurile aceleiași revizii.</p>;
  const agents = data.agents.filter(agent => agent.home_site_code === site);
  return <section className="space-y-4">
    <h3 className="font-semibold">Câștiguri provizorii</h3>
    {site !== 'TL' && <StoreSalesSummary data={data} site={site} />}
    <button disabled={download.isPending} onClick={() => download.mutate()} className="native-primary">Descarcă câștiguri și pontaje ZIP</button>
    <p className="text-sm text-slate-500">Exportă toate persoanele și magazinele din programul lunii, din aceeași revizie. Centralizatorul este provizoriu.</p>
    {download.isError && <p role="alert">Exportul nu a reușit sau datele s-au schimbat. <button onClick={() => { download.reset(); void query.refetch(); }}>Reîncarcă câștigurile</button></p>}
    <p>Vânzări până la {data.cutoff ?? 'dată indisponibilă'}. Targetul folosește {data.selling_days[site] ?? 0} zile de funcționare programate în această lună. Completează calendarul întregii luni pentru o estimare corectă.</p>
    <p className="text-sm text-slate-500">Comision lunar: prag 80%, bonus la 100% / 120%. Alte locații: prag zilnic 79% inclusiv. Suplimentare: 150 lei/zi până la data limită a vânzărilor.</p>
    {!data.cutoff && <p role="alert">Lipsește importul publicat cu dată limită.</p>}
    {!agents.length && <p>Nu există agenți de bază confirmați pentru acest magazin.</p>}
    {agents.map(agent => <article key={agent.agent_code} className="space-y-3 rounded-2xl border border-slate-100 bg-white p-4 shadow-sm dark:border-slate-700 dark:bg-slate-900">
      <h4 className="font-semibold">{agentLabel(agent)}</h4>
      {agent.identity_status !== 'confirmed' && <p className="text-sm text-amber-700">{agent.identity_status === 'conflicting' ? 'Codul are identități salariale contradictorii. Este necesară reconcilierea.' : 'Identitatea salarială nu este confirmată pentru magazinul de bază și luna selectată.'}</p>}
      {agent.issues.map(issue => <p role="alert" key={issue}>{issues[issue] ?? issue}</p>)}
      <dl className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        <div className="rounded-2xl bg-slate-50 p-3 dark:bg-slate-800"><dt className="text-xs text-slate-500">Target personal · {agent.home_work_days} zile</dt><dd className="mt-1 text-lg font-bold">{money(agent.home_target)}</dd></div>
        <div className="rounded-2xl bg-slate-50 p-3 dark:bg-slate-800"><dt className="text-xs text-slate-500">Vânzări magazin de bază</dt><dd className="mt-1 text-lg font-bold">{money(agent.home_sales)}</dd></div>
        <div className="rounded-2xl bg-slate-50 p-3 dark:bg-slate-800"><dt className="text-xs text-slate-500">Comision lunar</dt><dd className="mt-1 text-lg font-bold">{money(agent.home_commission)}</dd></div>
        <div className="rounded-2xl bg-slate-50 p-3 dark:bg-slate-800"><dt className="text-xs text-slate-500">Comision alte locații</dt><dd className="mt-1 text-lg font-bold">{money(agent.away_commission)}</dd></div>
        <div className="rounded-2xl bg-slate-50 p-3 dark:bg-slate-800"><dt className="text-xs text-slate-500">Plata suplimentărilor</dt><dd className="mt-1 text-lg font-bold">{money(agent.supplemental_pay)}</dd></div>
        <div className="rounded-2xl bg-slate-50 p-3 dark:bg-slate-800"><dt className="text-xs text-slate-500">Total componente calculate</dt><dd className="font-semibold">{money(agent.known_earnings)}</dd></div>
      </dl>
      <details><summary className="cursor-pointer">Detalii pe zile și locații</summary><div className="overflow-x-auto"><table className="w-full min-w-[720px] text-left text-sm [&_th]:px-3 [&_th]:py-2 [&_td]:px-3 [&_td]:py-2"><thead><tr><th>Data</th><th>Locația</th><th>Vânzări</th><th>Target zilnic</th><th>Comision alte locații</th><th>Suplimentare</th></tr></thead><tbody>{agent.days.map(day => <tr key={day.work_date}><td>{day.work_date}{day.issue === 'after_cutoff' ? ' · planificat' : ''}</td><td>{day.site_code}</td><td>{money(day.sales)}</td><td>{money(day.daily_target)}</td><td>{day.away ? money(day.commission) : 'Inclus în lunar'}</td><td>{day.supplemental ? money(day.supplemental_pay) : '—'}</td></tr>)}</tbody></table></div></details>
    </article>)}
    {data.unassigned_sales.some(row => row.site_code === site) && <p role="alert">Există vânzări ale magazinului fără persoană alocată în calendar. Completează programul; aceste sume nu au fost atribuite automat.</p>}
    <p className="text-sm text-slate-500">Baza salarială, bonurile, SIM, E-pay și celelalte stimulente nu sunt încă incluse. Acest total nu reprezintă salariul oficial. V1 rămâne oficial.</p>
  </section>;
}
