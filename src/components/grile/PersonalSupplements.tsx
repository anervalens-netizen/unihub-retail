import type { CalendarData, CalendarStore, readEarnings } from '../../api/grileCalendar';
import { agentLabel } from './calendarModel';
import { grileMoney } from './GrilePerformance';
import { SupplementEditor } from './CalendarExtras';

export function PersonalSupplements({ data, calendar, stores, site, writable }: { data: Awaited<ReturnType<typeof readEarnings>>; calendar?: CalendarData; stores: CalendarStore[]; site: string; writable: boolean }) {
  const agents = data.agents.filter(a => a.home_site_code === site);
  return <section className="overflow-hidden rounded-2xl border border-violet-200 dark:border-violet-800"><h4 className="bg-violet-600 px-4 py-3 font-bold text-white">Zile suplimentare · agenții magazinului</h4><div className="grid gap-4 p-4 xl:grid-cols-2">{agents.map(agent => {
    const days = agent.days.filter(d => d.supplemental);
    const elapsed = days.filter(d => d.issue !== 'after_cutoff');
    const total = elapsed.some(d => d.supplemental_pay == null || (d.away && d.commission == null)) ? null : elapsed.reduce((sum, d) => sum + Number(d.supplemental_pay ?? 0) + (d.away ? Number(d.commission ?? 0) : 0), 0);
    return <article key={agent.agent_code} className="min-w-0 rounded-xl border border-slate-200 p-3 dark:border-slate-700"><div className="mb-3 flex flex-wrap justify-between gap-2 text-sm"><strong>{agentLabel(agent)}</strong><span>Total suplimentar: <strong>{grileMoney(total)}</strong></span></div>
      {!days.length ? <p className="text-sm text-slate-500">Fără zile suplimentare.</p> : <div className="overflow-x-auto"><table className="min-w-[560px] w-full text-left text-xs [&_td]:py-2 [&_th]:pb-2"><thead><tr><th>Firmă / locație</th><th>Data</th><th>Vânzare</th><th>% daily</th><th>Comision</th><th>Total</th></tr></thead><tbody>{days.map(day => {
        const store = stores.find(s => s.site_code === day.site_code);
        const planned = day.issue === 'after_cutoff';
        const amount = day.supplemental_pay == null || (day.away && day.commission == null) ? null : Number(day.supplemental_pay) + (day.away ? Number(day.commission) : 0);
        return <tr key={day.work_date}><td>{store?.firma}<br />{store?.locatie ?? day.site_code}</td><td>{day.work_date}{planned && <span className="block text-slate-500">Planificat</span>}</td><td>{planned ? '—' : grileMoney(day.sales)}</td><td>{day.sales != null && day.daily_target != null && Number(day.daily_target) > 0 ? `${(Number(day.sales) / Number(day.daily_target) * 100).toLocaleString('ro-RO', { maximumFractionDigits: 1 })}%` : '—'}</td><td>{planned ? '—' : day.away ? grileMoney(day.commission) : 'Inclus în lunar'}</td><td>{planned ? '—' : grileMoney(amount)}</td></tr>;
      })}</tbody></table></div>}
      {writable && calendar && <SupplementEditor key={calendar.projection_revision} data={calendar} stores={stores} fixedAgent={agent.agent_code} />}
    </article>;
  })}</div><p className="px-4 pb-4 text-xs text-slate-500">În magazinul de bază, comisionul este inclus în cel lunar și nu se adaugă din nou. În alte locații se aplică 3% de la pragul zilnic de 79% inclusiv. Sporul este 150 lei pentru ziua marcată explicit.</p></section>;
}
