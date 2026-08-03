import { Building2, Users } from 'lucide-react';
import type { CampaignsPromotionsResponse } from '../api/types';
import { formatInt } from '../lib/formatters';

export function IncentiveQualificationSummary({
  promoData,
  className = '',
}: {
  promoData: CampaignsPromotionsResponse | null;
  className?: string;
}) {
  if (!promoData) return null;

  return (
    <section className={`rounded-xl border border-slate-200 bg-slate-50/70 p-3 dark:border-slate-700 dark:bg-slate-900/40 ${className}`}>
      <div>
        <h5 className="text-xs font-black text-slate-800 dark:text-slate-100">Calificare și mecanism</h5>
        <p className="mt-0.5 text-[10px] font-semibold text-slate-500 dark:text-slate-400">
          90–99,99% din target = 50% incentive · minimum 100% = incentive integral
        </p>
      </div>
      <div className="mt-2 grid grid-cols-2 gap-2">
        <div className="flex items-center gap-2 rounded-lg bg-white px-2.5 py-2 shadow-xs dark:bg-slate-900/70">
          <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-indigo-50 text-indigo-600 dark:bg-indigo-950/50 dark:text-indigo-300">
            <Building2 size={14} />
          </span>
          <div className="min-w-0">
            <div className="text-lg font-black leading-none text-slate-900 dark:text-white">{formatInt(promoData.incentive_qualified_stores)}</div>
            <div className="mt-0.5 truncate text-[10px] font-semibold text-slate-500">magazine calificate</div>
          </div>
        </div>
        <div className="flex items-center gap-2 rounded-lg bg-white px-2.5 py-2 shadow-xs dark:bg-slate-900/70">
          <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-emerald-50 text-emerald-600 dark:bg-emerald-950/50 dark:text-emerald-300">
            <Users size={14} />
          </span>
          <div className="min-w-0">
            <div className="text-lg font-black leading-none text-slate-900 dark:text-white">{formatInt(promoData.incentive_qualified_agents)}</div>
            <div className="mt-0.5 truncate text-[10px] font-semibold text-slate-500">agenți calificați</div>
          </div>
        </div>
      </div>
    </section>
  );
}
