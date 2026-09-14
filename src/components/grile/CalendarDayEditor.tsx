import { homeOn } from './rosterHistory';
import { agentLabel } from './calendarModel';
import { useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import type { CalendarData, CalendarStore } from '../../api/grileCalendar';
import { conflictingCalendarDay, dayChanges } from './calendarModel';
import type { RetailCalendarDayInput } from '../../api/generated/contracts';

export function CalendarDayEditor({ data, store, stores, date, busy, writable, onSave, onClose, onCloseDay, anchor }: {
  data: CalendarData; store: CalendarStore; stores: CalendarStore[]; date: string;
  anchor?: HTMLElement | null; onClose?: () => void; busy: boolean; writable: boolean; onSave: (days: RetailCalendarDayInput[]) => void; onCloseDay?: (closure: import('../../api/generated/contracts').RetailCalendarClosureInput, occupant?: { agent_code: string; site_code: string; revision: number }) => void;
}) {
  const [snapshot] = useState(data);
  const occupant = snapshot.days.find(d => d.work_date === date && d.site_code === store.site_code && d.status === 'work');
  const closure = snapshot.closures?.find(c => c.work_date === date && c.site_code === store.site_code);
  const [code, setCode] = useState(occupant?.agent_code ?? '');
  const [status, setStatus] = useState<'leave' | 'off'>(occupant?.status === 'off' ? 'off' : 'leave');
  const closed = !code && !store.virtualBase;
  const assignedHere = (agent: string) => snapshot.days.some(d => d.agent_code === agent && d.work_date === date && d.site_code === store.site_code && d.status !== 'cancelled');
  const roster = store.cleanupOnly ? snapshot.roster.filter(r => assignedHere(r.agent_code)) : snapshot.roster.filter(r => r.active && (homeOn(r, date) === store.site_code || (r.home_site_code === 'TL' && Boolean(r.regional) && r.regional === store.regional) || stores.some(s => s.site_code === homeOn(r, date) && s.regional === store.regional && Boolean(s.regional))));
  const groups = [['Agenții magazinului', roster.filter(r => homeOn(r, date) === store.site_code)], ['Alți agenți din regiune', roster.filter(r => homeOn(r, date) !== store.site_code)]] as const;
  const selected = snapshot.roster.find(r => r.agent_code === code);
  const away = Boolean(selected && homeOn(selected, date) !== store.site_code);
  const elsewhere = conflictingCalendarDay(snapshot, code, date, store.site_code);
  const blocked = busy || !writable || Boolean(elsewhere) || (store.virtualBase && !code) || (store.cleanupOnly && !assignedHere(code) && !occupant);
  const form = <form className="space-y-3 rounded-xl bg-slate-50 p-4 dark:bg-slate-800" onSubmit={e => { e.preventDefault(); if (blocked) return; if (closed) { onCloseDay?.({ work_date: date, site_code: store.site_code, closed: true, expected_revision: closure?.revision ?? 0 }, occupant); return; } onSave(dayChanges(snapshot, { work_date: date, agent_code: code, site_code: store.site_code, status: store.virtualBase ? status : 'work', supplemental: store.virtualBase ? false : away })); }}>
    <div className="flex items-center justify-between gap-2"><h4 className="font-semibold">Program pentru {date}</h4>{onClose && <button type="button" aria-label="Închide ziua" onClick={onClose} className="native-secondary">Închide</button>}</div>
    <label className="native-label">Agent sau stare zi<select autoFocus aria-label="Agent pentru zi" className={`native-field grile-day-agent-select ${closed ? 'is-closed' : ''}`} value={code} onChange={e => { setCode(e.target.value); }}><option value="">Închisă / fără agent</option>{groups.map(([label, rows]) => rows.length > 0 && <optgroup key={label} label={label}>{rows.map(r => <option key={r.agent_code} value={r.agent_code}>{agentLabel(r)}{homeOn(r, date) === store.site_code ? '' : ` · ${stores.find(s => s.site_code === homeOn(r, date))?.locatie ?? homeOn(r, date)}`}</option>)}</optgroup>)}</select></label>
    {store.virtualBase && <label className="native-label">Tip absență<select aria-label="Tip absență TL" className="native-field" value={status} onChange={e => setStatus(e.target.value as 'leave' | 'off')}><option value="leave">Concediu</option><option value="off">Zi liberă</option></select></label>}
    {occupant && <p>Înregistrare actuală: {agentLabel(snapshot.roster.find(r => r.agent_code === occupant.agent_code) ?? occupant)} · {occupant.status === 'off' ? 'zi liberă' : occupant.status === 'leave' ? 'concediu' : 'lucrează'}</p> }
    {closure && <p className="font-semibold text-rose-700">Zi închisă. Selectează un agent pentru a redeschide.</p>}
    {elsewhere && <p role="alert">Agentul are deja o zi în {elsewhere.site_code}. Corectează întâi programul de acolo.</p>}
    <button disabled={blocked} className="rounded-lg bg-indigo-600 px-4 py-2 text-white disabled:opacity-40">{busy ? 'Se salvează…' : closed ? 'Închide ziua' : 'Salvează ziua'}</button>
  </form>;
  return onClose && anchor ? <DayPopover anchor={anchor} onClose={busy ? () => undefined : onClose}>{form}</DayPopover> : form;
}

function DayPopover({ children, anchor, onClose }: { children: ReactNode; anchor: HTMLElement; onClose: () => void }) {
  const popup = useRef<HTMLDivElement>(null);
  const close = useRef(onClose);
  const [position, setPosition] = useState({ left: 0, top: 0 });
  useLayoutEffect(() => { close.current = onClose; }, [onClose]);
  useLayoutEffect(() => {
    const el = popup.current!;
    el.showPopover?.();
    const place = () => {
      const day = anchor.getBoundingClientRect();
      const width = el.offsetWidth || 400; const height = el.offsetHeight || 370;
      const top = day.bottom + height + 8 <= window.innerHeight ? day.bottom + 4 : Math.max(8, day.top - height - 4);
      setPosition({ left: Math.max(8, Math.min(day.left, window.innerWidth - width - 8)), top });
    };
    const outside = (event: PointerEvent) => { if (!el.contains(event.target as Node) && !anchor.contains(event.target as Node)) close.current(); };
    const escape = (event: KeyboardEvent) => { if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); close.current(); } };
    place();
    window.addEventListener('resize', place); document.addEventListener('scroll', place, true);
    document.addEventListener('pointerdown', outside); document.addEventListener('keydown', escape, true);
    return () => { window.removeEventListener('resize', place); document.removeEventListener('scroll', place, true); document.removeEventListener('pointerdown', outside); document.removeEventListener('keydown', escape, true); el.hidePopover?.(); };
  }, [anchor]);
  return <div ref={popup} popover={typeof HTMLElement !== 'undefined' && 'showPopover' in HTMLElement.prototype ? 'manual' : undefined} role="dialog" aria-label="Editează ziua din calendar" className="native-calendar grile-day-popover m-0 max-h-[85dvh] w-[min(420px,94vw)] overflow-auto rounded-xl border border-slate-200 bg-white p-0 text-slate-900 shadow-2xl dark:bg-slate-800 dark:text-white" style={{ position: 'fixed', inset: 'auto', ...position }}>{children}</div>;
}
