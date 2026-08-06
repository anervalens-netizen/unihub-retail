import type { TargetAllocationViewRow } from './TargetScenarioView';
import { formatPercent } from '../../lib/formatters';
import { formatSignedPercent, formatSignedPp, formatTableNumber, percentTone } from './model';

export function TargetAllocationTable({ regionalAllocation }: { regionalAllocation: TargetAllocationViewRow[] }) {
  return (
<div className="glass overflow-hidden rounded-2xl">
  <div className="border-b border-slate-200 px-4 py-3 dark:border-slate-700">
    <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-100">Cum a fost alocat targetul pe manageri</h3>
    <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
      Δ mix arată dacă managerul primește o pondere mai mare sau mai mică decât contribuția sa la vânzări. „Peste sezonier” și „Peste AI” cer verificare, nu înseamnă automat alocare greșită.
    </p>
  </div>
  <div className="overflow-x-auto">
    <table className="w-full min-w-[990px] table-fixed text-[11px]">
      <colgroup>
        <col className="w-[150px]" />
        <col className="w-[55px]" />
        <col className="w-[100px]" />
        <col className="w-[90px]" />
        <col className="w-[95px]" />
        <col className="w-[75px]" />
        <col className="w-[90px]" />
        <col className="w-[125px]" />
        <col className="w-[100px]" />
        <col className="w-[110px]" />
      </colgroup>
      <thead className="bg-slate-800 text-white dark:bg-slate-950">
        <tr>
          <th className="px-2 py-1.5 text-left">Manager</th>
          <th className="px-2 py-1.5 text-right">Loc.</th>
          <th className="px-2 py-1.5 text-right">Pondere target</th>
          <th className="px-2 py-1.5 text-right">Δ mix vs iulie</th>
          <th className="px-2 py-1.5 text-right">Target</th>
          <th className="px-2 py-1.5 text-right">vs iulie</th>
          <th className="px-2 py-1.5 text-right">vs sezonier</th>
          <th className="px-2 py-1.5 text-right" title="vs august anul trecut">vs aug. 2025</th>
          <th className="px-2 py-1.5 text-right">vs forecast AI</th>
          <th className="px-2 py-1.5 text-center">Semnal</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
        {regionalAllocation.map((item) => (
          <tr key={item.manager}>
            <td className="truncate whitespace-nowrap px-2 py-1.5 font-semibold text-slate-800 dark:text-slate-100" title={item.manager}>{item.manager}</td>
            <td className="px-2 py-1.5 text-right tabular-nums text-slate-600 dark:text-slate-300">{item.storeCount}</td>
            <td className="bg-amber-50 px-2 py-1.5 text-right font-semibold tabular-nums text-amber-800 dark:bg-amber-950/20 dark:text-amber-200">{formatPercent(item.targetShare)}</td>
            <td className={`px-2 py-1.5 text-right font-semibold tabular-nums ${percentTone(item.targetVsPreviousSharePp)}`}>{formatSignedPp(item.targetVsPreviousSharePp)}</td>
            <td className="px-2 py-1.5 text-right font-semibold tabular-nums text-slate-800 dark:text-slate-100">{formatTableNumber(item.target)}</td>
            <td className={`px-2 py-1.5 text-right font-semibold tabular-nums ${percentTone(item.targetVsPreviousPct)}`}>{formatSignedPercent(item.targetVsPreviousPct)}</td>
            <td className={`px-2 py-1.5 text-right font-semibold tabular-nums ${percentTone(item.targetVsSeasonalPct)}`}>{formatSignedPercent(item.targetVsSeasonalPct)}</td>
            <td className={`px-2 py-1.5 text-right font-semibold tabular-nums ${percentTone(item.targetVsPreviousYearPct)}`}>{formatSignedPercent(item.targetVsPreviousYearPct)}</td>
            <td className={`px-2 py-1.5 text-right font-semibold tabular-nums ${percentTone(item.targetVsForecastPct)}`}>{formatSignedPercent(item.targetVsForecastPct)}</td>
            <td className="px-2 py-1.5 text-center">
              <span className={`inline-flex whitespace-nowrap rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                item.signal === 'Peste AI'
                  ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300'
                  : item.signal === 'Peste sezonier'
                    ? 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300'
                    : 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300'
              }`}>{item.signal}</span>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  </div>
</div>
  );
}

