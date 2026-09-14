import { useId, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '../../auth/AuthContext';
import { canAccessManagement, canWriteBusinessData } from '../../auth/permissions';
import { calendarStores, readCalendar, calendarCandidates, saveStoreTeam, type CalendarData, type CalendarStore } from '../../api/grileCalendar';
import { getApiErrorMessage } from '../../api/client';
import { agentLabel, monthDays } from './calendarModel';
import { homeOn, rosterDate } from './rosterHistory';
import './nativeCalendar.css';

export function TeamAssignments({ month }: { month: string }) {
  const { user } = useAuth();
  if (!canAccessManagement(user?.profile)) return null;
  return <Assignments key={month} month={month} writable={canWriteBusinessData(user?.profile)} />;
}
function Assignments({ month, writable }: { month: string; writable: boolean }) {
  const [search, setSearch] = useState('');
  const [region, setRegion] = useState('');
  const [date, setDate] = useState(rosterDate(month) > (monthDays(month).dates.at(-1) ?? '') ? monthDays(month).dates.at(-1)! : rosterDate(month));
  const [selected, setSelected] = useState('');
  const stores = useQuery({ queryKey: ['calendar-stores'], queryFn: ({ signal }) => calendarStores(signal) });
  const calendar = useQuery({ queryKey: ['native-calendar', month], queryFn: ({ signal }) => readCalendar(month, signal) });
  if (stores.isError || calendar.isError) return <p role="alert">Alocările nu pot fi încărcate. <button onClick={() => { void stores.refetch(); void calendar.refetch(); }}>Reîncarcă</button></p>;
  if (!stores.data || !calendar.data) return <p>Se încarcă alocările confirmate…</p>;
  const data = calendar.data;
  const physical = stores.data.filter(s => !['Cartele', 'TL'].includes(s.site_code) && !/^TR /i.test(s.locatie));
  const normalize = (s: string) => s.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase('ro');
  const rows = physical.filter(s => (!region || s.regional === region) && normalize(`${s.locatie} ${s.site_code} ${s.regional} ${data.roster.filter(r => homeOn(r, date) === s.site_code).map(agentLabel).join(' ')}`).includes(normalize(search)));
  return <section className="native-calendar glass rounded-xl p-3" aria-label="Magazine și agenți alocați">
    <div className="flex flex-wrap items-center justify-between gap-2"><h3 className="font-bold">Magazine și agenți alocați</h3><span className="text-xs text-slate-500">{month} · alocări confirmate</span></div>
    <div className="my-2 grid gap-2 sm:grid-cols-3"><label className="native-label">Caută magazin sau agent<input className="native-field" type="search" value={search} onChange={e => setSearch(e.target.value)} /></label><label className="native-label">Manager<select className="native-field" value={region} onChange={e => setRegion(e.target.value)}><option value="">Toți managerii</option>{[...new Set(physical.map(s => s.regional))].sort().map(r => <option key={r}>{r}</option>)}</select></label><label className="native-label">Alocări valabile la<input className="native-field" type="date" min={`${month}-01`} max={monthDays(month).dates.at(-1)} value={date} onChange={e => { if (e.target.value.startsWith(month)) setDate(e.target.value); }} /></label></div>
    <div className="max-h-[440px] overflow-auto"><table className="w-full text-left text-sm"><thead className="sticky top-0"><tr><th className="p-2">Magazin</th><th>Agenți de bază</th><th><span className="sr-only">Acțiuni</span></th></tr></thead><tbody>{rows.map(store => {
      const agents = data.roster.filter(r => r.active && homeOn(r, date) === store.site_code);
      return <tr key={store.site_code}><td className="p-2"><strong>{store.locatie}</strong><span className="block text-xs text-slate-500">{store.firma} · {store.regional}</span></td><td>{agents.length ? agents.map(r => <div key={r.agent_code}>{agentLabel(r)}</div>) : <span className="text-amber-700">Alocare neconfirmată</span>}</td><td>{writable && <button className="native-secondary" onClick={() => setSelected(store.site_code)}>Editează</button>}</td></tr>;
    })}</tbody></table></div>
    {data.roster.some(r => r.active && homeOn(r, date) === 'UNASSIGNED') && <p className="my-2 text-sm text-amber-800">Fără magazin alocat: {data.roster.filter(r => r.active && homeOn(r, date) === 'UNASSIGNED').map(agentLabel).join(', ')}</p>}
    {selected && <AssignmentEditor key={`${selected}-${data.projection_revision}`} month={month} date={date} data={data} stores={physical} site={selected} onClose={() => setSelected('')} />}
  </section>;
}

const normalize = (s: string) => s.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase('ro');
type Choice = { agent_code: string; display_name?: string | null; detail?: string };
export function AgentSelect({ label, value, options, disabled, onChange }: { label: string; value: string; options: Choice[]; disabled?: boolean; onChange: (code: string) => void }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const id = useId();
  const button = useRef<HTMLButtonElement>(null);
  const visible = options.filter(r => normalize(`${agentLabel(r)} ${r.detail ?? ''}`).includes(normalize(query)));
  const selected = options.find(r => r.agent_code === value);
  const choose = (code: string) => { onChange(code); setOpen(false); button.current?.focus(); };
  return <div className="relative" onBlur={e => { if (!e.currentTarget.contains(e.relatedTarget)) setOpen(false); }}>
    <span id={`${id}-label`} className="native-label">{label}</span>
    <button ref={button} type="button" role="combobox" aria-labelledby={`${id}-label`} aria-expanded={open} aria-controls={open ? id : undefined} aria-haspopup="listbox" disabled={disabled} className="native-field flex w-full items-center justify-between text-left" onClick={() => { setQuery(''); setOpen(!open); }} onKeyDown={e => { if (e.key.length === 1 && !e.ctrlKey && !e.metaKey) { e.preventDefault(); setQuery(e.key); setOpen(true); } if (e.key === 'ArrowDown') { e.preventDefault(); setQuery(''); setOpen(true); } }}>
      <span>{selected ? agentLabel(selected) : 'Alege agentul'}</span><span aria-hidden="true">▾</span>
    </button>
    {open && <div className="absolute left-0 right-0 top-full z-50 rounded-lg border border-indigo-200 bg-white p-1 shadow-xl" onKeyDown={e => { if (e.key === 'Escape') { e.preventDefault(); setOpen(false); button.current?.focus(); } }}>
      <input autoFocus aria-label={`Filtrează ${label}`} className="native-field mb-1 w-full" placeholder="Scrie numele sau codul…" value={query} onChange={e => setQuery(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && visible[0]) { e.preventDefault(); choose(visible[0].agent_code); } if (e.key === 'ArrowDown') { e.preventDefault(); e.currentTarget.parentElement?.querySelector<HTMLButtonElement>('[role=option]')?.focus(); } }} />
      <div id={id} role="listbox" aria-label={label} className="max-h-56 overflow-auto">{visible.map(r => <button type="button" role="option" aria-selected={r.agent_code === value} key={r.agent_code} className="block w-full rounded px-2 py-1.5 text-left text-sm hover:bg-indigo-50 focus:bg-indigo-50" onClick={() => choose(r.agent_code)} onKeyDown={e => { if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); const next = e.key === 'ArrowDown' ? e.currentTarget.nextElementSibling : e.currentTarget.previousElementSibling; (next as HTMLElement | null)?.focus(); } }}><strong>{agentLabel(r)}</strong>{r.detail && <span className="block text-xs text-slate-500">{r.detail}</span>}</button>)}{!visible.length && <p className="p-2 text-sm">Niciun agent găsit.</p>}</div>
    </div>}
  </div>;
}
function AssignmentEditor({ month, date, data, stores, site, onClose }: { month: string; date: string; data: CalendarData; stores: CalendarStore[]; site: string; onClose: () => void }) {
  const initial = data.roster.filter(r => r.active && homeOn(r, date) === site);
  const [codes, setCodes] = useState([initial[0]?.agent_code ?? '', initial[1]?.agent_code ?? '']);
  const [from, setFrom] = useState(date);
  const [activation, setActivation] = useState('');
  const cache = useQueryClient();
  const candidates = useQuery({ queryKey: ['calendar-candidates', month], queryFn: ({ signal }) => calendarCandidates(month, signal) });
  const all = [...data.roster.filter(r => r.active && r.home_site_code !== 'TL'), ...(candidates.data ?? []).filter(c => !data.roster.some(r => r.agent_code === c.agent_code))];
  const options = all.map(r => ({ ...r, detail: 'home_site_code' in r ? stores.find(s => s.site_code === homeOn(r, from))?.locatie ?? 'Fără magazin alocat' : 'De confirmat' })).sort((a, b) => Number(initial.some(r => r.agent_code === b.agent_code)) - Number(initial.some(r => r.agent_code === a.agent_code)) || agentLabel(a).localeCompare(agentLabel(b), 'ro'));
  const outgoing = data.roster.filter(r => r.active && homeOn(r, from) === site && !codes.includes(r.agent_code));
  const save = useMutation({ mutationFn: () => saveStoreTeam(month, site, { agent_codes: codes, effective_from: from, location_code_active_from: activation || null, expected_revision: data.projection_revision }), onSuccess: async () => { await cache.invalidateQueries({ queryKey: ['native-calendar', month] }); await cache.invalidateQueries({ queryKey: ['native-earnings', month] }); onClose(); } });
  return <form className="mt-3 space-y-2 rounded-xl border border-indigo-200 p-3" aria-label="Editează agenții magazinului" onSubmit={e => { e.preventDefault(); save.mutate(); }}>
    <div className="flex justify-between"><strong>{stores.find(s => s.site_code === site)?.locatie} · Alocare agenți</strong><button type="button" disabled={save.isPending} onClick={onClose}>Închide</button></div>
    <div className="grid gap-2 sm:grid-cols-2">{[0, 1].map(index => <AgentSelect key={index} label={`Agent ${index + 1}`} value={codes[index] ?? ''} options={options.filter(r => r.agent_code !== codes[1 - index])} disabled={save.isPending} onChange={code => setCodes(codes.map((old, i) => i === index ? code : old))} />)}
      <label className="native-label">Alocare efectivă de la<input required className="native-field" type="date" min={`${month}-01`} max={monthDays(month).dates.at(-1)} value={from} onChange={e => { setFrom(e.target.value); if (e.target.value) { const pair = data.roster.filter(r => r.active && homeOn(r, e.target.value) === site); setCodes([pair[0]?.agent_code ?? '', pair[1]?.agent_code ?? '']); } }} /></label>
      <label className="native-label">Cod locație activ din · opțional<input className="native-field" type="date" min={from} value={activation} onChange={e => setActivation(e.target.value)} /></label>
    </div>
    <p className="text-xs text-slate-500">Cei doi agenți se salvează împreună. Data alocării este independentă de activarea codului de locație. Zilele deja programate își păstrează locația.</p>
    {outgoing.length > 0 && <p className="text-xs text-amber-800">Fără magazin de bază de la {from}: {outgoing.map(agentLabel).join(', ')}. Îi poți aloca apoi unui alt magazin; istoricul rămâne păstrat.</p>}
    {candidates.isError && <p role="alert">Catalogul agenților noi nu poate fi încărcat. <button type="button" onClick={() => void candidates.refetch()}>Reîncarcă</button></p>}
    <button className="native-primary" disabled={codes.some(c => !c) || codes[0] === codes[1] || save.isPending || Boolean(activation && activation < from)}>{save.isPending ? 'Se salvează…' : 'Salvează cei doi agenți'}</button>
    {save.isError && <p role="alert">{getApiErrorMessage(save.error, 'Alocarea s-a schimbat. Reîncarcă înainte de a salva.')} <button type="button" onClick={() => void cache.invalidateQueries({ queryKey: ['native-calendar', month] })}>Reîncarcă</button></p>}
  </form>;
}
