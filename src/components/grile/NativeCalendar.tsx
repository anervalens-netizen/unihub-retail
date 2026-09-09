import { useEffect, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '../../auth/AuthContext';
import { canAccessManagement, canWriteBusinessData } from '../../auth/permissions';
import { ApiError, getApiErrorMessage } from '../../api/client';
import { downloadAttendance, calendarCandidates, calendarStores, confirmCalendarAgent, readCalendar, saveCalendarDays, type CalendarData, type CalendarStore } from '../../api/grileCalendar';
import type { RetailCalendarDayInput } from '../../api/generated/contracts';
import { getCurrentYearMonth } from '../../lib/dates';
import { Earnings } from './Earnings';
import { TeamLeaderRoster } from './TeamLeaderRoster';
import { Attendance } from './Attendance';
import { StoreHoursEditor } from './StoreHoursEditor';
import { CalendarDayEditor } from './CalendarDayEditor';
import { CalendarDays, X } from 'lucide-react';
import { SegmentedTabs } from '../common/SegmentedTabs';
import { CalendarOverview } from './CalendarOverview';
import './nativeCalendar.css';
import { agentLabel, dayLabels, monthDays } from './calendarModel';

export function NativeCalendar({ initialMonth }: { initialMonth?: string }) {
  const { user } = useAuth();
  const [month, setMonth] = useState(initialMonth || getCurrentYearMonth());
  if (!canAccessManagement(user?.profile)) return <p>Calendarul este disponibil echipei de management.</p>;
  return <section className="native-calendar space-y-4"><div className="flex flex-wrap items-center justify-between gap-3 px-1"><div className="flex items-center gap-2 text-slate-700 dark:text-slate-200"><CalendarDays size={20} className="text-indigo-500" /><h2 className="text-lg font-bold">Program V2</h2></div><label className="native-label">Luna programului<input aria-label="Luna programului" type="month" value={month} min="2000-01" max="2100-12" onChange={e => { if (/^(20\d{2}|2100)-(0[1-9]|1[0-2])$/.test(e.target.value)) setMonth(e.target.value); }} className="native-field" /></label></div><CalendarMonth key={month} month={month} writable={canWriteBusinessData(user?.profile)} /></section>;
}

function CalendarMonth({ month, writable }: { month: string; writable: boolean }) {
  const [selected, setSelected] = useState<CalendarStore | null>(null);
  const stores = useQuery({ queryKey: ['calendar-stores'], queryFn: ({ signal }) => calendarStores(signal) });
  const calendar = useQuery({ queryKey: ['native-calendar', month], queryFn: ({ signal }) => readCalendar(month, signal) });
  const download = useMutation({ mutationFn: () => downloadAttendance(month, calendar.data?.projection_revision ?? '') });
  if (stores.isError || calendar.isError) return <div role="alert" className="glass rounded-2xl p-5 text-sm text-rose-700 dark:text-rose-300">Calendarul nu poate fi încărcat. <button className="native-secondary ml-2" onClick={() => { void stores.refetch(); void calendar.refetch(); }}>Reîncarcă</button></div>;
  if (!stores.data || !calendar.data) return <p role="status" className="glass rounded-2xl p-6 text-sm text-slate-500">Se încarcă programul…</p>;
  const eligible: CalendarStore[] = stores.data.filter(s => !/^TR /i.test(s.locatie) && s.site_code !== 'Cartele');
  const referenced = new Set([...calendar.data.days.map(d => d.site_code), ...calendar.data.roster.map(r => r.home_site_code)]);
  for (const site_code of referenced) {
    if (site_code === 'TL') continue;
    if (!eligible.some(s => s.site_code === site_code)) eligible.push({ site_code, locatie: `${site_code} · doar corectări`, firma: '', regional: 'Magazine indisponibile — corectări', asm: '', cleanupOnly: true });
  }
  return <div className="space-y-4">
    <button className="native-secondary" onClick={() => setSelected({ site_code: 'TL', locatie: 'TL · Team Leaders', firma: '', regional: '', asm: '', virtualBase: true })}>TL · Grile Team Leaders</button>
    <CalendarOverview stores={eligible} data={calendar.data} downloading={download.isPending} refreshing={calendar.isFetching} onDownload={() => download.mutate()} onSelect={setSelected} />
    {download.isError && <p role="alert" className="rounded-2xl bg-rose-50 p-4 text-sm text-rose-700">Exportul nu a reușit. Reîncarcă programul înainte de a încerca din nou. <button className="native-secondary" onClick={() => void calendar.refetch()}>Reîncarcă pontajele</button></p>}
    {selected && <StoreCalendar key={selected.site_code} month={month} store={selected} stores={eligible} data={calendar.data} refreshing={calendar.isFetching} writable={writable} onClose={() => setSelected(null)} />}
  </div>;
}

function StoreCalendar({ month, store, stores, data, refreshing, writable, onClose }: { month: string; store: CalendarStore; stores: CalendarStore[]; data: CalendarData; refreshing: boolean; writable: boolean; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [tab, setTab] = useState(store.virtualBase ? 'Grile' : 'Calendar');
  const [date, setDate] = useState('');
  const [editVersion, setEditVersion] = useState(0);
  const [rosterPending, setRosterPending] = useState(false);
  const [hoursPending, setHoursPending] = useState(false);
  const cache = useQueryClient();
  useEffect(() => { const element = dialog.current!; element.showModal(); return () => element.close(); }, []);
  const save = useMutation({ mutationFn: (days: RetailCalendarDayInput[]) => saveCalendarDays(month, days), onSuccess: async () => { await cache.invalidateQueries({ queryKey: ['native-calendar', month] }); setDate(''); } });
  const refresh = async () => { await cache.invalidateQueries({ queryKey: ['native-calendar', month] }); save.reset(); setEditVersion(v => v + 1); };
  return <dialog ref={dialog} aria-labelledby="calendar-store-title" onCancel={onClose} onClose={onClose} className="native-calendar m-auto max-h-[90dvh] w-[min(1100px,95vw)] overflow-auto rounded-3xl border-0 bg-white p-4 text-slate-900 shadow-2xl backdrop:bg-slate-950/50 sm:p-6 dark:bg-slate-900 dark:text-slate-100">
    <header className="mb-4 flex items-center justify-between gap-4"><div><h2 id="calendar-store-title" className="text-xl font-bold">{store.locatie}</h2><p className="mt-1 text-xs text-slate-500">{store.firma} · {month} · {store.site_code}</p></div><button aria-label="Închide magazinul" onClick={onClose} className="native-secondary shrink-0"><X size={18} aria-hidden="true" /><span className="sr-only sm:not-sr-only">Închide</span></button></header>
    {store.virtualBase && <TeamLeaderRoster month={month} data={data} stores={stores} writable={writable && !refreshing} />}
    {!store.virtualBase && <StoreHoursEditor key={`${store.site_code}-${data.store_hours?.find(h => h.site_code === store.site_code)?.revision ?? 0}`} month={month} site={store.site_code} data={data} disabled={refreshing || save.isPending || rosterPending || hoursPending} writable={writable && !store.cleanupOnly} onPendingChange={setHoursPending} />}
    <div className="mb-4"><SegmentedTabs ariaLabel="Secțiuni magazin" options={(store.virtualBase ? ['Grile'] : ['Grile', 'Calendar', 'Pontaj']).map(label => ({ value: label, label }))} value={tab} onChange={setTab} /></div>
    {tab === 'Grile' && <Earnings month={month} site={store.site_code} calendarRevision={data.projection_revision} />}
    {tab === 'Pontaj' && <Attendance data={data} store={store} />}
    {tab === 'Calendar' && <div className="space-y-4">{store.cleanupOnly ? <p>Magazin indisponibil pentru programări noi. Poți consulta și anula zilele existente.</p> : <Roster month={month} store={store} data={data} writable={writable && !save.isPending && !hoursPending} onPendingChange={setRosterPending} onChanged={() => { setDate(''); }} />}<MonthGrid month={month} store={store} data={data} disabled={refreshing || save.isPending || rosterPending || hoursPending} onSelect={d => { setDate(d); save.reset(); }} />{save.isError && <div role="alert">{save.error instanceof ApiError && save.error.status === 409 ? 'Programul s-a schimbat sau există un conflict. Reîncarcă înainte de o nouă editare.' : getApiErrorMessage(save.error, 'Salvarea a eșuat.')} <button onClick={() => void refresh()}>Reîncarcă programul</button></div>}{date && <CalendarDayEditor key={`${date}-${editVersion}-${data.roster.map(r => `${r.agent_code}:${r.revision}`).join('|')}`} date={date} store={store} stores={stores} data={data} writable={writable && !hoursPending && !refreshing && !rosterPending && !save.isError && !save.isSuccess} busy={save.isPending} onSave={days => save.mutate(days)} />}</div>}
  </dialog>;
}

function MonthGrid({ month, store, data, disabled, onSelect }: { month: string; store: CalendarStore; data: CalendarData; disabled: boolean; onSelect: (date: string) => void }) {
  const { dates, offset } = monthDays(month);
  return <div className="overflow-x-auto"><div className="grid grid-cols-7 gap-1 sm:gap-2">{['Lun', 'Mar', 'Mie', 'Joi', 'Vin', 'Sâm', 'Dum'].map(d => <div key={d} className="p-2 text-center text-sm text-slate-500">{d}</div>)}{Array.from({ length: offset }, (_, i) => <div key={`empty-${i}`} />)}{dates.map(date => {
    const entries = data.days.filter(d => d.work_date === date && d.site_code === store.site_code && d.status !== 'cancelled');
    const worker = entries.find(d => d.status === 'work');
    return <button key={date} aria-label={`Editează ${date}`} disabled={disabled || (store.cleanupOnly && entries.length === 0)} onClick={() => onSelect(date)} className={`min-h-20 min-w-0 overflow-hidden rounded-xl border border-slate-100 p-1 text-left transition hover:border-indigo-300 focus-visible:ring-2 focus-visible:ring-indigo-500 sm:min-h-24 sm:p-2 dark:border-slate-700 ${worker ? 'bg-indigo-50 dark:bg-indigo-950' : ''}`}><span className="block font-bold">{Number(date.slice(-2))}</span>{!worker && <span className="block text-[9px] text-slate-500 sm:text-xs">Nealocat</span>}{entries.map(d => <span key={d.agent_code} className="block truncate text-[10px] sm:text-xs">{agentLabel(data.roster.find(r => r.agent_code === d.agent_code) ?? d)} · {dayLabels[d.status]}{d.supplemental ? ' (supl.)' : ''}</span>)}</button>;
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
  return <details className="rounded-2xl border border-slate-100 bg-slate-50/70 p-4 dark:border-slate-700 dark:bg-slate-800/50"><summary className="cursor-pointer font-semibold">Confirmă agenții și magazinul de bază</summary><p className="my-2 text-sm">Confirmă echipa pentru luna selectată, inclusiv agenții fără vânzări curente.</p>{candidates.isError && <p role="alert">Catalogul nu poate fi încărcat. <button onClick={() => void candidates.refetch()}>Reîncarcă agenții</button></p>}<label className="native-label">Agent <select aria-label="Cod agent pentru confirmare" disabled={confirm.isPending} value={code} onChange={e => { const row = data.roster.find(r => r.agent_code === e.target.value); setSelection({ code: e.target.value, revision: row?.revision ?? 0, active: row?.active ?? true }); confirm.reset(); }} className="native-field"><option value="">Alege agentul</option>{data.roster.map(r => <option key={r.agent_code} value={r.agent_code}>{agentLabel(r)} · confirmat în {r.home_site_code}{r.active ? '' : ' · inactiv'}</option>)}{available.map(c => <option key={c.agent_code} value={c.agent_code}>{c.agent_code} · {c.site_codes.join(', ')}{c.needs_active_confirmation ? ' · fără vânzări curente' : ''}</option>)}</select></label><label className="my-3 flex items-center gap-2 text-sm"><input type="checkbox" disabled={confirm.isPending} checked={active} onChange={e => setSelection(s => ({ ...s, active: e.target.checked }))} /> Activ în această lună</label>{revision > 0 && <p className="my-2 text-sm">Corectare agent confirmat: magazinul de bază devine {store.locatie}. Pentru mutare sau dezactivare, anulează întâi zilele confirmate.</p>}<button className="native-primary" disabled={!code || confirm.isPending || candidates.isFetching} onClick={() => confirm.mutate()}>Confirmă în {store.locatie}</button>{confirm.isError && <p role="alert">{getApiErrorMessage(confirm.error, 'Confirmarea a eșuat. Reîncarcă programul.')} <button onClick={async () => { await cache.invalidateQueries({ queryKey: ['native-calendar', month] }); setSelection({ code: '', revision: 0, active: true }); confirm.reset(); }}>Reîncarcă agenții confirmați</button></p>}</details>;
}
