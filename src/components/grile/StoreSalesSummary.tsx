import type { readEarnings } from '../../api/grileCalendar';

export function StoreSalesSummary({ data, site }: { data: Awaited<ReturnType<typeof readEarnings>>; site: string }) {
  const worked = data.agents.flatMap(agent => agent.days.filter(day => day.site_code === site).map(day => ({ ...day, agent_code: agent.agent_code })));
  const elapsed = worked.filter(day => day.issue !== 'after_cutoff');
  const unassigned = data.unassigned_sales.filter(day => day.site_code === site);
  const missing = !data.cutoff || elapsed.some(day => day.sales === null);
  const values = [...elapsed, ...unassigned];
  const total = values.reduce((sum, day) => sum + Math.round(Number(day.sales ?? 0) * 100), 0) / 100;
  const visitors = elapsed.filter(day => day.away);
  return <div className="rounded-2xl bg-indigo-50 p-4 dark:bg-indigo-950">
    <h4 className="font-semibold">Vânzări totale magazin · inclusiv suplimentari</h4>
    <p className="mt-1 text-xl font-bold">{missing ? 'Indisponibil — lipsesc date' : `${total.toLocaleString('ro-RO', { maximumFractionDigits: 2 })} lei`}</p>
    <p className="mt-1 text-sm">Vânzarea rămâne la magazinul lucrat, indiferent de baza agentului. Sunt incluse și vânzările încă nealocate.</p>
    {visitors.length > 0 && <ul className="mt-2 text-sm">{visitors.map(day => <li key={`${day.agent_code}-${day.work_date}`}>{day.agent_code} · {day.work_date}: {day.sales === null ? 'Indisponibil' : `${Number(day.sales).toLocaleString('ro-RO')} lei`}</li>)}</ul>}
  </div>;
}
