import { useEffect, useState } from 'react';
import { getApiErrorMessage } from '../../api/client';
import { fetchSalaryArchive, type SalaryArchiveItem, type SalaryArchiveResponse } from '../../api/salaryArchive';
import type { AppFilters } from '../../lib/appFilters';
import { ALL_FIRMS, ALL_SCOPE } from '../../lib/filterValues';

const PAGE_SIZE = 50;
const controlClass = 'min-h-11 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900';
const currency = new Intl.NumberFormat('ro-RO', { style: 'currency', currency: 'RON' });

function ArchiveRow({ item }: { item: SalaryArchiveItem }) {
  const verified = item.identity_status === 'verified_existing' && !!item.candidate_person_id;
  const amount = item.total_amount === null ? null : Number(item.total_amount);
  return <tr className="border-t border-slate-100 align-top dark:border-slate-800">
    <td className="p-3 whitespace-nowrap">{item.period?.slice(0, 7) ?? 'Lună neclarificată'}</td>
    <td className="p-3"><span className="font-semibold">{item.full_name}</span><p className="mt-1 text-xs text-slate-500">{item.company_name ?? 'Firmă neclarificată'} · {item.location ?? item.site_code ?? 'Magazin neclarificat'}</p></td>
    <td className="p-3 text-right whitespace-nowrap tabular-nums">{amount !== null && Number.isFinite(amount) ? currency.format(amount) : 'Sumă neclarificată'}</td>
    <td className="p-3"><span className={verified ? 'text-emerald-700 dark:text-emerald-300' : 'text-amber-700 dark:text-amber-300'}>{verified ? 'Identitate verificată' : 'Identitate nereconciliată'}</span>
      <p className="mt-1 text-xs text-slate-500">{item.already_recorded ? 'Deja în salariile oficiale — nu se adună din nou' : item.pnl_eligible ? 'Eligibil pentru estimări; nu reprezintă un cost salarial complet' : 'Exclus din estimări până la clarificare'}</p>
      {!item.selected && <p className="mt-1 text-xs text-slate-500">Versiune arhivată, neutilizată</p>}
      {item.review_reasons.length > 0 && <p className="mt-1 text-xs text-amber-700 dark:text-amber-300">Necesită verificarea sursei ({item.review_reasons.length} observații).</p>}
    </td>
    <td className="max-w-64 break-words p-3 text-xs text-slate-500">{item.source_file}<p className="mt-1">Foaie: {item.source_sheet} · rând {item.source_row}</p></td>
  </tr>;
}

export function SalaryArchivePanel({ globalFilters }: { globalFilters?: AppFilters }) {
  const [search, setSearch] = useState('');
  const [year, setYear] = useState('');
  const [month, setMonth] = useState('');
  const [page, setPage] = useState(0);
  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState<SalaryArchiveResponse | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const siteKey = JSON.stringify(globalFilters?.magazin ?? []);
  const company = globalFilters?.firma && globalFilters.firma !== ALL_FIRMS ? globalFilters.firma : undefined;
  const regional = globalFilters?.rm && globalFilters.rm !== ALL_SCOPE ? globalFilters.rm : undefined;
  // Key the page to its filter scope: changing scope immediately requests page 1.
  const scopeKey = JSON.stringify([search, year, month, siteKey, company, regional]);
  const [pageScope, setPageScope] = useState(scopeKey);
  const activePage = pageScope === scopeKey ? page : 0;
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setResult(null); setError('');
    const timer = setTimeout(() => {
      const sites = JSON.parse(siteKey) as string[];
      void fetchSalaryArchive({
        search: search.trim() || undefined, year: year ? Number(year) : undefined,
        month: month ? Number(month) : undefined, site_code: sites.length ? sites : undefined,
        company_name: sites.length ? undefined : company, regional: sites.length ? undefined : regional,
        limit: PAGE_SIZE, offset: activePage * PAGE_SIZE,
      }, controller.signal).then((data) => {
        if (!controller.signal.aborted) setResult(data);
      }).catch((cause: unknown) => {
        if (!controller.signal.aborted) setError(getApiErrorMessage(cause, 'Istoricul HR nu a putut fi încărcat.'));
      }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    }, 250);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [search, year, month, siteKey, company, regional, activePage, attempt]);
  const goToPage = (next: number) => { setPageScope(scopeKey); setPage(next); };
  const total = result?.total_rows ?? 0;
  return <section aria-label="Istoric HR arhivat" className="mx-4 space-y-4 pb-4">
    <div className="rounded-2xl border border-indigo-100 bg-indigo-50 p-3 text-sm text-indigo-900 dark:border-indigo-900 dark:bg-indigo-950/30 dark:text-indigo-200">
      <h3 className="font-bold">Istoric HR arhivat</h3>
      <p className="mt-1">Documentele istorice sunt păstrate separat de salariile oficiale. Sumele reprezintă netul și bonurile, nu costul salarial complet al firmei. Rândurile deja înregistrate nu se adună din nou.</p>
      <p className="mt-1">Identitățile nereconciliate rămân fără atribuire unei persoane. Lunile fără documente rămân lipsă.</p>
    </div>
    <div className="flex flex-wrap items-end gap-3">
      <label className="grid gap-1 text-xs">Nume agent<input aria-label="Caută nume în istoricul HR" type="search" maxLength={120} value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Caută după nume..." className={controlClass} /></label>
      <label className="grid gap-1 text-xs">An<select aria-label="An istoric HR" value={year} onChange={(event) => setYear(event.target.value)} className={controlClass}><option value="">Toți anii</option>{Array.from({ length: 86 }, (_, index) => 2015 + index).map((value) => <option key={value} value={value}>{value}</option>)}</select></label>
      <label className="grid gap-1 text-xs">Lună<select aria-label="Lună istoric HR" value={month} onChange={(event) => setMonth(event.target.value)} className={controlClass}><option value="">Toate lunile</option>{Array.from({ length: 12 }, (_, index) => index + 1).map((value) => <option key={value} value={value}>{String(value).padStart(2, '0')}</option>)}</select></label>
    </div>
    {!!globalFilters?.agent.length && <p className="text-xs text-slate-500">Filtrul global de cod agent nu se aplică arhivei. Folosește căutarea după nume.</p>}
    {error && <div role="alert" className="rounded-xl bg-amber-50 p-3 text-sm text-amber-900">{error} <button type="button" onClick={() => setAttempt((value) => value + 1)} className="ml-2 underline">Reîncearcă</button></div>}
    <div className="glass overflow-x-auto rounded-2xl" aria-busy={loading}>
      <table className="w-full min-w-[920px] text-left text-sm"><thead className="bg-slate-50 text-xs text-slate-500 dark:bg-slate-800"><tr>{['Lună', 'Agent / firmă / magazin', 'Net + bonuri', 'Stare', 'Sursă'].map((title) => <th key={title} scope="col" className="p-3">{title}</th>)}</tr></thead>
        <tbody>{result?.items.map((item, index) => <ArchiveRow key={`${item.source_file}-${item.source_sheet}-${item.source_row}-${index}`} item={item} />)}
          {loading && <tr><td colSpan={5} className="p-6 text-center" role="status">Se încarcă istoricul...</td></tr>}
          {!loading && !error && total === 0 && <tr><td colSpan={5} className="p-6 text-center">Nu există rânduri pentru filtrele selectate.</td></tr>}
        </tbody>
      </table>
    </div>
    <div className="flex flex-wrap items-center justify-between gap-3 text-xs text-slate-500"><span aria-live="polite">{result ? `${total ? activePage * PAGE_SIZE + 1 : 0}–${Math.min((activePage + 1) * PAGE_SIZE, total)} din ${total} rânduri` : ''}</span>
      <div className="flex gap-2"><button type="button" className={`${controlClass} disabled:opacity-40`} disabled={loading || activePage === 0} onClick={() => goToPage(activePage - 1)}>Înapoi</button><button type="button" className={`${controlClass} disabled:opacity-40`} disabled={loading || !result || (activePage + 1) * PAGE_SIZE >= total} onClick={() => goToPage(activePage + 1)}>Înainte</button></div>
    </div>
  </section>;
}
