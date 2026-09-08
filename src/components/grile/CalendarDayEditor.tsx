import { useState } from 'react';
import type { CalendarData, CalendarStore } from '../../api/grileCalendar';
import { dayChanges, dayLabels } from './calendarModel';
import type { RetailCalendarDayInput } from '../../api/generated/contracts';

export function CalendarDayEditor({ data, store, stores, date, busy, writable, onSave }: {
  data: CalendarData; store: CalendarStore; stores: CalendarStore[]; date: string;
  busy: boolean; writable: boolean; onSave: (days: RetailCalendarDayInput[]) => void;
}) {
  const [snapshot] = useState(data);
  const occupant = snapshot.days.find(d => d.work_date === date && d.site_code === store.site_code && d.status === 'work');
  const [code, setCode] = useState(occupant?.agent_code ?? '');
  const [status, setStatus] = useState<RetailCalendarDayInput['status']>('work');
  const [supplemental, setSupplemental] = useState(occupant?.supplemental ?? false);
  const roster = snapshot.roster.filter(r => r.active && (r.home_site_code === store.site_code || stores.some(s => s.site_code === r.home_site_code && s.regional === store.regional && Boolean(s.regional))));
  const selected = snapshot.roster.find(r => r.agent_code === code);
  const existing = snapshot.days.find(d => d.work_date === date && d.agent_code === code);
  const away = Boolean(selected && selected.home_site_code !== store.site_code);
  const elsewhere = existing && existing.status !== 'cancelled' && existing.site_code !== store.site_code;
  const blocked = !code || busy || !writable || Boolean(elsewhere) || (away && (status === 'leave' || status === 'off')) || (status === 'cancelled' && !existing);
  return <form className="space-y-3 rounded-xl bg-slate-50 p-4 dark:bg-slate-800" onSubmit={e => { e.preventDefault(); if (!blocked) onSave(dayChanges(snapshot, { work_date: date, agent_code: code, site_code: store.site_code, status, supplemental: status === 'work' && (away || supplemental) })); }}>
    <h4 className="font-semibold">Program pentru {date}</h4>
    <label className="block">Agent<select aria-label="Agent pentru zi" className="ml-2 rounded border p-2 dark:bg-slate-900" value={code} onChange={e => setCode(e.target.value)}><option value="">Alege agentul</option>{roster.map(r => <option key={r.agent_code} value={r.agent_code}>{r.agent_code}{r.home_site_code === store.site_code ? '' : ` · suplimentar din ${r.home_site_code}`}</option>)}</select></label>
    {existing && <p>Înregistrare actuală: {dayLabels[existing.status]} · {existing.site_code}</p>}
    <label className="block">Tip zi<select aria-label="Tip zi" className="ml-2 rounded border p-2 dark:bg-slate-900" value={status} onChange={e => setStatus(e.target.value as typeof status)}>{Object.entries(dayLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
    {status === 'work' && <label className="block"><input type="checkbox" checked={away || supplemental} disabled={away} onChange={e => setSupplemental(e.target.checked)} /> Suplimentar</label>}
    {elsewhere && <p role="alert">Agentul are deja o zi în {existing.site_code}. Corectează întâi programul de acolo.</p>}
    {occupant && occupant.agent_code !== code && status === 'work' && <p>Salvarea înlocuiește alocarea lui {occupant.agent_code} pentru această zi.</p>}
    {away && (status === 'leave' || status === 'off') && <p>Concediul și zilele libere se editează la magazinul de bază.</p>}
    <button disabled={blocked} className="rounded-lg bg-indigo-600 px-4 py-2 text-white disabled:opacity-40">{busy ? 'Se salvează…' : 'Salvează ziua'}</button>
  </form>;
}
