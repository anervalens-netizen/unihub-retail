import { useState } from 'react';
import { CalendarDays, ChevronDown, ChevronRight, Download, Search, Store, Users } from 'lucide-react';
import type { CalendarData, CalendarStore } from '../../api/grileCalendar';

export function CalendarOverview({ stores, data, downloading, refreshing, onDownload, onSelect }: {
  stores: CalendarStore[]; data: CalendarData; downloading: boolean; refreshing: boolean;
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
    <div className="glass rounded-3xl p-4 sm:p-6">
      <div className="flex items-center justify-between gap-2"><h3 className="text-lg font-bold text-slate-900 dark:text-white">Programul echipei</h3><span className="rounded-full bg-indigo-50 px-2 py-1 text-[10px] font-semibold text-indigo-700 dark:bg-indigo-950 dark:text-indigo-200">Provizoriu</span></div>
      <p className="mt-1 text-xs text-slate-500">Calendar, suplimentări și pontaje</p>
      <div className="my-4 grid grid-cols-3 gap-2 sm:gap-4">
        <CalendarStat icon={<Store size={18} />} value={visible.length} label="Magazine" tone="indigo" />
        <CalendarStat icon={<Users size={18} />} value={agents.length} label="Agenți confirmați" tone="emerald" />
        <CalendarStat icon={<CalendarDays size={18} />} value={days.length} label="Zile programate" tone="amber" />
      </div>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-3">
        <label className="native-label">Manager<select aria-label="Manager program" className="native-field" value={manager} onChange={event => setManager(event.target.value)}><option value="">Toți managerii</option>{managers.map(name => <option key={name} value={name || '__unassigned'}>{name || 'Fără manager'}</option>)}</select></label>
        <label className="native-label">Firmă<select aria-label="Firmă program" className="native-field" value={company} onChange={event => setCompany(event.target.value)}><option value="">Toate firmele</option>{companies.map(name => <option key={name}>{name}</option>)}</select></label>
        <label className="native-label col-span-2 lg:col-span-1">Magazin<div className="relative"><Search size={17} aria-hidden="true" className="absolute left-3 top-3.5 text-slate-400" /><input type="search" aria-label="Caută magazin" className="native-field !pl-10" placeholder="Nume sau cod magazin" value={search} onChange={event => setSearch(event.target.value)} /></div></label>
      </div>
    </div>
    <div className="flex items-center justify-between px-1"><h3 className="font-bold text-slate-800 dark:text-slate-100">Magazinele echipei</h3><span className="text-xs text-slate-500">{visible.length} din {stores.length} magazine</span></div>
    <div className="space-y-3">{groups.map(name => <details key={`${name}-${manager}-${company}-${query}`} open={Boolean(manager || query) || groups.length === 1} className="group glass overflow-hidden rounded-2xl">
      <summary className="flex min-h-16 cursor-pointer list-none items-center gap-3 px-4 py-4 marker:content-none sm:px-5 [&::-webkit-details-marker]:hidden"><span className="rounded-xl bg-indigo-50 p-2 text-indigo-600 dark:bg-indigo-950 dark:text-indigo-300"><Users size={18} /></span><span className="min-w-0 flex-1"><span className="block truncate text-sm font-bold text-slate-800 dark:text-slate-100">{name || 'Fără manager'}</span><span className="text-xs text-slate-500">{visible.filter(store => store.regional === name).length} magazine</span></span><ChevronDown size={18} className="text-slate-400 transition-transform group-open:rotate-180" /></summary>
      <div className="grid gap-3 border-t border-slate-100 bg-slate-50/50 p-3 sm:grid-cols-2 sm:p-4 xl:grid-cols-3 dark:border-slate-800 dark:bg-slate-950/20">{visible.filter(store => store.regional === name).map(store => <CalendarStoreCard key={store.site_code} store={store} data={data} onSelect={onSelect} />)}</div>
    </details>)}</div>
      <div className="glass mt-5 flex flex-col gap-3 rounded-2xl p-4 sm:flex-row sm:items-center sm:justify-between dark:border-slate-800">
        <p className="max-w-lg text-xs leading-relaxed text-slate-500">Pontajele sunt provizorii. ZIP-ul include toate magazinele din programul lunii, indiferent de filtre. V1 rămâne grila oficială.</p>
        <button className="native-primary shrink-0" disabled={downloading || refreshing || !data.roster.length} onClick={onDownload}><Download size={17} aria-hidden="true" />{downloading ? 'Se pregătește…' : 'Descarcă pontajele ZIP (provizoriu)'}</button>
      </div>
      {!data.roster.length && <p className="mt-3 text-xs text-slate-500">Pentru început, deschide un magazin și confirmă agenții echipei. Exportul devine disponibil după confirmare.</p>}
    {!visible.length && <div className="glass rounded-3xl p-8 text-center"><Search className="mx-auto mb-3 text-slate-400" /><h4 className="font-semibold">Niciun magazin găsit</h4><p className="mt-1 text-sm text-slate-500">Schimbă managerul, firma sau termenul căutat.</p><button className="native-secondary mt-4" onClick={() => { setManager(''); setCompany(''); setSearch(''); }}>Resetează filtrele</button></div>}
  </>;
}

function CalendarStat({ icon, value, label, tone }: { icon: React.ReactNode; value: number; label: string; tone: 'indigo' | 'emerald' | 'amber' }) {
  const colors = { indigo: 'bg-indigo-50/80 text-indigo-600 dark:bg-indigo-950/50 dark:text-indigo-300', emerald: 'bg-emerald-50/80 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300', amber: 'bg-amber-50/80 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300' };
  return <div className={`min-w-0 rounded-2xl p-2.5 sm:p-4 ${colors[tone]}`}><div className="mb-1">{icon}</div><strong className="block text-2xl tracking-tight sm:text-3xl">{value}</strong><span className="mt-1 block text-xs font-medium leading-snug">{label}</span></div>;
}

function CalendarStoreCard({ store, data, onSelect }: { store: CalendarStore; data: CalendarData; onSelect: (store: CalendarStore) => void }) {
  const days = data.days.filter(day => day.site_code === store.site_code && day.status === 'work').length;
  const agents = data.roster.filter(agent => agent.active && agent.home_site_code === store.site_code).length;
  return <button onClick={() => onSelect(store)} className="group/store min-w-0 rounded-2xl border border-slate-100 bg-white p-4 text-left shadow-sm transition hover:border-indigo-200 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 dark:border-slate-700 dark:bg-slate-900">
    <div className="mb-3 flex items-center justify-between gap-2"><span className="rounded-lg bg-slate-100 px-2 py-1 text-xs font-semibold text-slate-600 dark:bg-slate-800 dark:text-slate-300">{store.firma || 'Arhivă'}</span><ChevronRight size={18} className="text-slate-400 group-hover/store:text-indigo-500" /></div>
    <strong className="block break-words text-sm text-slate-900 dark:text-white">{store.locatie}</strong><span className="mt-1 block text-xs text-slate-400">{store.site_code}</span>
    <div className="mt-4 flex flex-wrap gap-2 text-xs"><span className={`rounded-lg px-2 py-1 ${days ? 'bg-indigo-50 text-indigo-700 dark:bg-indigo-950 dark:text-indigo-200' : 'bg-amber-50 text-amber-800 dark:bg-amber-950 dark:text-amber-200'}`}>{days ? `${days} ${days === 1 ? 'zi programată' : 'zile programate'}` : 'De completat'}</span><span className="py-1 text-slate-500">{agents} {agents === 1 ? 'agent confirmat' : 'agenți confirmați'}</span></div>
  </button>;
}
