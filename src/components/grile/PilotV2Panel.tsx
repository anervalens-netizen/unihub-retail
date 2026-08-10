import { AlertTriangle, ExternalLink, FlaskConical } from 'lucide-react';

import { GRILE_PILOT_V2 } from '../../config/grilePilotV2';
import { FirmaBadge } from '../FirmaBadge';

export function PilotV2Panel() {
  return (
    <div className="space-y-4">
      <div className="rounded-2xl border border-violet-200 bg-white p-4 dark:border-violet-900/60 dark:bg-slate-900">
        <div className="flex items-start gap-3">
          <span className="rounded-xl bg-violet-100 p-2 text-violet-700 dark:bg-violet-950/60 dark:text-violet-300">
            <FlaskConical className="h-5 w-5" />
          </span>
          <div>
            <h3 className="text-lg font-semibold text-slate-800 dark:text-slate-100">Grile V2 · pilot</h3>
            <p className="mt-0.5 text-xs text-slate-500">
              Program, target personal, vânzări și proiecție salarială într-o singură grilă.
            </p>
          </div>
        </div>

        <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {GRILE_PILOT_V2.map((grila) => (
            <a
              key={grila.siteCode}
              href={`https://docs.google.com/spreadsheets/d/${grila.sheetId}`}
              target="_blank"
              rel="noreferrer"
              className="group flex min-h-20 items-center justify-between gap-3 rounded-xl border border-slate-200 bg-slate-50/70 px-4 py-3 transition hover:border-violet-300 hover:bg-violet-50/60 dark:border-slate-700 dark:bg-slate-800/60 dark:hover:border-violet-700 dark:hover:bg-violet-950/20"
            >
              <span className="min-w-0">
                <span className="flex items-center text-sm font-semibold text-slate-800 dark:text-slate-100">
                  <FirmaBadge firma={grila.firma} />
                  <span className="truncate">{grila.locatie}</span>
                </span>
                <span className="mt-1 block text-xs text-slate-500">{grila.siteCode} · august 2026</span>
              </span>
              <ExternalLink className="h-4 w-4 flex-shrink-0 text-slate-400 group-hover:text-violet-600" />
            </a>
          ))}
        </div>
      </div>

      <div className="flex gap-2 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2.5 text-xs text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/25 dark:text-amber-200">
        <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0" />
        <p>
          Verificarea automată și închiderea lunii rămân pe <strong>Grila actuală</strong>. Pilotul V2 nu
          modifică grilele existente și nu intră în fluxul oficial de închidere.
        </p>
      </div>
    </div>
  );
}
