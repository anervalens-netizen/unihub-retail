import type { ManagerOverview } from '../../api/hr';
import { FirmaBadge } from '../FirmaBadge';
import { TableHeaderCell } from '../common/TableHeader';
import { cn } from '../../lib/utils';

/**
 * Shared store portfolio presentation used by both the mobile card and the
 * desktop table. Extracted from `ASMSubtab.tsx` during the C8 frontend
 * decomposition so the responsive views do not duplicate the same table.
 */
export function ManagerStorePortfolio({ row }: { row: ManagerOverview }) {
  return (
    <div className="overflow-x-auto rounded-xl border border-slate-200 dark:border-slate-700">
      <table className="min-w-[680px] w-full text-xs">
        <thead className="bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300">
          <tr>
            <TableHeaderCell>Magazin</TableHeaderCell>
            <TableHeaderCell>Firmă</TableHeaderCell>
            <TableHeaderCell align="center">Agenți activi</TableHeaderCell>
            <TableHeaderCell align="center">Luna precedentă</TableHeaderCell>
            <TableHeaderCell align="center">Schimbare</TableHeaderCell>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100 bg-white dark:divide-slate-800 dark:bg-slate-900">
          {row.stores.map((store) => {
            const deltaTone = store.agent_delta > 0
              ? 'text-emerald-600 dark:text-emerald-400'
              : store.agent_delta < 0
                ? 'text-rose-600 dark:text-rose-400'
                : 'text-slate-500 dark:text-slate-400';
            return (
              <tr key={store.site_code} className="hover:bg-slate-50 dark:hover:bg-slate-800/40">
                <td className="px-2.5 py-2">
                  <div className="font-semibold text-slate-700 dark:text-slate-200">{store.locatie}</div>
                  <div className="text-[10px] text-slate-500 dark:text-slate-400">{store.site_code}</div>
                </td>
                <td className="px-2.5 py-2"><FirmaBadge firma={store.firma} /></td>
                <td className="px-2.5 py-2 text-center font-semibold tabular-nums text-slate-700 dark:text-slate-200">
                  {store.active_agents}
                </td>
                <td className="px-2.5 py-2 text-center tabular-nums text-slate-500">{store.previous_active_agents}</td>
                <td className={cn('px-2.5 py-2 text-center font-bold tabular-nums', deltaTone)}>
                  {store.agent_delta > 0 ? '+' : ''}{store.agent_delta}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
