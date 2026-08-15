import { useMemo, useState } from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';

import type { AgentEvaluationV2Row } from '../../api/agents';
import { AgentV2MobileCard, AgentV2Row, type V2SortKey, V2SortHeader } from './AgentEvaluationTables';

function EvaluationMechanismDetails() {
  const cards = [
    ['1. Target: max 25p, luna curenta singura 10p', 'In fiecare luna calculam targetul agentului asa: target magazin / zile cu vanzare in locatie x zile cu vanzare agent. Luna primeste nota proprie: sub 80% = 0, 80-89.9% = 1/3, 90-99.9% = 2/3, minimum 100% = maxim. Pentru selectie multi-luna, punctajul target este media ponderata a notelor lunare, nu doar procentul total agregat. Procentul afisat in tabel este procentul agregat, iar punctele sunt nota lunara ponderata.'],
    ['2. Productivitate zilnica: max 20p/25p', 'Calculam vanzare / zile lucrate si comparam cu reperul disponibil: mediana colegilor din magazin, apoi istoricul locatiei pe ultimele 3 luni, apoi media managerului. Puncte: sub 85% = 0, 85-99.9% = 1/3, 100-114.9% = 2/3, minimum 115% = maxim.'],
    ['3. Bon2Acc: max 15p/20p', 'Masuram procentul de bonuri cu minimum 2 produse din total bonuri agent. Puncte: sub 25% = 0, 25-29.9% = 1/3, 30-34.9% = 2/3, minimum 35% = maxim.'],
    ['4. Focus: max 15p/20p', 'Masuram produse focus / total produse vandute de agent. Puncte: sub 6% = 0, 6-7.9% = 1/3, 8-9.9% = 2/3, minimum 10% = maxim.'],
    ['5. Folii Premium: max 10p', 'Masuram folii premium din total folii eligibile. Premium inseamna modelele marcate Sapphire, Ceramic sau Corning. Daca agentul are sub 5 folii eligibile, indicatorul este scos din scor si scorul se normalizeaza fara el. Puncte: sub 30% = 0, 30-39.9% = 1/3, 40-49.9% = 2/3, minimum 50% = maxim.'],
    ['6. Valoare reper: max 15p', 'Masuram vanzare / total produse, adica valoarea medie per produs vandut. Puncte: sub 90 lei = 0, 90-94.9 lei = 1/3, 95-99.9 lei = 2/3, minimum 100 lei = maxim.'],
    ['7. Eligibilitate si rating', 'Un agent este eligibil daca are volum minim: luna finala cere 8 zile si 30 bonuri; luna partiala singura cere 40% din zilele disponibile si 20 bonuri. La selectie multi-luna, lunile inchise cer 8 zile si 30 bonuri per luna, iar luna partiala cere 40% din zilele disponibile si 20 bonuri. Rating: 85+ Excelent, 75-84.9 Foarte Bun, 65-74.9 Bun, 50-64.9 Risc, sub 50 Critic.'],
    ['8. Luna partiala si trend', 'Daca selectezi doar luna partiala, scorul este provizoriu: targetul cantareste 10p, productivitatea 25p, Bon2Acc 20p si Focus 20p. Daca selectezi mai multe luni si una este partiala, luna partiala intra in target cu ponderea zile disponibile / zile luna, iar lunile inchise raman dominante.'],
  ];
  return (
    <div className="border-t border-indigo-100 px-3 pb-3 pt-2 dark:border-indigo-900/40">
      <div className="space-y-2 text-[11px] leading-4 text-slate-600 dark:text-slate-300">
        <div className="rounded-lg border border-indigo-100 bg-white/80 p-2.5 dark:border-indigo-900/50 dark:bg-slate-900/50">
          <div className="font-semibold text-slate-800 dark:text-slate-100">Regula generala</div>
          <p className="mt-0.5">Evaluarea noua este independenta de scorul vechi. Fiecare indicator primeste puncte dupa praguri fixe: sub pragul minim primeste 0, pragul minim primeste o treime din punctaj, pragul mediu primeste doua treimi, iar pragul bun primeste punctajul maxim. Scorul final este normalizat la 100.</p>
        </div>
        <div className="rounded-lg border border-indigo-100 bg-white/80 p-2.5 dark:border-indigo-900/50 dark:bg-slate-900/50">
          <div className="font-semibold text-slate-800 dark:text-slate-100">Ponderi</div>
          <p className="mt-0.5">Selectie normala sau multi-luna: Target 25p, Productivitate 20p, Bon2Acc 15p, Focus 15p, Folii Premium 10p, Valoare reper 15p. Daca selectezi doar luna partiala, scorul devine provizoriu: Target 10p, Productivitate 25p, Bon2Acc 20p, Focus 20p, Folii Premium 10p, Valoare reper 15p.</p>
        </div>
        <div className="grid grid-cols-1 gap-2 md:grid-cols-2 xl:grid-cols-3">
          {cards.map(([title, description]) => <div key={title} className="rounded-lg border border-slate-200 bg-white/80 p-2.5 dark:border-slate-700 dark:bg-slate-900/50">
            <div className="text-[11px] font-semibold text-slate-800 dark:text-slate-100">{title}</div>
            <p className="mt-0.5 text-[11px] leading-4 text-slate-600 dark:text-slate-300">{description}</p>
          </div>)}
        </div>
      </div>
    </div>
  );
}

function EvaluationMechanism({ open, onToggle }: { open: boolean; onToggle: () => void }) {
  return (
    <div className="rounded-xl border border-indigo-200 bg-indigo-50/60 dark:border-indigo-900/50 dark:bg-indigo-950/20">
      <button type="button" onClick={onToggle} className="flex w-full items-center justify-between gap-3 px-3 py-2.5 text-left">
        <div>
          <div className="text-[11px] font-bold uppercase tracking-wider text-indigo-600 dark:text-indigo-300">Cum se face evaluarea</div>
          <div className="mt-0.5 text-[11px] text-slate-500 dark:text-slate-400">Punctaj 0–100, separat de analiza inițială și fără componentă de bonus.</div>
        </div>
        {open ? <ChevronUp size={14} className="text-indigo-500" /> : <ChevronDown size={14} className="text-indigo-500" />}
      </button>
      {open && <EvaluationMechanismDetails />}
    </div>
  );
}

function EvaluationSummary({ rows }: { rows: AgentEvaluationV2Row[] }) {
  const summary = useMemo(() => {
    const scored = rows.filter((row) => row.total_score !== null);
    return {
      agents: new Set(rows.map((row) => row.agent)).size,
      avgScore: scored.length ? scored.reduce((sum, row) => sum + Number(row.total_score), 0) / scored.length : 0,
      eligible: rows.filter((row) => row.eligibility_status === 'eligibil').length,
      partial: rows.filter((row) => row.is_partial).length,
    };
  }, [rows]);
  const items = [
    { label: 'Agenți', value: String(summary.agents), sub: `${rows.length} rânduri` },
    { label: 'Scor', value: summary.avgScore.toFixed(1), sub: 'medie /100' },
    { label: 'Eligibili', value: String(summary.eligible), sub: 'volum valid' },
    { label: 'Provizorii', value: String(summary.partial), sub: 'lună parțială' },
  ];
  return <div className="rounded-xl border border-slate-200 bg-white/80 p-2.5 dark:border-slate-700 dark:bg-slate-900/50"><div className="grid grid-cols-4 gap-2">{items.map((item) => <div key={item.label} className="min-w-0">
    <div className="truncate text-[10px] font-bold uppercase tracking-wider text-slate-400">{item.label}</div>
    <div className="truncate text-sm font-bold tabular-nums text-slate-900 dark:text-slate-100 sm:text-base">{item.value}</div>
    <div className="hidden truncate text-[10px] text-slate-500 dark:text-slate-400 sm:block">{item.sub}</div>
  </div>)}</div></div>;
}

function EvaluationTable({ rows, sortKey, sortDirection, onSort }: {
  rows: AgentEvaluationV2Row[]; sortKey: V2SortKey;
  sortDirection: 'asc' | 'desc'; onSort: (key: V2SortKey) => void;
}) {
  const headers: Array<{ label: string; key: V2SortKey; align?: 'right' }> = [
    { label: 'Agent', key: 'agent' }, { label: 'Vânzare', key: 'total_sales', align: 'right' },
    { label: 'Scor', key: 'total_score', align: 'right' }, { label: 'Status', key: 'eligibility_status' },
    { label: 'Target', key: 'target_pct', align: 'right' }, { label: 'Productivitate', key: 'daily_vs_reference_pct', align: 'right' },
    { label: 'Bon2Acc', key: 'bonuri_pct', align: 'right' }, { label: 'Focus', key: 'focus_pct', align: 'right' },
    { label: 'Folii Premium', key: 'premium_glass_pct', align: 'right' }, { label: 'Valoare reper', key: 'value_reper', align: 'right' },
    { label: 'Trend', key: 'trend_daily_pct', align: 'right' },
  ];
  return <>
    <div className="space-y-2 lg:hidden">{rows.map((row) => <AgentV2MobileCard key={`${row.month}:${row.site_code}:${row.agent}:mobile`} row={row} />)}{rows.length === 0 && <p className="rounded-2xl border border-slate-200 p-6 text-center text-sm text-slate-400 dark:border-slate-700">Fără agenți pentru filtrele selectate.</p>}</div>
    <div className="hidden rounded-2xl border border-slate-200 bg-white/70 dark:border-slate-700 dark:bg-slate-900/40 lg:block lg:overflow-hidden"><div className="max-h-[68vh] overflow-auto"><table className="min-w-[1320px] w-full text-left">
      <thead className="sticky top-0 z-10 bg-slate-100 text-[10px] uppercase tracking-wider text-slate-500 dark:bg-slate-800"><tr><th className="px-3 py-2">Lună</th>{headers.map((header) => <V2SortHeader key={header.key} label={header.label} sortKey={header.key} align={header.align} currentKey={sortKey} direction={sortDirection} onSort={onSort} />)}</tr></thead>
      <tbody>{rows.map((row) => <AgentV2Row key={`${row.month}:${row.site_code}:${row.agent}:v2`} row={row} />)}{rows.length === 0 && <tr><td colSpan={12} className="px-3 py-8 text-center text-sm text-slate-400">Fără agenți pentru filtrele selectate.</td></tr>}</tbody>
    </table></div></div>
  </>;
}

export function NewEvaluationSubsection({ rows, sortKey, sortDirection, onSort }: {
  rows: AgentEvaluationV2Row[];
  sortKey: V2SortKey;
  sortDirection: 'asc' | 'desc';
  onSort: (key: V2SortKey) => void;
}) {
  const [showMechanism, setShowMechanism] = useState(false);
  return <div className="space-y-3">
    <EvaluationMechanism open={showMechanism} onToggle={() => setShowMechanism((value) => !value)} />
    <EvaluationSummary rows={rows} />
    <EvaluationTable rows={rows} sortKey={sortKey} sortDirection={sortDirection} onSort={onSort} />
  </div>;
}
