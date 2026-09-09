import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { getApiErrorMessage } from '../../api/client';
import { saveCalendarDays, type CalendarData, type CalendarStore } from '../../api/grileCalendar';
import { agentLabel, dayChanges, monthDays } from './calendarModel';

export function leaveChanges(data: CalendarData, site: string, code: string, from: string, until: string) {
  const days = monthDays(data.month).dates.filter(date => date >= from && date <= until && ![0, 6].includes(new Date(`${date}T12:00:00Z`).getUTCDay()));
  if (!data.roster.some(r => r.agent_code === code && r.active && r.home_site_code === site)) throw new Error('Alege un agent de bază activ.');
  if (!days.length || from > until || !from.startsWith(data.month) || !until.startsWith(data.month)) throw new Error('Alege un interval valid din luna programului, cu zile luni–vineri.');
  if (days.some(date => data.days.some(d => d.agent_code === code && d.work_date === date && d.status !== 'cancelled' && d.site_code !== site))) throw new Error('Agentul este programat și în alt magazin în acest interval. Corectează întâi acea alocare.');
  return days.flatMap(work_date => dayChanges(data, { work_date, agent_code: code, site_code: site, status: 'leave', supplemental: false }));
}
function leaveIntervals(dates: string[]) {
  const ranges: { from: string; until: string; days: number }[] = [];
  for (const date of dates) {
    const last = ranges.at(-1);
    const working = monthDays(date.slice(0, 7)).dates.filter(d => last && d > last.until && d <= date && ![0, 6].includes(new Date(`${d}T12:00:00Z`).getUTCDay()));
    if (last && working.length <= 1) { last.until = date; last.days += ![0, 6].includes(new Date(`${date}T12:00:00Z`).getUTCDay()) ? 1 : 0; }
    else ranges.push({ from: date, until: date, days: ![0, 6].includes(new Date(`${date}T12:00:00Z`).getUTCDay()) ? 1 : 0 });
  }
  return ranges;
}
export function CalendarExtras({ data, store, stores, writable }: { data: CalendarData; store: CalendarStore; stores: CalendarStore[]; writable: boolean }) {
  const home = data.roster.filter(r => r.home_site_code === store.site_code && r.active);
  const leaves = data.days.filter(d => d.site_code === store.site_code && d.status === 'leave' && home.some(r => r.agent_code === d.agent_code));
  const extras = data.days.filter(d => d.site_code === store.site_code && d.status === 'work' && d.supplemental);
  const cache = useQueryClient(); const [code, setCode] = useState(''); const [from, setFrom] = useState(''); const [until, setUntil] = useState('');
  const save = useMutation({ mutationFn: () => saveCalendarDays(data.month, leaveChanges(data, store.site_code, code, from, until)), onSuccess: async () => { await cache.invalidateQueries({ queryKey: ['native-calendar', data.month] }); setFrom(''); setUntil(''); } });
  const grouped = home.flatMap(agent => leaveIntervals(leaves.filter(d => d.agent_code === agent.agent_code).map(d => d.work_date).sort()).map(range => ({ agent, ...range })));
  return <div className="space-y-5">
    <section className="overflow-hidden rounded-2xl border border-amber-200 dark:border-amber-800"><h4 className="bg-amber-600 px-4 py-3 font-bold text-white">Concedii · agenții magazinului</h4><div className="p-4">
      {!grouped.length ? <p className="text-sm text-slate-500">Nu sunt concedii înregistrate.</p> : <table className="w-full text-left text-sm"><thead><tr><th>Agent</th><th>De la</th><th>Până la</th><th>Zile L–V</th></tr></thead><tbody>{grouped.map(({ agent, from: start, until: end, days }) => <tr key={`${agent.agent_code}-${start}`}><td className="py-2">{agentLabel(agent)}</td><td>{start}</td><td>{end}</td><td>{days}</td></tr>)}</tbody></table>}
      {writable && <form className="mt-4 space-y-3" onSubmit={e => { e.preventDefault(); save.mutate(); }}><div className="grid gap-3 sm:grid-cols-3"><label className="native-label">Agent de bază<select required className="native-field" value={code} onChange={e => setCode(e.target.value)}><option value="">Alege agentul</option>{home.map(r => <option key={r.agent_code} value={r.agent_code}>{agentLabel(r)}</option>)}</select></label><label className="native-label">De la<input required className="native-field" type="date" min={`${data.month}-01`} max={monthDays(data.month).dates.at(-1)} value={from} onChange={e => setFrom(e.target.value)} /></label><label className="native-label">Până la<input required className="native-field" type="date" min={from || `${data.month}-01`} max={monthDays(data.month).dates.at(-1)} value={until} onChange={e => setUntil(e.target.value)} /></label></div><p className="text-xs text-slate-500">Înregistrează concediu luni–vineri. Zilele lucrate ale agentului din acest magazin sunt înlocuite cu concediu; acoperirea magazinului se programează separat.</p><button className="native-primary" disabled={save.isPending}>Salvează concediul</button>{save.isError && <p role="alert">{getApiErrorMessage(save.error, save.error instanceof Error ? save.error.message : 'Salvarea a eșuat.')}</p>}</form>}
    </div></section>
    <section className="overflow-hidden rounded-2xl border border-violet-200 dark:border-violet-800"><h4 className="bg-violet-600 px-4 py-3 font-bold text-white">Suplimentari în această locație</h4><div className="p-4">
      {!extras.length ? <p className="text-sm text-slate-500">Nu sunt zile suplimentare programate.</p> : <div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead><tr><th>Data</th><th>Agent</th><th>Firmă · bază</th><th>Status</th></tr></thead><tbody>{extras.map(d => { const agent = data.roster.find(r => r.agent_code === d.agent_code); const base = stores.find(s => s.site_code === agent?.home_site_code); return <tr key={`${d.work_date}-${d.agent_code}`}><td className="py-2">{d.work_date}</td><td>{agentLabel(agent ?? d)}</td><td>{base ? `${base.firma} · ${base.locatie}` : agent?.home_site_code}</td><td>Programat suplimentar</td></tr>; })}</tbody></table></div>}
      {writable && <SupplementEditor key={data.projection_revision} data={data} stores={stores} fixedStore={store} />}
    </div></section>
  </div>;
}
export function SupplementEditor({ data, stores, fixedStore, fixedAgent }: { data: CalendarData; stores: CalendarStore[]; fixedStore?: CalendarStore; fixedAgent?: string }) {
  const cache = useQueryClient(); const [code, setCode] = useState(fixedAgent ?? ''); const [site, setSite] = useState(fixedStore?.site_code ?? ''); const [date, setDate] = useState(''); const [paid, setPaid] = useState(false);
  const selectedAgent = data.roster.find(r => r.agent_code === code);
  const region = fixedStore?.regional || selectedAgent?.regional || stores.find(s => s.site_code === selectedAgent?.home_site_code)?.regional;
  const candidates = data.roster.filter(r => r.active && (!fixedStore || r.regional === region || stores.some(s => s.site_code === r.home_site_code && s.regional === region)));
  const destinations = stores.filter(s => !s.cleanupOnly && s.regional === region);
  const elsewhere = data.days.find(d => d.agent_code === code && d.work_date === date && d.status !== 'cancelled' && d.site_code !== site);
  const occupant = data.days.find(d => d.site_code === site && d.work_date === date && d.status === 'work' && d.agent_code !== code);
  const save = useMutation({ mutationFn: () => saveCalendarDays(data.month, dayChanges(data, { work_date: date, agent_code: code, site_code: site, status: 'work', supplemental: paid })), onSuccess: async () => { await cache.invalidateQueries({ queryKey: ['native-calendar', data.month] }); await cache.invalidateQueries({ queryKey: ['native-earnings', data.month] }); } });
  return <details className="mt-4 rounded-xl border border-violet-200 p-3 dark:border-violet-800"><summary className="cursor-pointer text-sm font-semibold">Programează o zi suplimentară</summary><form className="mt-3 space-y-3" onSubmit={e => { e.preventDefault(); if (paid && !elsewhere) save.mutate(); }}><div className="grid gap-3 sm:grid-cols-3">
    {!fixedAgent && <label className="native-label">Agent<select required className="native-field" value={code} onChange={e => setCode(e.target.value)}><option value="">Alege persoana</option>{candidates.map(r => <option key={r.agent_code} value={r.agent_code}>{agentLabel(r)}</option>)}</select></label>}
    {!fixedStore && <label className="native-label">Magazin lucrat<select required className="native-field" value={site} onChange={e => setSite(e.target.value)}><option value="">Alege magazinul</option>{destinations.map(s => <option key={s.site_code} value={s.site_code}>{s.firma} · {s.locatie}</option>)}</select></label>}
    <label className="native-label">Data<input required type="date" className="native-field" min={`${data.month}-01`} max={monthDays(data.month).dates.at(-1)} value={date} onChange={e => setDate(e.target.value)} /></label></div>
    <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={paid} onChange={e => setPaid(e.target.checked)} />Confirm zi suplimentară plătită</label>
    {occupant && <p className="text-sm text-amber-700">Această salvare îl înlocuiește pe {agentLabel(data.roster.find(r => r.agent_code === occupant.agent_code) ?? occupant)} în {date}.</p>}
    {elsewhere && <p role="alert" className="text-sm text-rose-700">Persoana este deja programată în {elsewhere.site_code}. Corectează întâi alocarea existentă.</p>}
    <p className="text-xs text-slate-500">Vânzarea fizică a magazinului din această zi va fi atribuită persoanei selectate. Totalul magazinului rămâne același.</p>
    <button className="native-primary" disabled={!code || !site || !date || !paid || Boolean(elsewhere) || save.isPending || save.isSuccess}>Salvează suplimentarul</button>
    {save.isError && <p role="alert">{getApiErrorMessage(save.error, 'Programul s-a schimbat. Reîncarcă înainte de a salva din nou.')} <button type="button" onClick={() => void cache.invalidateQueries({ queryKey: ['native-calendar', data.month] })}>Reîncarcă</button></p>}
  </form></details>;
}
