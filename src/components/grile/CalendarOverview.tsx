import { useState } from 'react';
import { CalendarDays, ChevronDown, ChevronRight, Download, Search, Store, Users } from 'lucide-react';
import type { CalendarData, CalendarStore } from '../../api/grileCalendar';
import { calendarTeamGroups } from './calendarTeamLeaders';

export function CalendarOverview({ stores, data, downloading, refreshing, onDownload, onSelect, headerActions }: {
  headerActions?: React.ReactNode; stores: CalendarStore[]; data: CalendarData; downloading: boolean; refreshing: boolean;
  onDownload: () => void; onSelect: (store: CalendarStore) => void;
}) {
  const [manager, setManager] = useState('');
  const [company, setCompany] = useState('');
  const [search, setSearch] = useState('');
  const managers = [...new Set(stores.map(store => store.regional))].sort();
  const companies = [...new Set(stores.map(store => store.firma).filter(Boolean))].sort();
  const query = search.trim().toLocaleLowerCase('ro');
  const visible = stores.filter(store => (!manager || (store.regional || '__unassigned') === manager)
    && (!company || store.firma === company)
    && `${store.locatie} ${store.site_code}`.toLocaleLowerCase('ro').includes(query));
  const sites = new Set(visible.map(store => store.site_code));
  const days = data.days.filter(day => sites.has(day.site_code) && day.status === 'work');
  const agents = data.roster.filter(agent => agent.active && sites.has(agent.home_site_code));
  const groups = managers.filter(name => visible.some(store => store.regional === name));
  return <>
    <div className="calendar-summary glass rounded-xl p-3">
      <div className="flex flex-wrap items-center justify-between gap-2"><div className="flex items-center gap-2"><h3 className="text-sm font-bold text-slate-900 dark:text-white">Programul echipei</h3><span className="rounded-full bg-indigo-50 px-2 py-0.5 text-xs font-semibold text-indigo-700 dark:bg-indigo-950 dark:text-indigo-200">Provizoriu</span></div><div className="flex flex-wrap items-center gap-2">{headerActions}</div></div>
      <p className="mt-1 text-xs text-slate-500">Calendar, suplimentări și pontaje</p>
      <div className="my-2 grid grid-cols-3 gap-2">
        <CalendarStat icon={<Store size={18} />} value={visible.length} label="Magazine" tone="indigo" />
        <CalendarStat icon={<Users size={18} />} value={agents.length} label="Agenți confirmați" tone="emerald" />
        <CalendarStat icon={<CalendarDays size={18} />} value={days.length} label="Zile programate" tone="amber" />
      </div>
      <div className="grid grid-cols-2 gap-2 lg:grid-cols-3">
        <label className="native-label">Manager<select aria-label="Manager program" className="native-field" value={manager} onChange={event => setManager(event.target.value)}><option value="">Toți managerii</option>{managers.map(name => <option key={name} value={name || '__unassigned'}>{name || 'Fără manager'}</option>)}</select></label>
        <label className="native-label">Firmă<select aria-label="Firmă program" className="native-field" value={company} onChange={event => setCompany(event.target.value)}><option value="">Toate firmele</option>{companies.map(name => <option key={name}>{name}</option>)}</select></label>
        <label className="native-label col-span-2 lg:col-span-1">Magazin<div className="relative"><Search size={17} aria-hidden="true" className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" /><input type="search" aria-label="Caută magazin" className="native-field !pl-10" placeholder="Nume sau cod magazin" value={search} onChange={event => setSearch(event.target.value)} /></div></label>
      </div>
    </div>
    <div className="flex items-center justify-between px-1"><h3 className="font-bold text-slate-800 dark:text-slate-100">Magazinele echipei</h3><span className="text-xs text-slate-500">{visible.length} din {stores.length} magazine</span></div>
    <div className="calendar-groups space-y-1.5">{groups.map(name => <details key={`${name}-${manager}-${company}-${query}`} open={Boolean(manager || query) || groups.length === 1} className="group/manager glass overflow-hidden rounded-xl">
      <summary className="flex min-h-11 cursor-pointer list-none items-center gap-2 px-3 py-2 marker:content-none [&::-webkit-details-marker]:hidden"><span className="rounded-lg bg-indigo-50 p-1 text-indigo-600 dark:bg-indigo-950 dark:text-indigo-300"><Users size={18} /></span><span className="flex min-w-0 flex-1 flex-wrap items-center gap-x-3"><span className="truncate text-sm font-bold text-slate-800 dark:text-slate-100">{name || 'Fără manager'}</span><span className="text-xs text-slate-500">{visible.filter(store => store.regional === name).length} magazine</span></span><ChevronDown size={18} className="text-slate-400 transition-transform group-open/manager:rotate-180" /></summary>
      {name === 'Andrei Stancu' ? <CalendarTeamGroups stores={visible.filter(store => store.regional === name)} data={data} onSelect={onSelect} expanded={Boolean(query)} /> : <div className="grid gap-2 border-t border-slate-100 p-2 sm:grid-cols-2 xl:grid-cols-3 dark:border-slate-800">{visible.filter(store => store.regional === name).map(store => <CalendarStoreCard key={store.site_code} store={store} data={data} onSelect={onSelect} />)}</div>}
    </details>)}</div>
      <div className="glass flex flex-col gap-2 rounded-xl p-3 sm:flex-row sm:items-center sm:justify-between dark:border-slate-800">
        <p className="max-w-lg text-xs leading-relaxed text-slate-500">Pontajele sunt provizorii. ZIP-ul include toate magazinele din programul lunii, indiferent de filtre. V1 rămâne grila oficială.</p>
        <button className="native-primary shrink-0" disabled={downloading || refreshing || !data.roster.length} onClick={onDownload}><Download size={17} aria-hidden="true" />{downloading ? 'Se pregătește…' : 'Descarcă pontajele ZIP (provizoriu)'}</button>
      </div>
      {!data.roster.length && <p className="mt-3 text-xs text-slate-500">Pentru început, deschide un magazin și confirmă agenții echipei. Exportul devine disponibil după confirmare.</p>}
    {!visible.length && <div className="glass rounded-3xl p-8 text-center"><Search className="mx-auto mb-3 text-slate-400" /><h4 className="font-semibold">Niciun magazin găsit</h4><p className="mt-1 text-sm text-slate-500">Schimbă managerul, firma sau termenul căutat.</p><button className="native-secondary mt-4" onClick={() => { setManager(''); setCompany(''); setSearch(''); }}>Resetează filtrele</button></div>}
  </>;
}

function CalendarStat({ icon, value, label, tone }: { icon: React.ReactNode; value: number; label: string; tone: 'indigo' | 'emerald' | 'amber' }) {
  const colors = { indigo: 'bg-indigo-50/80 text-indigo-600 dark:bg-indigo-950/50 dark:text-indigo-300', emerald: 'bg-emerald-50/80 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300', amber: 'bg-amber-50/80 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300' };
  return <div className={`flex min-w-0 flex-wrap items-center gap-x-2 gap-y-0.5 rounded-lg px-2.5 py-2 ${colors[tone]}`}><span className="hidden sm:inline-flex">{icon}</span><strong className="text-lg tabular-nums">{value}</strong><span className="text-xs font-medium leading-snug">{label}</span></div>;
}

function CalendarStoreCard({ store, data, onSelect }: { store: CalendarStore; data: CalendarData; onSelect: (store: CalendarStore) => void }) {
  const days = data.days.filter(day => day.site_code === store.site_code && day.status === 'work').length;
  const agents = data.roster.filter(agent => agent.active && agent.home_site_code === store.site_code).length;
  return <button onClick={() => onSelect(store)} className="group/store min-w-0 rounded-lg border border-slate-200 bg-white px-3 py-2 text-left transition hover:border-indigo-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 dark:border-slate-700 dark:bg-slate-900">
    <div className="flex items-start justify-between gap-2"><strong className="min-w-0 break-words text-xs leading-5 text-slate-900 dark:text-white">{store.locatie}</strong><ChevronRight size={15} className="mt-0.5 shrink-0 text-slate-400 group-hover/store:text-indigo-500" /></div>
    <div className="flex flex-wrap items-center gap-x-2 text-xs leading-5"><span className="font-medium text-slate-600 dark:text-slate-300">{store.firma || 'Arhivă'}</span><span className="text-slate-400">{store.site_code}</span></div>
    <div className="mt-1 flex flex-wrap items-center gap-x-2 text-xs leading-5"><span className={days ? 'text-indigo-700 dark:text-indigo-200' : 'text-amber-800 dark:text-amber-200'}>{days ? `${days} ${days === 1 ? 'zi programată' : 'zile programate'}` : 'De completat'}</span><span className="text-slate-500">{agents} {agents === 1 ? 'agent confirmat' : 'agenți confirmați'}</span></div>
  </button>;
}

function CalendarTeamGroups({ stores, data, onSelect, expanded }: { stores: CalendarStore[]; data: CalendarData; onSelect: (store: CalendarStore) => void; expanded: boolean }) {
  return <div className="space-y-1.5 border-t border-slate-100 bg-slate-50/50 p-2 dark:border-slate-800 dark:bg-slate-950/20">{calendarTeamGroups(stores).map(team => <details key={team.code} open={expanded} className="group/team overflow-hidden rounded-xl border border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-900">
    <summary className="flex min-h-10 cursor-pointer list-none items-center gap-2 px-3 py-2 marker:content-none [&::-webkit-details-marker]:hidden"><Users size={17} className="shrink-0 text-indigo-500" /><span className="flex min-w-0 flex-1 flex-wrap items-center gap-x-3"><span className="text-xs font-semibold">{team.label}</span><span className="text-xs text-slate-500">{team.stores.length} {team.stores.length === 1 ? 'magazin' : 'magazine'}</span></span><ChevronDown size={17} className="shrink-0 text-slate-400 transition-transform group-open/team:rotate-180" /></summary>
    <div className="grid gap-2 border-t border-slate-100 p-2 sm:grid-cols-2 xl:grid-cols-3 dark:border-slate-800">{team.stores.map(store => <CalendarStoreCard key={store.site_code} store={store} data={data} onSelect={onSelect} />)}</div>
  </details>)}</div>;
}
