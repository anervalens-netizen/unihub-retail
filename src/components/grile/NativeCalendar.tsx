import { useEffect, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '../../auth/AuthContext';
import { canAccessManagement, canWriteBusinessData } from '../../auth/permissions';
import { ApiError, getApiErrorMessage } from '../../api/client';
import { downloadAttendance, calendarCandidates, calendarStores, confirmCalendarAgent, readCalendar, saveCalendarDays, type CalendarData, type CalendarStore } from '../../api/grileCalendar';
import type { RetailCalendarDayInput } from '../../api/generated/contracts';
import { getCurrentYearMonth } from '../../lib/dates';
import { Earnings } from './Earnings';
import { Attendance } from './Attendance';
import { StoreHoursEditor } from './StoreHoursEditor';
import { CalendarDayEditor } from './CalendarDayEditor';
import { dayLabels, monthDays } from './calendarModel';

export function NativeCalendar({ initialMonth }: { initialMonth?: string }) {
  const { user } = useAuth();
  const [month, setMonth] = useState(initialMonth || getCurrentYearMonth());
  if (!canAccessManagement(user?.profile)) return <p>Calendarul este disponibil echipei de management.</p>;
  return <section className="space-y-4"><label>Luna programului <input aria-label="Luna programului" type="month" value={month} min="2000-01" max="2100-12" onChange={e => { if (/^(20\d{2}|2100)-(0[1-9]|1[0-2])$/.test(e.target.value)) setMonth(e.target.value); }} className="rounded border p-2 dark:bg-slate-900" /></label><CalendarMonth key={month} month={month} writable={canWriteBusinessData(user?.profile)} /></section>;
}

function CalendarMonth({ month, writable }: { month: string; writable: boolean }) {
  const [selected, setSelected] = useState<CalendarStore | null>(null);
  const stores = useQuery({ queryKey: ['calendar-stores'], queryFn: ({ signal }) => calendarStores(signal) });
  const calendar = useQuery({ queryKey: ['native-calendar', month], queryFn: ({ signal }) => readCalendar(month, signal) });
  const download = useMutation({ mutationFn: () => downloadAttendance(month, calendar.data?.projection_revision ?? '') });
  if (stores.isError || calendar.isError) return <div role="alert">Calendarul nu poate fi încărcat. <button onClick={() => { void stores.refetch(); void calendar.refetch(); }}>Reîncarcă</button></div>;
  if (!stores.data || !calendar.data) return <p role="status">Se încarcă programul…</p>;
  const eligible: CalendarStore[] = stores.data.filter(s => !/^TR /i.test(s.locatie) && s.site_code !== 'Cartele');
  const referenced = new Set([...calendar.data.days.map(d => d.site_code), ...calendar.data.roster.map(r => r.home_site_code)]);
  for (const site_code of referenced) {
    if (!eligible.some(s => s.site_code === site_code)) eligible.push({ site_code, locatie: `${site_code} · doar corectări`, firma: '', regional: 'Magazine indisponibile — corectări', asm: '', cleanupOnly: true });
  }
  const managers = [...new Set(eligible.map(s => s.regional))].sort();
  return <div className="space-y-4">
    <p className="text-sm text-slate-500">Program confirmat de manager · un agent pe magazin și zi. V1 rămâne grila oficială.</p>
    <button disabled={download.isPending || calendar.isFetching || !calendar.data.roster.length} onClick={() => download.mutate()} className="rounded border px-3 py-2">Descarcă pontajele ZIP (provizoriu)</button>
    <p className="text-sm text-slate-500">Include toate magazinele din programul lunii, câte un Excel per magazin.</p>
    {download.isError && <p role="alert">Exportul nu a reușit. Reîncarcă programul înainte de a încerca din nou. <button onClick={() => void calendar.refetch()}>Reîncarcă pontajele</button></p>}
    {managers.map(manager => <section key={manager} className="rounded-xl border p-4"><h3 className="mb-3 font-semibold">{manager || 'Fără manager'}</h3><div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{eligible.filter(s => s.regional === manager).map(store => <button key={store.site_code} onClick={() => setSelected(store)} className="rounded-xl border bg-white p-4 text-left hover:border-indigo-500 dark:bg-slate-900"><strong className="block">{store.locatie}</strong><span className="text-sm text-slate-500">{store.site_code} · {store.firma}</span><span className="mt-2 block text-sm">{calendar.data.days.filter(d => d.site_code === store.site_code && d.status === 'work').length} zile programate</span></button>)}</div></section>)}
    {!eligible.length && <p>Nu există magazine active disponibile.</p>}
    {selected && <StoreCalendar key={selected.site_code} month={month} store={selected} stores={eligible} data={calendar.data} refreshing={calendar.isFetching} writable={writable} onClose={() => setSelected(null)} />}
  </div>;
}

function StoreCalendar({ month, store, stores, data, refreshing, writable, onClose }: { month: string; store: CalendarStore; stores: CalendarStore[]; data: CalendarData; refreshing: boolean; writable: boolean; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [tab, setTab] = useState('Calendar');
  const [date, setDate] = useState('');
  const [editVersion, setEditVersion] = useState(0);
  const [rosterPending, setRosterPending] = useState(false);
  const [hoursPending, setHoursPending] = useState(false);
  const cache = useQueryClient();
  useEffect(() => { const element = dialog.current!; element.showModal(); return () => element.close(); }, []);
  const save = useMutation({ mutationFn: (days: RetailCalendarDayInput[]) => saveCalendarDays(month, days), onSuccess: async () => { await cache.invalidateQueries({ queryKey: ['native-calendar', month] }); setDate(''); } });
  const refresh = async () => { await cache.invalidateQueries({ queryKey: ['native-calendar', month] }); save.reset(); setEditVersion(v => v + 1); };
  return <dialog ref={dialog} aria-labelledby="calendar-store-title" onCancel={onClose} onClose={onClose} className="m-auto max-h-[90vh] w-[min(1100px,95vw)] overflow-auto rounded-2xl bg-white p-5 text-slate-900 shadow-xl backdrop:bg-slate-950/50 dark:bg-slate-900 dark:text-slate-100">
    <header className="mb-4 flex items-center justify-between gap-4"><div><h2 id="calendar-store-title" className="text-xl font-bold">{store.locatie}</h2><p>{month} · {store.site_code}</p></div><button aria-label="Închide magazinul" onClick={onClose} className="rounded border px-3 py-2">Închide</button></header>
    <StoreHoursEditor key={`${store.site_code}-${data.store_hours?.find(h => h.site_code === store.site_code)?.revision ?? 0}`} month={month} site={store.site_code} data={data} disabled={refreshing || save.isPending || rosterPending || hoursPending} writable={writable && !store.cleanupOnly} onPendingChange={setHoursPending} />
    <nav aria-label="Secțiuni magazin" className="mb-4 flex gap-2">{['Grile', 'Calendar', 'Pontaj'].map(label => <button key={label} aria-pressed={tab === label} onClick={() => setTab(label)} className={`rounded-lg px-4 py-2 ${tab === label ? 'bg-indigo-600 text-white' : 'border'}`}>{label}</button>)}</nav>
    {tab === 'Grile' && <Earnings month={month} site={store.site_code} calendarRevision={data.projection_revision} />}
    {tab === 'Pontaj' && <Attendance data={data} store={store} />}
    {tab === 'Calendar' && <div className="space-y-4">{store.cleanupOnly ? <p>Magazin indisponibil pentru programări noi. Poți consulta și anula zilele existente.</p> : <Roster month={month} store={store} data={data} writable={writable && !save.isPending && !hoursPending} onPendingChange={setRosterPending} onChanged={() => { setDate(''); }} />}<MonthGrid month={month} store={store} data={data} disabled={refreshing || save.isPending || rosterPending || hoursPending} onSelect={d => { setDate(d); save.reset(); }} />{save.isError && <div role="alert">{save.error instanceof ApiError && save.error.status === 409 ? 'Programul s-a schimbat sau există un conflict. Reîncarcă înainte de o nouă editare.' : getApiErrorMessage(save.error, 'Salvarea a eșuat.')} <button onClick={() => void refresh()}>Reîncarcă programul</button></div>}{date && <CalendarDayEditor key={`${date}-${editVersion}-${data.roster.map(r => `${r.agent_code}:${r.revision}`).join('|')}`} date={date} store={store} stores={stores} data={data} writable={writable && !hoursPending && !refreshing && !rosterPending && !save.isError && !save.isSuccess} busy={save.isPending} onSave={days => save.mutate(days)} />}</div>}
  </dialog>;
}

function MonthGrid({ month, store, data, disabled, onSelect }: { month: string; store: CalendarStore; data: CalendarData; disabled: boolean; onSelect: (date: string) => void }) {
  const { dates, offset } = monthDays(month);
  return <div className="overflow-x-auto"><div className="grid min-w-[580px] grid-cols-7 gap-2">{['Lun', 'Mar', 'Mie', 'Joi', 'Vin', 'Sâm', 'Dum'].map(d => <div key={d} className="p-2 text-center text-sm text-slate-500">{d}</div>)}{Array.from({ length: offset }, (_, i) => <div key={`empty-${i}`} />)}{dates.map(date => {
    const entries = data.days.filter(d => d.work_date === date && d.site_code === store.site_code && d.status !== 'cancelled');
    const worker = entries.find(d => d.status === 'work');
    return <button key={date} aria-label={`Editează ${date}`} disabled={disabled || (store.cleanupOnly && entries.length === 0)} onClick={() => onSelect(date)} className={`min-h-24 rounded-xl border p-2 text-left hover:border-indigo-500 ${worker ? 'bg-indigo-50 dark:bg-indigo-950' : ''}`}><span className="block font-bold">{Number(date.slice(-2))}</span>{!worker && <span className="block text-xs text-slate-500">Nealocat</span>}{entries.map(d => <span key={d.agent_code} className="block text-xs">{d.agent_code} · {dayLabels[d.status]}{d.supplemental ? ' (supl.)' : ''}</span>)}</button>;
  })}</div></div>;
}

function Roster({ month, store, data, writable, onChanged, onPendingChange }: { month: string; store: CalendarStore; data: CalendarData; writable: boolean; onChanged: () => void; onPendingChange: (pending: boolean) => void }) {
  const [selection, setSelection] = useState({ code: '', revision: 0, active: true });
  const { code, revision, active } = selection;
  const cache = useQueryClient();
  const candidates = useQuery({ queryKey: ['calendar-candidates', month], queryFn: ({ signal }) => calendarCandidates(month, signal), enabled: writable });
  const confirm = useMutation({ onMutate: () => onPendingChange(true), onSettled: () => onPendingChange(false), onError: async () => { onChanged(); await cache.invalidateQueries({ queryKey: ['native-calendar', month] }); }, mutationFn: () => confirmCalendarAgent(month, code, { home_site_code: store.site_code, active, expected_revision: revision }), onSuccess: async () => { onChanged(); await cache.invalidateQueries({ queryKey: ['native-calendar', month] }); setSelection({ code: '', revision: 0, active: true }); } });
  const available = candidates.data?.filter(c => !data.roster.some(r => r.agent_code === c.agent_code)) ?? [];
  if (!writable) return <p>Mod consultare.</p>;
  return <details className="rounded-xl border p-3"><summary className="cursor-pointer font-semibold">Confirmă agenții și magazinul de bază</summary><p className="my-2 text-sm">Selectează explicit agentul activ. Absența vânzărilor nu înseamnă că a plecat.</p>{candidates.isError && <p role="alert">Catalogul nu poate fi încărcat. <button onClick={() => void candidates.refetch()}>Reîncarcă agenții</button></p>}<label>Cod agent <select aria-label="Cod agent pentru confirmare" disabled={confirm.isPending} value={code} onChange={e => { const row = data.roster.find(r => r.agent_code === e.target.value); setSelection({ code: e.target.value, revision: row?.revision ?? 0, active: row?.active ?? true }); confirm.reset(); }} className="rounded border p-2 dark:bg-slate-900"><option value="">Alege agentul</option>{data.roster.map(r => <option key={r.agent_code} value={r.agent_code}>{r.agent_code} · confirmat în {r.home_site_code}{r.active ? '' : ' · inactiv'}</option>)}{available.map(c => <option key={c.agent_code} value={c.agent_code}>{c.agent_code} · {c.site_codes.join(', ')}{c.needs_active_confirmation ? ' · fără vânzări curente' : ''}</option>)}</select></label><label className="ml-3"><input type="checkbox" disabled={confirm.isPending} checked={active} onChange={e => setSelection(s => ({ ...s, active: e.target.checked }))} /> Activ în această lună</label>{revision > 0 && <p className="my-2 text-sm">Corectare agent confirmat: magazinul de bază devine {store.locatie}. Pentru mutare sau dezactivare, anulează întâi zilele confirmate.</p>}<button className="ml-2 rounded bg-indigo-600 p-2 text-white disabled:opacity-40" disabled={!code || confirm.isPending || candidates.isFetching} onClick={() => confirm.mutate()}>Confirmă în {store.locatie}</button>{confirm.isError && <p role="alert">{getApiErrorMessage(confirm.error, 'Confirmarea a eșuat. Reîncarcă programul.')} <button onClick={async () => { await cache.invalidateQueries({ queryKey: ['native-calendar', month] }); setSelection({ code: '', revision: 0, active: true }); confirm.reset(); }}>Reîncarcă agenții confirmați</button></p>}</details>;
}
