import { Target, TrendingUp, UserRound, Wallet } from 'lucide-react';
import type { CalendarStore, readEarnings } from '../../api/grileCalendar';
import { agentLabel } from './calendarModel';
type Agent = Awaited<ReturnType<typeof readEarnings>>['agents'][number];
import { CompensationEditor } from './CompensationEditor';

export const grileMoney = (value: string | number | null | undefined) => value == null ? 'De completat' : `${Number(value).toLocaleString('ro-RO', { maximumFractionDigits: 0 })} lei`;
const percent = (value: string | number | null | undefined) => value == null ? '—' : `${Number(value).toLocaleString('ro-RO', { maximumFractionDigits: 1 })}%`;
function Metrics({ values }: { values: [string, string | number][] }) {
  return <dl className="grid grid-cols-3 gap-x-3 gap-y-4 py-3">{values.map(([label, value]) => <div key={label} className="min-w-0"><dt className="text-[11px] text-slate-500">{label}</dt><dd className="mt-1 break-words text-sm font-bold text-slate-900 sm:text-base dark:text-white">{value}</dd></div>)}</dl>;
}
export function StorePerformance({ data, store }: { data: Awaited<ReturnType<typeof readEarnings>>; store: CalendarStore }) {
  const p = data.stores?.[store.site_code];
  return <header className="space-y-4"><div className="flex flex-wrap items-start justify-between gap-2"><div><h3 className="text-xl font-bold">Performanță magazin și echipă</h3><p className="text-sm text-slate-500">{store.firma} · {store.locatie} · {data.month}</p></div><span className="text-xs text-slate-500">Vânzări până la {data.cutoff ?? 'dată indisponibilă'}</span></div>
    <div className="grid grid-cols-2 gap-3 rounded-2xl border border-slate-200 p-4 sm:grid-cols-5 dark:border-slate-700">{[
      ['Target vânzări', grileMoney(p?.target), ''], ['Realizat', grileMoney(p?.sales), percent(p?.progress)], ['Forecast', grileMoney(p?.forecast), percent(p?.forecast_progress)], ['Zilnic 90%', grileMoney(p?.daily_90), ''], ['Zilnic 100%', grileMoney(p?.daily_100), ''],
    ].map(([label, value, extra]) => <div key={label}><span className="text-[10px] uppercase text-slate-500">{label}</span><strong className="mt-1 block text-base">{value}</strong>{extra && <span className="text-xs text-slate-500">{extra}</span>}</div>)}</div>
  </header>;
}
export function AgentPerformance({ agent, writable, index }: { agent: Agent; writable: boolean; index: number }) {
  const p = agent.performance; const input = agent.compensation; const salary = agent.salary;
  return <article className="rounded-2xl border border-slate-200 bg-white p-4 sm:p-5 dark:border-slate-700 dark:bg-slate-900">
    <header className="flex items-center gap-3 border-b border-slate-100 pb-4 dark:border-slate-700"><span className={`rounded-full p-3 ${index % 2 ? 'bg-emerald-50 text-emerald-600' : 'bg-blue-50 text-blue-600'}`}><UserRound size={22} /></span><div><h4 aria-label={agentLabel(agent)} className="text-lg font-bold">{agent.display_name || agent.agent_code}</h4><p className="text-xs text-slate-500">COD {agent.agent_code}</p></div></header>
    <h5 className="mt-4 flex items-center gap-2 text-sm font-bold"><TrendingUp size={17} className="text-blue-500" />Performanță</h5>
    <Metrics values={[[ 'Target personal', grileMoney(p?.target ?? agent.home_target)], ['Zile programate', p?.scheduled_days ?? agent.home_work_days], ['Progres', percent(p?.progress)], ['Realizat', grileMoney(p?.sales ?? agent.home_sales)], ['Medie / zi', grileMoney(p?.average)], ['Forecast vânzări', grileMoney(p?.forecast)], ['Zile lucrate', p?.worked_days ?? 0], ['CO', p?.leave_days ?? 0], ['Suplimentar', p?.supplemental_days ?? 0]]} />
    <div className="border-y border-slate-100 py-3 dark:border-slate-700"><h5 className="flex items-center gap-2 text-sm font-bold"><Target size={17} className="text-blue-500" />Daily necesar pentru prag</h5><Metrics values={[[ '80%', grileMoney(p?.daily_80)], ['100%', grileMoney(p?.daily_100)], ['120%', grileMoney(p?.daily_120)]]} /></div>
    <h5 className="mt-4 flex items-center gap-2 text-sm font-bold"><Wallet size={17} className="text-blue-500" />Salariu — detaliere și proiecție</h5>
    <Metrics values={[[ 'Salariu bază', grileMoney(input?.salary_base)], ['Tichete masă', grileMoney(input?.vouchers)], ['Comision accesorii', grileMoney(agent.home_commission)], ['SIM', grileMoney(salary?.sim_pay)], ['E-pay <50 lei · cant.', input?.epay_under_50 == null ? 'De completat' : `${input.epay_under_50} buc.`], ['E-pay ≥50 lei · cant.', input?.epay_over_50 == null ? 'De completat' : `${input.epay_over_50} buc.`]]} />
    <div className="rounded-xl bg-blue-50 px-3 dark:bg-blue-950/40"><Metrics values={[[ 'Total salariu curent', grileMoney(salary?.current_total)], ['Forecast salariu', grileMoney(salary?.forecast_total)], ['Potențial la 120%', grileMoney(salary?.potential_120)]]} /></div>
    <Metrics values={[[ 'Incentive', grileMoney(input?.incentive)], ['Comision total curent', grileMoney(salary?.commission_total)], ['Total suplimentar', grileMoney(agent.supplemental_pay)], ['Comision alte locații', grileMoney(agent.away_commission)], ['E-pay · plată', grileMoney(salary?.epay_pay)], ['Corecții', grileMoney(input?.adjustment)]]} />
    {salary?.current_total == null && <p className="text-xs text-amber-700">Totalul este disponibil după completarea componentelor și rezolvarea eventualelor date lipsă.</p>}
    {input && <CompensationEditor key={`${agent.agent_code}-${input.revision}`} value={input} writable={writable} />}
  </article>;
}
