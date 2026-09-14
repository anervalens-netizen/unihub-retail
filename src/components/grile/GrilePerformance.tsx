import { Target, UserRound, Wallet } from 'lucide-react';
import type { CalendarStore, readEarnings } from '../../api/grileCalendar';
import { agentLabel } from './calendarModel';
import { CompensationEditor } from './CompensationEditor';
import { AgentTargetEditor } from './AgentTargetEditor';
type Agent = Awaited<ReturnType<typeof readEarnings>>['agents'][number];
export const grileMoney = (value: string | number | null | undefined) => value == null ? 'Indisponibil' : `${Number(value).toLocaleString('ro-RO', { maximumFractionDigits: 0 })} lei`;
const percent = (value: string | number | null | undefined) => value == null ? '—' : `${Number(value).toLocaleString('ro-RO', { maximumFractionDigits: 1 })}%`;
function Metrics({ values }: { values: [string, import('react').ReactNode][] }) {
  return <dl className="grile-metrics">{values.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>;
}
export function StorePerformance({ data, store }: { data: Awaited<ReturnType<typeof readEarnings>>; store: CalendarStore }) {
  const p = data.stores?.[store.site_code];
  return <header className="grile-store-summary">
    <div className="flex items-center justify-between gap-2 text-xs"><strong>Performanță magazin</strong><span className="text-slate-500">Vânzări până la {data.cutoff ?? 'dată indisponibilă'}</span></div>
    <dl className="mt-1 grid grid-cols-2 gap-x-3 gap-y-1 sm:grid-cols-5">{[
      ['Target', grileMoney(p?.target), ''], ['Realizat', grileMoney(p?.sales), percent(p?.progress)], ['Forecast', grileMoney(p?.forecast), percent(p?.forecast_progress)], ['Zilnic 90%', grileMoney(p?.daily_90), ''], ['Zilnic 100%', grileMoney(p?.daily_100), ''],
    ].map(([label, value, extra]) => <div key={label}><dt className="text-[11px] text-slate-500">{label}</dt><dd className="flex flex-wrap items-baseline gap-x-2 text-sm font-bold">{value}{extra && <span className="text-[11px] font-normal text-slate-500">{extra}</span>}</dd></div>)}</dl>
  </header>;
}
export function AgentPerformance({ agent, writable, index }: { agent: Agent; writable: boolean; index: number }) {
  const p = agent.performance; const input = agent.compensation; const salary = agent.salary;
  return <article className="grile-agent-card rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-900">
    <header className="flex items-center gap-2 border-b border-slate-100 pb-2 dark:border-slate-700"><span className={`rounded-full p-2 ${index % 2 ? 'bg-emerald-50 text-emerald-600' : 'bg-blue-50 text-blue-600'}`}><UserRound size={18} /></span><div><h4 aria-label={agentLabel(agent)} className="text-base font-bold">{agent.display_name || agent.agent_code}</h4><p className="text-[10px] text-slate-500">COD {agent.agent_code}</p></div></header>
    <div className="grile-day-counts"><span>Programate <b>{p?.scheduled_days ?? agent.home_work_days}</b></span><span>Lucrate <b>{p?.worked_days ?? 0}</b></span><span>CO <b>{p?.leave_days ?? 0}</b></span><span>Suplimentare <b>{p?.supplemental_days ?? 0}</b></span></div>
    <Metrics values={[[ 'Target agent', <AgentTargetEditor key={`${agent.agent_code}-${agent.target_setting?.revision ?? 0}`} agent={agent} writable={writable} />], ['Realizat', grileMoney(p?.sales ?? agent.home_sales)], ['Progres', percent(p?.progress)], ['Forecast %', percent(p?.forecast_progress)], ['Medie / zi', grileMoney(p?.average)], ['Forecast vânzări', grileMoney(p?.forecast)]]} />
    <div className="grile-thresholds"><span className="grile-daily-label"><Target size={14} /><strong>Daily</strong></span>{[['80%', p?.daily_80], ['100%', p?.daily_100], ['120%', p?.daily_120]].map(([label, value]) => <span key={label}><small>{label}</small><b>{grileMoney(value)}</b></span>)}</div>
    <h5 className="grile-section-title"><Wallet size={14} />Salariu — detaliere și proiecție</h5>
    <Metrics values={[[ 'Salariu bază', grileMoney(input?.salary_base)], ['Tichete masă', grileMoney(input?.vouchers)], ['Comision accesorii', grileMoney(agent.home_commission)], ['SIM', `${grileMoney(salary?.sim_pay)}${input?.sim_quantity != null ? ` · ${input.sim_quantity} buc.` : ''}`]]} />
    {input && <CompensationEditor key={`${agent.agent_code}-${input.revision}`} value={input} writable={writable} />}
    <div className="rounded-lg bg-blue-50 px-2 dark:bg-blue-950/40"><Metrics values={[[ 'Total salariu curent', grileMoney(salary?.current_total)], ['Forecast salariu', grileMoney(salary?.forecast_total)], ['Potențial la 100%', grileMoney(salary?.potential_100)], ['Potențial la 120%', grileMoney(salary?.potential_120)]]} /></div>
    <Metrics values={[[ 'Incentive', grileMoney(input?.incentive)], ['Comision total curent', grileMoney(salary?.commission_total)], ['Total suplimentar', grileMoney(agent.supplemental_pay)], ['Comision alte locații', grileMoney(agent.away_commission)], ['E-pay · plată', grileMoney(salary?.epay_pay)]]} />
    {salary?.current_total == null && <p className="text-xs text-amber-700">Totalul așteaptă datele sursă sau programul complet; câmpurile automate nu se completează manual.</p>}
  </article>;
}
