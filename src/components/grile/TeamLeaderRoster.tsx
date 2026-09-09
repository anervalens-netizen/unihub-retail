import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { confirmCalendarAgent, type CalendarData, type CalendarStore } from '../../api/grileCalendar';
import { getApiErrorMessage } from '../../api/client';

export function TeamLeaderRoster({ month, data, stores, writable }: { month: string; data: CalendarData; stores: CalendarStore[]; writable: boolean }) {
  const [entry, setEntry] = useState({ code: '', regional: '', revision: 0, active: true });
  const cache = useQueryClient();
  const save = useMutation({ mutationFn: () => confirmCalendarAgent(month, entry.code.trim(), { home_site_code: 'TL', regional: entry.regional, active: entry.active, expected_revision: entry.revision }), onSuccess: async () => {
    await cache.invalidateQueries({ queryKey: ['native-calendar', month] });
    setEntry({ code: '', regional: '', revision: 0, active: true });
  } });
  const managers = [...new Set([...stores.filter(s => !s.cleanupOnly).map(s => s.regional), entry.regional].filter(Boolean))].sort();
  const leaders = data.roster.filter(r => r.home_site_code === 'TL');
  if (!writable) return <p>Team Leaders fără magazin de bază · mod consultare.</p>;
  return <form className="mb-4 space-y-3 rounded-2xl bg-slate-50 p-4 dark:bg-slate-800" onSubmit={e => { e.preventDefault(); if (entry.code.trim() && entry.regional && !save.isPending) save.mutate(); }}>
    <h3 className="font-semibold">Echipa TL · {month}</h3>
    <p className="text-sm">Confirmă codul real al persoanei și managerul regional. Programul se introduce în calendarul magazinului lucrat.</p>
    <label className="native-label">Team Leader<select className="native-field" aria-label="Team Leader confirmat" disabled={save.isPending} value={entry.revision ? entry.code : ''} onChange={e => {
      const row = leaders.find(r => r.agent_code === e.target.value);
      setEntry(row ? { code: row.agent_code, regional: row.regional ?? '', revision: row.revision, active: row.active } : { code: '', regional: '', revision: 0, active: true });
      save.reset();
    }}><option value="">Adaugă Team Leader</option>{leaders.map(r => <option key={r.agent_code} value={r.agent_code}>{r.display_name || r.agent_code} · {r.agent_code}{r.active ? '' : ' · inactiv'}</option>)}</select></label>
    <label className="native-label">Cod Team Leader<input className="native-field" aria-label="Cod Team Leader" maxLength={80} required disabled={save.isPending || entry.revision > 0} value={entry.code} onChange={e => setEntry({ ...entry, code: e.target.value })} /></label>
    <label className="native-label">Manager regional<select className="native-field" aria-label="Manager regional TL" required disabled={save.isPending} value={entry.regional} onChange={e => setEntry({ ...entry, regional: e.target.value })}><option value="">Alege managerul</option>{managers.map(m => <option key={m}>{m}</option>)}</select></label>
    <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={entry.active} disabled={save.isPending} onChange={e => setEntry({ ...entry, active: e.target.checked })} /> Activ în această lună</label>
    {entry.revision > 0 && <p className="text-sm">Pentru schimbarea managerului sau dezactivare, anulează întâi zilele programate.</p>}
    <button className="native-primary" disabled={save.isPending || !entry.code.trim() || !entry.regional}>Salvează Team Leader</button>
    {save.isError && <p role="alert">{getApiErrorMessage(save.error, 'Salvarea nu a reușit. Reîncarcă și selectează din nou persoana.')} <button type="button" onClick={() => { void cache.invalidateQueries({ queryKey: ['native-calendar', month] }); setEntry({ code: '', regional: '', revision: 0, active: true }); save.reset(); }}>Reîncarcă echipa TL</button></p>}
  </form>;
}
