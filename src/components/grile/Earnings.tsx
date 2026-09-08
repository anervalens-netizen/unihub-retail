import { useQuery } from '@tanstack/react-query';
import { readEarnings } from '../../api/grileCalendar';

const money = (value: string | number | null) => value === null ? 'Indisponibil' : `${Number(value).toLocaleString('ro-RO', { maximumFractionDigits: 2 })} lei`;
const issues: Record<string, string> = {
  missing_published_source: 'Lipsește importul publicat cu dată limită.',
  missing_sales: 'Lipsesc vânzări pentru o zi lucrată; nu sunt considerate zero.',
  missing_positive_target: 'Lipsește un target pozitiv pentru magazin.',
};

export function Earnings({ month, site, calendarRevision }: { month: string; site: string; calendarRevision: string }) {
  const query = useQuery({ queryKey: ['native-earnings', month, calendarRevision], queryFn: ({ signal }) => readEarnings(month, signal) });
  if (query.isError) return <p role="alert">Câștigurile nu pot fi încărcate. <button onClick={() => void query.refetch()}>Reîncarcă</button></p>;
  if (!query.data || query.isFetching) return <p role="status">Se calculează câștigurile…</p>;
  const data = query.data;
  if (data.calendar_revision !== calendarRevision) return <p role="alert">Calendarul s-a schimbat. Reîncarcă programul pentru a vedea câștigurile aceleiași revizii.</p>;
  const agents = data.agents.filter(agent => agent.home_site_code === site);
  return <section className="space-y-4">
    <h3 className="font-semibold">Câștiguri provizorii</h3>
    <p>Vânzări până la {data.cutoff ?? 'dată indisponibilă'}. Targetul folosește {data.selling_days[site] ?? 0} zile de funcționare programate în această lună. Completează calendarul întregii luni pentru o estimare corectă.</p>
    <p className="text-sm text-slate-500">Comision lunar: prag 80%, bonus la 100% / 120%. Alte locații: prag zilnic 79% inclusiv. Suplimentare: 150 lei/zi până la data limită a vânzărilor.</p>
    {!data.cutoff && <p role="alert">Lipsește importul publicat cu dată limită.</p>}
    {!agents.length && <p>Nu există agenți de bază confirmați pentru acest magazin.</p>}
    {agents.map(agent => <article key={agent.agent_code} className="space-y-3 rounded-xl border p-4">
      <h4 className="font-semibold">{agent.agent_code}</h4>
      {agent.issues.map(issue => <p role="alert" key={issue}>{issues[issue] ?? issue}</p>)}
      <dl className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        <div><dt>Target personal · {agent.home_work_days} zile</dt><dd>{money(agent.home_target)}</dd></div>
        <div><dt>Vânzări magazin de bază</dt><dd>{money(agent.home_sales)}</dd></div>
        <div><dt>Comision lunar</dt><dd>{money(agent.home_commission)}</dd></div>
        <div><dt>Comision alte locații</dt><dd>{money(agent.away_commission)}</dd></div>
        <div><dt>Plata suplimentărilor</dt><dd>{money(agent.supplemental_pay)}</dd></div>
        <div><dt>Total componente calculate</dt><dd className="font-semibold">{money(agent.known_earnings)}</dd></div>
      </dl>
      <details><summary className="cursor-pointer">Detalii pe zile și locații</summary><div className="overflow-x-auto"><table className="w-full min-w-[720px] text-left text-sm [&_th]:px-3 [&_th]:py-2 [&_td]:px-3 [&_td]:py-2"><thead><tr><th>Data</th><th>Locația</th><th>Vânzări</th><th>Target zilnic</th><th>Comision alte locații</th><th>Suplimentare</th></tr></thead><tbody>{agent.days.map(day => <tr key={day.work_date}><td>{day.work_date}{day.issue === 'after_cutoff' ? ' · planificat' : ''}</td><td>{day.site_code}</td><td>{money(day.sales)}</td><td>{money(day.daily_target)}</td><td>{day.away ? money(day.commission) : 'Inclus în lunar'}</td><td>{day.supplemental ? money(day.supplemental_pay) : '—'}</td></tr>)}</tbody></table></div></details>
    </article>)}
    {data.unassigned_sales.some(row => row.site_code === site) && <p role="alert">Există vânzări ale magazinului fără persoană alocată în calendar. Completează programul; aceste sume nu au fost atribuite automat.</p>}
    <p className="text-sm text-slate-500">Baza salarială, bonurile, SIM, E-pay și celelalte stimulente nu sunt încă incluse. Acest total nu reprezintă salariul oficial. V1 rămâne oficial.</p>
  </section>;
}
