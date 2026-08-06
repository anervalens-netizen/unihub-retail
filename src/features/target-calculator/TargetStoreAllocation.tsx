import { Fragment } from 'react';
import { CheckCircle2, ChevronDown, Download, PencilLine, RotateCcw, Save, X } from 'lucide-react';

import { formatCurrency, formatPercent } from '../../lib/formatters';
import {
  attainmentTone,
  flagLabel,
  formatTableNumber,
  monthLabel,
  profitabilityFlagLabel,
  shouldShowHistoricalTarget,
} from './model';
import type { TargetProfitability, TargetScenarioRow } from './api';
import type { TargetScenarioViewProps } from './TargetScenarioView';

const inputCls = 'rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300';
const finalInputCls = 'rounded-xl border-2 border-amber-300 bg-amber-50 px-3 py-2 text-sm font-semibold text-slate-800 focus:outline-none focus:ring-2 focus:ring-amber-400 dark:border-amber-600 dark:bg-amber-950/30 dark:text-slate-100';
const MISSING_PROFITABILITY: TargetProfitability = {
  agent_count: Number.NaN, base_salary_per_agent: Number.NaN, salary_cost_at_90_pct: Number.NaN,
  operating_costs: null, accessory_margin_pct: null, break_even_gross_sales: null, forecast_sales: null,
  anomaly_flags: ['PNL_INCOMPLETE'],
};
function profitabilityFor(row: TargetScenarioRow): TargetProfitability { return row.profitability ?? MISSING_PROFITABILITY; }
function isBelowBreakEven(row: TargetScenarioRow, value: number | null): boolean {
  const breakEven = profitabilityFor(row).break_even_gross_sales;
  return value != null && breakEven != null && value < breakEven;
}

export function TargetStoreAllocation({ model }: { model: TargetScenarioViewProps }) {
  const {
    context, busy, scenario, filteredRows, resetToProposal, handleSave, handleFinalize, handleExport,
    profitabilitySummary, locationFilterRef, locationDropdownOpen, setLocationDropdownOpen,
    selectedLocationCodes, selectedLocationSet, setSelectedLocationCodes, locationOptions,
    toggleLocationFilter, removeLocationFilter, displaySourceMonths, tableTotals, updateRow,
    setDetailSiteCode, regionalFilter, dirty,
  } = model;
  if (!scenario) return null;
  return (
<div className="glass rounded-2xl overflow-hidden">
  <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-4 py-3 dark:border-slate-700">
    <div>
      <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-100">Target + profitabilitate per locație</h3>
      <p className="text-xs text-slate-500">
        {filteredRows.length} locații afișate · <span className="font-semibold text-amber-700 dark:text-amber-300">Propunere manager</span> se salvează automat
      </p>
    </div>
    <div className="flex flex-wrap gap-2">
      {scenario.status === 'draft' && (
        <>
          {context?.can_finalize && (
            <button onClick={resetToProposal} disabled={busy} className="flex items-center gap-1.5 rounded-xl bg-slate-100 px-3 py-2 text-xs font-medium text-slate-600 hover:bg-slate-200 disabled:opacity-50 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700">
              <RotateCcw size={13} /> {regionalFilter === 'all' ? 'Reset propunere' : 'Reset manager'}
            </button>
          )}
          <button onClick={handleSave} disabled={busy || !dirty} className="flex items-center gap-1.5 rounded-xl bg-indigo-100 px-3 py-2 text-xs font-medium text-indigo-700 hover:bg-indigo-200 disabled:opacity-50 dark:bg-indigo-900/30 dark:text-indigo-300">
            <Save size={13} /> Salveaza acum
          </button>
          {context?.can_finalize && (
            <button onClick={handleFinalize} disabled={busy} className="flex items-center gap-1.5 rounded-xl bg-emerald-600 px-3 py-2 text-xs font-medium text-white hover:bg-emerald-700 disabled:opacity-50">
              <CheckCircle2 size={13} /> Finalizeaza
            </button>
          )}
        </>
      )}
      {context?.can_finalize && (
        <button onClick={handleExport} disabled={busy} className="flex items-center gap-1.5 rounded-xl bg-slate-900 px-3 py-2 text-xs font-medium text-white hover:bg-slate-700 disabled:opacity-50 dark:bg-slate-100 dark:text-slate-900">
          <Download size={13} /> Export Excel
        </button>
      )}
    </div>
  </div>

  {profitabilitySummary && profitabilitySummary.status !== 'ready' && (
    <div className="border-b border-amber-200 bg-amber-50 px-4 py-2 text-xs text-amber-800 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-200">
      Surse financiare parțiale: P&amp;L {profitabilitySummary.pnl_store_count}/{scenario.store_count} magazine · forecast {profitabilitySummary.forecast_store_count}/{scenario.store_count}. Valorile lipsă rămân marcate, nu sunt estimate.
    </div>
  )}

  <div className="border-b border-slate-100 px-4 py-3 dark:border-slate-800">
    <div ref={locationFilterRef} className="flex flex-col gap-3 lg:flex-row lg:items-end">
      <div className="relative min-w-0 flex-1 space-y-1 text-xs font-medium text-slate-500 lg:max-w-sm">
        <span>Selecteaza locatie</span>
        <button
          type="button"
          onClick={() => setLocationDropdownOpen((current) => !current)}
          className={`${inputCls} flex w-full items-center justify-between gap-2 text-left`}
        >
          <span className="truncate">
            {selectedLocationCodes.length > 0
              ? `${selectedLocationCodes.length} locatii selectate`
              : 'Adauga locatie...'}
          </span>
          <ChevronDown size={14} className={`shrink-0 text-slate-400 transition-transform ${locationDropdownOpen ? 'rotate-180' : ''}`} />
        </button>
        {locationDropdownOpen && (
          <div className="absolute left-0 right-0 top-full z-30 mt-2 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-xl dark:border-slate-700 dark:bg-slate-900">
            <div className="flex items-center justify-between gap-2 border-b border-slate-100 px-3 py-2 dark:border-slate-800">
              <span className="text-[11px] text-slate-400">{selectedLocationCodes.length} selectate</span>
              {selectedLocationCodes.length > 0 && (
                <button
                  type="button"
                  onClick={() => setSelectedLocationCodes([])}
                  className="text-[11px] font-semibold text-indigo-600 hover:text-indigo-700 dark:text-indigo-300"
                >
                  Goleste
                </button>
              )}
            </div>
            <div className="max-h-72 overflow-y-auto p-1">
              {locationOptions.length === 0 && (
                <p className="px-3 py-3 text-xs text-slate-400">Nu exista locatii disponibile.</p>
              )}
              {locationOptions.map((row) => (
                <label
                  key={row.site_code}
                  className="flex cursor-pointer items-start gap-2 rounded-xl px-3 py-2 text-xs hover:bg-slate-50 dark:hover:bg-slate-800"
                >
                  <input
                    type="checkbox"
                    checked={selectedLocationSet.has(row.site_code)}
                    onChange={() => toggleLocationFilter(row.site_code)}
                    className="mt-0.5 h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                  />
                  <span className="min-w-0">
                    <span className="block truncate font-semibold text-slate-700 dark:text-slate-200">{row.locatie}</span>
                    <span className="block truncate text-[10px] text-slate-400">{row.site_code} · {row.firma}</span>
                  </span>
                </label>
              ))}
            </div>
          </div>
        )}
      </div>
      {selectedLocationCodes.length > 0 && (
        <button
          onClick={() => setSelectedLocationCodes([])}
          className="rounded-xl bg-slate-100 px-3 py-2 text-xs font-medium text-slate-600 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-300"
        >
          Toate locatiile
        </button>
      )}
    </div>
    {selectedLocationCodes.length > 0 && (
      <div className="mt-3 flex flex-wrap gap-2">
        {selectedLocationCodes.map((siteCode) => {
          const row = locationOptions.find((item) => item.site_code === siteCode);
          if (!row) return null;
          return (
            <button
              key={siteCode}
              onClick={() => removeLocationFilter(siteCode)}
              className="inline-flex items-center gap-1 rounded-full bg-indigo-50 px-3 py-1 text-xs font-medium text-indigo-700 hover:bg-indigo-100 dark:bg-indigo-900/30 dark:text-indigo-300"
            >
              {row.locatie}
              <X size={12} />
            </button>
          );
        })}
      </div>
    )}
  </div>

  <div className="space-y-3 p-3 md:hidden">
    {filteredRows.map((row) => (
      <div key={row.site_code} className="rounded-2xl border border-slate-200 bg-white p-3 shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <button
          onClick={() => setDetailSiteCode(row.site_code)}
          className="text-left"
        >
          <p className="font-semibold text-slate-800 underline decoration-dotted underline-offset-4 dark:text-slate-100">{row.locatie}</p>
          <p className="mt-0.5 text-[11px] text-slate-400">{row.site_code} · {row.firma} · {row.regional}</p>
        </button>
        <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
          <div className={`rounded-xl p-2 ${
            isBelowBreakEven(row, row.proposed_target)
              ? 'bg-red-50 dark:bg-red-950/25'
              : 'bg-slate-50 dark:bg-slate-800/60'
          }`}>
            <p className="text-[10px] uppercase tracking-wide text-slate-400">Calcul target</p>
            <p className={`font-semibold ${
              isBelowBreakEven(row, row.proposed_target)
                ? 'text-red-600 dark:text-red-400'
                : 'text-indigo-600 dark:text-indigo-300'
            }`}>{formatCurrency(row.proposed_target)}</p>
          </div>
          <label className="rounded-xl border border-amber-200 bg-amber-50 p-2 dark:border-amber-900 dark:bg-amber-950/20">
            <span className="text-[10px] font-semibold uppercase tracking-wide text-amber-700 dark:text-amber-300">Propunere manager</span>
            <input
              type="number"
              min="0"
              disabled={scenario.status === 'finalized'}
              className={`${finalInputCls} mt-1 w-full text-right tabular-nums disabled:opacity-70`}
              value={row.final_target ?? ''}
              placeholder="Completeaza"
              onChange={(event) => updateRow(row.site_code, 'final_target', event.target.value === '' ? null : Number(event.target.value))}
            />
          </label>
        </div>
        <div className="mt-2 grid grid-cols-3 gap-2 text-[11px]">
          {displaySourceMonths.map((source) => {
            const period = row.history.find((history) => history.month === source.month);
            const showTarget = shouldShowHistoricalTarget(source);
            return (
              <div key={source.month} className="rounded-xl bg-slate-50 p-2 text-slate-600 dark:bg-slate-800/60 dark:text-slate-300">
                <p className="font-semibold">{monthLabel(source.month)}</p>
                {showTarget && <p>T {formatTableNumber(period?.target)}</p>}
                <p className="text-slate-400">R {formatTableNumber(period?.realized)}</p>
                <p className={attainmentTone(period?.attainment_pct)}>
                  {period?.attainment_pct == null ? '-' : formatPercent(period.attainment_pct)}
                </p>
              </div>
            );
          })}
        </div>
        <div className="mt-2 grid grid-cols-2 gap-2 text-[11px]">
          <div className="rounded-xl bg-slate-50 p-2 dark:bg-slate-800/60">
            <p className="text-slate-400">Cheltuieli salariale</p>
            <p className="font-semibold text-slate-700 dark:text-slate-200">{formatTableNumber(profitabilityFor(row).salary_cost_at_90_pct)}</p>
          </div>
          <div className="rounded-xl bg-slate-50 p-2 dark:bg-slate-800/60">
            <p className="text-slate-400">Cheltuieli operaționale</p>
            <p className="font-semibold text-slate-700 dark:text-slate-200">{formatTableNumber(profitabilityFor(row).operating_costs)}</p>
          </div>
          <div className="rounded-xl bg-orange-50 p-2 dark:bg-orange-950/20">
            <p className="text-orange-700 dark:text-orange-300">Break-even brut</p>
            <p className="font-semibold text-orange-800 dark:text-orange-200">{formatTableNumber(profitabilityFor(row).break_even_gross_sales)}</p>
          </div>
          <div className={`rounded-xl p-2 ${
            isBelowBreakEven(row, profitabilityFor(row).forecast_sales)
              ? 'bg-red-50 dark:bg-red-950/25'
              : 'bg-emerald-50 dark:bg-emerald-950/20'
          }`}>
            <p className="text-slate-500 dark:text-slate-300">Forecast</p>
            <p className={`font-semibold ${
              isBelowBreakEven(row, profitabilityFor(row).forecast_sales)
                ? 'text-red-600 dark:text-red-400'
                : 'text-emerald-600 dark:text-emerald-400'
            }`}>{formatTableNumber(profitabilityFor(row).forecast_sales)}</p>
          </div>
        </div>
        {[...(row.calculation_details.flags ?? []), ...profitabilityFor(row).anomaly_flags].length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1">
            {(row.calculation_details.flags ?? []).slice(0, 2).map((flag) => (
              <span key={flag} className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-semibold text-amber-700 dark:bg-amber-900/30 dark:text-amber-300">
                {flagLabel(flag)}
              </span>
            ))}
            {profitabilityFor(row).anomaly_flags.map((flag) => (
              <span key={flag} className="rounded-full bg-red-100 px-2 py-0.5 text-[10px] font-semibold text-red-700 dark:bg-red-900/30 dark:text-red-300">
                {profitabilityFlagLabel(flag)}
              </span>
            ))}
          </div>
        )}
        <div className="mt-2 flex items-center justify-between gap-2 text-xs">
          <span className="text-slate-400">Delta</span>
          <span className={`font-semibold ${
            row.final_target == null
              ? 'text-amber-600'
              : row.final_target - row.proposed_target > 0.01
                ? 'text-emerald-600'
                : row.final_target - row.proposed_target < -0.01
                  ? 'text-red-600'
                  : 'text-slate-400'
          }`}>
            {row.final_target == null ? 'Necompletat' : formatCurrency(row.final_target - row.proposed_target)}
          </span>
        </div>
        <input
          disabled={scenario.status === 'finalized'}
          className={`${inputCls} mt-2 w-full disabled:opacity-70`}
          placeholder="Observatii"
          value={row.note ?? ''}
          onChange={(event) => updateRow(row.site_code, 'note', event.target.value)}
        />
      </div>
    ))}
  </div>

  <div className="compact-data-table hidden overflow-x-auto md:block">
    <table className="w-full min-w-[1610px] table-fixed text-[10px] leading-tight">
      <colgroup>
        <col className="w-[60px]" />
        <col className="w-[88px]" />
        <col className="w-[165px]" />
        <col className="w-[78px]" />
        {displaySourceMonths.map((period) => (
          <Fragment key={period.month}>
            <col className="w-[68px]" />
            <col className="w-[70px]" />
            <col className="w-[50px]" />
          </Fragment>
        ))}
        <col className="w-[62px]" />
        <col className="w-[78px]" />
        <col className="w-[160px]" />
        <col className="w-[90px]" />
        <col className="w-[90px]" />
        <col className="w-[92px]" />
        <col className="w-[82px]" />
      </colgroup>
      <thead>
        <tr className="bg-blue-100 font-bold text-slate-800 dark:bg-blue-950/50 dark:text-slate-100">
          <th className="px-1.5 py-1 text-left">SUBTOTAL</th>
          <th colSpan={3} />
          {tableTotals.history.map((period) => (
            <Fragment key={period.month}>
              <th className="px-1 py-1 text-right tabular-nums">{formatTableNumber(period.target)}</th>
              <th className="px-1 py-1 text-right tabular-nums">{formatTableNumber(period.realized)}</th>
              <th className={`px-1 py-1 text-right tabular-nums ${attainmentTone(period.attainment)}`}>
                {period.attainment == null ? '-' : formatPercent(period.attainment)}
              </th>
            </Fragment>
          ))}
          <th className="px-1 py-1 text-right tabular-nums">{formatPercent(tableTotals.normalizedWeight * 100)}</th>
          <th className="px-1 py-1 text-right tabular-nums">{formatTableNumber(tableTotals.proposedTarget)}</th>
          <th className="bg-amber-50 px-1 py-1 text-right tabular-nums dark:bg-amber-950/20">{formatTableNumber(tableTotals.finalTarget)}</th>
          <th className="px-1 py-1 text-right tabular-nums">{formatTableNumber(tableTotals.salary)}</th>
          <th className="px-1 py-1 text-right tabular-nums">{formatTableNumber(tableTotals.operatingCosts)}</th>
          <th className="bg-orange-50 px-1 py-1 text-right tabular-nums dark:bg-orange-950/20">{formatTableNumber(tableTotals.breakEven)}</th>
          <th className={`px-1 py-1 text-right tabular-nums ${
            tableTotals.forecast != null
            && tableTotals.breakEven != null
            && tableTotals.forecast < tableTotals.breakEven
              ? 'bg-red-100 text-red-700 dark:bg-red-950/30 dark:text-red-300'
              : 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/20 dark:text-emerald-300'
          }`}>{formatTableNumber(tableTotals.forecast)}</th>
        </tr>
        <tr className="bg-slate-800 text-white dark:bg-slate-950">
          <th className="px-1 py-1 text-left font-semibold">Firma</th>
          <th className="px-1 py-1 text-left font-semibold">Manager</th>
          <th className="px-1 py-1 text-left font-semibold">Nume locație</th>
          <th className="px-1 py-1 text-left font-semibold">Cod</th>
          {displaySourceMonths.map((period) => (
            <Fragment key={period.month}>
              <th className="px-1 py-1 text-right font-semibold">Target<br />{period.month}</th>
              <th className="px-1 py-1 text-right font-semibold">Realizat<br />{period.month}</th>
              <th className="px-1 py-1 text-right font-semibold">%<br />{period.month}</th>
            </Fragment>
          ))}
          <th className="px-1 py-1 text-right font-semibold">Pondere</th>
          <th className="px-1 py-1 text-right font-semibold">Calcul<br />{monthLabel(scenario.target_month)}</th>
          <th className="bg-red-900 px-1 py-1 text-right font-semibold">
            <span className="flex items-center justify-end gap-1"><PencilLine size={12} /> Propunere manager</span>
          </th>
          <th className="px-1 py-1 text-right font-semibold" title="Cheltuieli salariale la 90% - P&L estimat">Salarii<br />90%</th>
          <th className="px-1 py-1 text-right font-semibold" title="Cheltuieli operaționale estimate">OPEX<br />estimat</th>
          <th className="px-1 py-1 text-right font-semibold" title="Break-even vânzări brute">Break-even<br />brut</th>
          <th className="px-1 py-1 text-right font-semibold">Forecast<br />{monthLabel(scenario.target_month)}</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
        {filteredRows.map((row) => (
          <tr key={row.site_code}>
            <td className="whitespace-nowrap px-1.5 py-1 text-slate-600 dark:text-slate-300">{row.firma}</td>
            <td className="truncate whitespace-nowrap px-1.5 py-1 text-slate-600 dark:text-slate-300" title={row.regional}>{row.regional}</td>
            <td
              className={`px-1.5 py-1 ${
                profitabilityFor(row).anomaly_flags.includes('PNL_INCOMPLETE')
                  ? 'bg-red-50 dark:bg-red-950/20'
                  : ''
              }`}
              title={
                profitabilityFor(row).anomaly_flags.length > 0
                  ? `Anomalii: ${profitabilityFor(row).anomaly_flags.map(profitabilityFlagLabel).join(', ')}`
                  : undefined
              }
            >
              <button
                onClick={() => setDetailSiteCode(row.site_code)}
                className="block max-w-full truncate text-left font-medium leading-tight text-slate-800 underline decoration-dotted underline-offset-4 hover:text-indigo-600 dark:text-slate-200 dark:hover:text-indigo-300"
              >
                {row.locatie}
              </button>
            </td>
            <td className="truncate whitespace-nowrap px-1.5 py-1 text-slate-500 dark:text-slate-400" title={row.site_code}>{row.site_code}</td>
            {displaySourceMonths.map((source) => {
              const period = row.history.find((history) => history.month === source.month);
              return (
                <Fragment key={source.month}>
                  <td className="px-1.5 py-1 text-right tabular-nums text-slate-500 dark:text-slate-400">{formatTableNumber(period?.target)}</td>
                  <td className="px-1.5 py-1 text-right tabular-nums text-slate-700 dark:text-slate-200">{formatTableNumber(period?.realized)}</td>
                  <td className={`px-1.5 py-1 text-right tabular-nums ${attainmentTone(period?.attainment_pct)}`}>
                    {period?.attainment_pct == null ? '-' : formatPercent(period.attainment_pct)}
                  </td>
                </Fragment>
              );
            })}
            <td className="px-1.5 py-1 text-right tabular-nums text-slate-600 dark:text-slate-300">
              {formatPercent(row.normalized_weight == null ? null : row.normalized_weight * 100)}
            </td>
            <td className={`px-1.5 py-1 text-right font-semibold tabular-nums ${
              isBelowBreakEven(row, row.proposed_target)
                ? 'bg-red-50 text-red-600 dark:bg-red-950/20 dark:text-red-400'
                : 'text-slate-800 dark:text-slate-100'
            }`}>
              {formatTableNumber(row.proposed_target)}
            </td>
            <td className="border-x border-amber-100 bg-amber-50/50 px-1 py-0.5 text-right dark:border-amber-900 dark:bg-amber-950/10">
              <div className="flex items-center justify-end gap-1">
              <input
                type="number"
                min="0"
                disabled={scenario.status === 'finalized'}
                className="h-7 w-[72px] rounded-md border border-amber-300 bg-amber-50 px-1 text-right text-[10px] font-semibold tabular-nums text-slate-800 focus:outline-none focus:ring-1 focus:ring-amber-400 disabled:opacity-70 dark:border-amber-600 dark:bg-amber-950/30 dark:text-slate-100"
                value={row.final_target ?? ''}
                placeholder="Completeaza"
                onChange={(event) => updateRow(row.site_code, 'final_target', event.target.value === '' ? null : Number(event.target.value))}
              />
              <input
                disabled={scenario.status === 'finalized'}
                className="h-7 w-[78px] rounded-md border border-slate-200 bg-white px-1 text-[10px] text-slate-700 focus:outline-none focus:ring-1 focus:ring-indigo-500 disabled:opacity-70 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300"
                placeholder="Observație"
                title="Observație manager"
                value={row.note ?? ''}
                onChange={(event) => updateRow(row.site_code, 'note', event.target.value)}
              />
              </div>
            </td>
            <td className="px-1.5 py-1 text-right tabular-nums text-slate-700 dark:text-slate-200">{formatTableNumber(profitabilityFor(row).salary_cost_at_90_pct)}</td>
            <td className="px-1.5 py-1 text-right tabular-nums text-slate-700 dark:text-slate-200">{formatTableNumber(profitabilityFor(row).operating_costs)}</td>
            <td className="bg-orange-50 px-1.5 py-1 text-right font-semibold tabular-nums text-orange-800 dark:bg-orange-950/20 dark:text-orange-200">{formatTableNumber(profitabilityFor(row).break_even_gross_sales)}</td>
            <td className={`px-1.5 py-1 text-right font-semibold tabular-nums ${
              profitabilityFor(row).forecast_sales == null
                ? 'text-slate-400'
                : isBelowBreakEven(row, profitabilityFor(row).forecast_sales)
                  ? 'bg-red-50 text-red-600 dark:bg-red-950/20 dark:text-red-400'
                  : profitabilityFor(row).anomaly_flags.includes('FORECAST_BELOW_TARGET')
                    ? 'bg-amber-50 text-amber-700 dark:bg-amber-950/20 dark:text-amber-300'
                  : 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/20 dark:text-emerald-300'
            }`}>{formatTableNumber(profitabilityFor(row).forecast_sales)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  </div>
</div>
  );
}

