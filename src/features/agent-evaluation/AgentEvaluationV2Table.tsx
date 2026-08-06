import { useMemo, useState } from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';
import type { AgentEvaluationV2Row } from '../../api/agents';
import { AgentV2MobileCard, AgentV2Row, type V2SortKey, V2SortHeader } from './AgentEvaluationTables';

export function NewEvaluationSubsection({
  rows,
  sortKey,
  sortDirection,
  onSort,
}: {
  rows: AgentEvaluationV2Row[];
  sortKey: V2SortKey;
  sortDirection: 'asc' | 'desc';
  onSort: (key: V2SortKey) => void;
}) {
  const [showMechanism, setShowMechanism] = useState(false);
  const summary = useMemo(() => {
    const scored = rows.filter((row) => row.total_score !== null);
    const agents = new Set(rows.map((row) => row.agent)).size;
    const avgScore = scored.length ? scored.reduce((sum, row) => sum + Number(row.total_score), 0) / scored.length : 0;
    const eligible = rows.filter((row) => row.eligibility_status === 'eligibil').length;
    const partial = rows.filter((row) => row.is_partial).length;
    return { agents, avgScore, eligible, partial };
  }, [rows]);

  return (
    <div className="space-y-3">
      <div className="rounded-xl border border-indigo-200 dark:border-indigo-900/50 bg-indigo-50/60 dark:bg-indigo-950/20">
        <button
          type="button"
          onClick={() => setShowMechanism((value) => !value)}
          className="flex w-full items-center justify-between gap-3 px-3 py-2.5 text-left"
        >
          <div>
            <div className="text-[11px] font-bold uppercase tracking-wider text-indigo-600 dark:text-indigo-300">
              Cum se face evaluarea
            </div>
            <div className="mt-0.5 text-[11px] text-slate-500 dark:text-slate-400">
              Punctaj 0–100, separat de analiza inițială și fără componentă de bonus.
            </div>
          </div>
          {showMechanism ? <ChevronUp size={14} className="text-indigo-500" /> : <ChevronDown size={14} className="text-indigo-500" />}
        </button>
        {showMechanism && (
          <div className="border-t border-indigo-100 dark:border-indigo-900/40 px-3 pb-3 pt-2">
            <div className="space-y-2 text-[11px] leading-4 text-slate-600 dark:text-slate-300">
              <div className="rounded-lg border border-indigo-100 bg-white/80 p-2.5 dark:border-indigo-900/50 dark:bg-slate-900/50">
                <div className="font-semibold text-slate-800 dark:text-slate-100">Regula generala</div>
                <p className="mt-0.5">
                  Evaluarea noua este independenta de scorul vechi. Fiecare indicator primeste puncte dupa praguri fixe:
                  sub pragul minim primeste 0, pragul minim primeste o treime din punctaj, pragul mediu primeste doua treimi,
                  iar pragul bun primeste punctajul maxim. Scorul final este normalizat la 100.
                </p>
              </div>
              <div className="rounded-lg border border-indigo-100 bg-white/80 p-2.5 dark:border-indigo-900/50 dark:bg-slate-900/50">
                <div className="font-semibold text-slate-800 dark:text-slate-100">Ponderi</div>
                <p className="mt-0.5">
                  Selectie normala sau multi-luna: Target 25p, Productivitate 20p, Bon2Acc 15p, Focus 15p,
                  Folii Premium 10p, Valoare reper 15p. Daca selectezi doar luna partiala, scorul devine provizoriu:
                  Target 10p, Productivitate 25p, Bon2Acc 20p, Focus 20p, Folii Premium 10p, Valoare reper 15p.
                </p>
              </div>

              <div className="grid grid-cols-1 gap-2 md:grid-cols-2 xl:grid-cols-3">
              <div className="rounded-lg border border-slate-200 dark:border-slate-700 bg-white/80 dark:bg-slate-900/50 p-2.5">
                <div className="text-[11px] font-semibold text-slate-800 dark:text-slate-100">1. Target: max 25p, luna curenta singura 10p</div>
                <p className="mt-0.5 text-[11px] leading-4 text-slate-600 dark:text-slate-300">
                  In fiecare luna calculam targetul agentului asa: target magazin / zile cu vanzare in locatie x zile cu vanzare agent.
                  Luna primeste nota proprie: sub 80% = 0, 80-89.9% = 1/3, 90-99.9% = 2/3, minimum 100% = maxim.
                  Pentru selectie multi-luna, punctajul target este media ponderata a notelor lunare, nu doar procentul total agregat.
                  Procentul afisat in tabel este procentul agregat, iar punctele sunt nota lunara ponderata.
                </p>
              </div>
              <div className="rounded-lg border border-slate-200 dark:border-slate-700 bg-white/80 dark:bg-slate-900/50 p-2.5">
                <div className="text-[11px] font-semibold text-slate-800 dark:text-slate-100">2. Productivitate zilnica: max 20p/25p</div>
                <p className="mt-0.5 text-[11px] leading-4 text-slate-600 dark:text-slate-300">
                  Calculam vanzare / zile lucrate si comparam cu reperul disponibil: mediana colegilor din magazin,
                  apoi istoricul locatiei pe ultimele 3 luni, apoi media managerului. Puncte: sub 85% = 0,
                  85-99.9% = 1/3, 100-114.9% = 2/3, minimum 115% = maxim.
                </p>
              </div>
              <div className="rounded-lg border border-slate-200 dark:border-slate-700 bg-white/80 dark:bg-slate-900/50 p-2.5">
                <div className="text-[11px] font-semibold text-slate-800 dark:text-slate-100">3. Bon2Acc: max 15p/20p</div>
                <p className="mt-0.5 text-[11px] leading-4 text-slate-600 dark:text-slate-300">
                  Masuram procentul de bonuri cu minimum 2 produse din total bonuri agent. Puncte: sub 25% = 0,
                  25-29.9% = 1/3, 30-34.9% = 2/3, minimum 35% = maxim.
                </p>
              </div>
              <div className="rounded-lg border border-slate-200 dark:border-slate-700 bg-white/80 dark:bg-slate-900/50 p-2.5">
                <div className="text-[11px] font-semibold text-slate-800 dark:text-slate-100">4. Focus: max 15p/20p</div>
                <p className="mt-0.5 text-[11px] leading-4 text-slate-600 dark:text-slate-300">
                  Masuram produse focus / total produse vandute de agent. Puncte: sub 6% = 0, 6-7.9% = 1/3,
                  8-9.9% = 2/3, minimum 10% = maxim.
                </p>
              </div>
              <div className="rounded-lg border border-slate-200 dark:border-slate-700 bg-white/80 dark:bg-slate-900/50 p-2.5">
                <div className="text-[11px] font-semibold text-slate-800 dark:text-slate-100">5. Folii Premium: max 10p</div>
                <p className="mt-0.5 text-[11px] leading-4 text-slate-600 dark:text-slate-300">
                  Masuram folii premium din total folii eligibile. Premium inseamna modelele marcate Sapphire, Ceramic sau Corning.
                  Daca agentul are sub 5 folii eligibile, indicatorul este scos din scor si scorul se normalizeaza fara el.
                  Puncte: sub 30% = 0, 30-39.9% = 1/3, 40-49.9% = 2/3, minimum 50% = maxim.
                </p>
              </div>
              <div className="rounded-lg border border-slate-200 dark:border-slate-700 bg-white/80 dark:bg-slate-900/50 p-2.5">
                <div className="text-[11px] font-semibold text-slate-800 dark:text-slate-100">6. Valoare reper: max 15p</div>
                <p className="mt-0.5 text-[11px] leading-4 text-slate-600 dark:text-slate-300">
                  Masuram vanzare / total produse, adica valoarea medie per produs vandut. Puncte: sub 90 lei = 0,
                  90-94.9 lei = 1/3, 95-99.9 lei = 2/3, minimum 100 lei = maxim.
                </p>
              </div>
              <div className="rounded-lg border border-slate-200 dark:border-slate-700 bg-white/80 dark:bg-slate-900/50 p-2.5">
                <div className="text-[11px] font-semibold text-slate-800 dark:text-slate-100">7. Eligibilitate si rating</div>
                <p className="mt-0.5 text-[11px] leading-4 text-slate-600 dark:text-slate-300">
                  Un agent este eligibil daca are volum minim: luna finala cere 8 zile si 30 bonuri; luna partiala singura cere
                  40% din zilele disponibile si 20 bonuri. La selectie multi-luna, lunile inchise cer 8 zile si 30 bonuri per luna,
                  iar luna partiala cere 40% din zilele disponibile si 20 bonuri.
                  Rating: 85+ Excelent, 75-84.9 Foarte Bun, 65-74.9 Bun, 50-64.9 Risc, sub 50 Critic.
                </p>
              </div>
              <div className="rounded-lg border border-slate-200 dark:border-slate-700 bg-white/80 dark:bg-slate-900/50 p-2.5">
                <div className="text-[11px] font-semibold text-slate-800 dark:text-slate-100">8. Luna partiala si trend</div>
                <p className="mt-0.5 text-[11px] leading-4 text-slate-600 dark:text-slate-300">
                  Daca selectezi doar luna partiala, scorul este provizoriu: targetul cantareste 10p, productivitatea 25p,
                  Bon2Acc 20p si Focus 20p. Daca selectezi mai multe luni si una este partiala, luna partiala intra in
                  target cu ponderea zile disponibile / zile luna, iar lunile inchise raman dominante.
                </p>
              </div>
              </div>
            </div>
          </div>
        )}
      </div>

      <div className="rounded-xl border border-slate-200 dark:border-slate-700 bg-white/80 dark:bg-slate-900/50 p-2.5">
        <div className="grid grid-cols-4 gap-2">
          {[
            { label: 'Agenți', value: String(summary.agents), sub: `${rows.length} rânduri` },
            { label: 'Scor', value: summary.avgScore.toFixed(1), sub: 'medie /100' },
            { label: 'Eligibili', value: String(summary.eligible), sub: 'volum valid' },
            { label: 'Provizorii', value: String(summary.partial), sub: 'lună parțială' },
          ].map((item) => (
            <div key={item.label} className="min-w-0">
              <div className="text-[10px] uppercase tracking-wider font-bold text-slate-400 truncate">{item.label}</div>
              <div className="text-sm sm:text-base font-bold text-slate-900 dark:text-slate-100 tabular-nums truncate">{item.value}</div>
              <div className="hidden sm:block text-[10px] text-slate-500 dark:text-slate-400 truncate">{item.sub}</div>
            </div>
          ))}
        </div>
      </div>

      <div className="space-y-2 lg:hidden">
        {rows.map((row) => <AgentV2MobileCard key={`${row.month}:${row.site_code}:${row.agent}:mobile`} row={row} />)}
        {rows.length === 0 && <p className="rounded-2xl border border-slate-200 p-6 text-center text-sm text-slate-400 dark:border-slate-700">Fără agenți pentru filtrele selectate.</p>}
      </div>
      <div className="hidden rounded-2xl border border-slate-200 bg-white/70 dark:border-slate-700 dark:bg-slate-900/40 lg:block lg:overflow-hidden">
        <div className="max-h-[68vh] overflow-auto">
          <table className="min-w-[1320px] w-full text-left">
            <thead className="sticky top-0 z-10 bg-slate-100 dark:bg-slate-800 text-[10px] uppercase tracking-wider text-slate-500">
              <tr>
                <th className="px-3 py-2">Lună</th>
                <V2SortHeader label="Agent" sortKey="agent" currentKey={sortKey} direction={sortDirection} onSort={onSort} />
                <V2SortHeader label="Vânzare" sortKey="total_sales" align="right" currentKey={sortKey} direction={sortDirection} onSort={onSort} />
                <V2SortHeader label="Scor" sortKey="total_score" align="right" currentKey={sortKey} direction={sortDirection} onSort={onSort} />
                <V2SortHeader label="Status" sortKey="eligibility_status" currentKey={sortKey} direction={sortDirection} onSort={onSort} />
                <V2SortHeader label="Target" sortKey="target_pct" align="right" currentKey={sortKey} direction={sortDirection} onSort={onSort} />
                <V2SortHeader label="Productivitate" sortKey="daily_vs_reference_pct" align="right" currentKey={sortKey} direction={sortDirection} onSort={onSort} />
                <V2SortHeader label="Bon2Acc" sortKey="bonuri_pct" align="right" currentKey={sortKey} direction={sortDirection} onSort={onSort} />
                <V2SortHeader label="Focus" sortKey="focus_pct" align="right" currentKey={sortKey} direction={sortDirection} onSort={onSort} />
                <V2SortHeader label="Folii Premium" sortKey="premium_glass_pct" align="right" currentKey={sortKey} direction={sortDirection} onSort={onSort} />
                <V2SortHeader label="Valoare reper" sortKey="value_reper" align="right" currentKey={sortKey} direction={sortDirection} onSort={onSort} />
                <V2SortHeader label="Trend" sortKey="trend_daily_pct" align="right" currentKey={sortKey} direction={sortDirection} onSort={onSort} />
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <AgentV2Row key={`${row.month}:${row.site_code}:${row.agent}:v2`} row={row} />
              ))}
              {rows.length === 0 && (
                <tr>
                  <td colSpan={12} className="px-3 py-8 text-center text-sm text-slate-400">
                    Fără agenți pentru filtrele selectate.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
