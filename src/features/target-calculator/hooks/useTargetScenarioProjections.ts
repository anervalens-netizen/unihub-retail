import { useMemo } from 'react';

import { shiftMonth } from '../../../lib/dates';
import type { TargetCalculatorContext, TargetProfitability, TargetScenario, TargetScenarioRow } from '../api';
import { monthLabel, percentChangeValue, shouldShowHistoricalTarget, sum } from '../model';

const MISSING_PROFITABILITY: TargetProfitability = {
  agent_count: Number.NaN, base_salary_per_agent: Number.NaN,
  salary_cost_at_90_pct: Number.NaN, operating_costs: null,
  accessory_margin_pct: null, break_even_gross_sales: null,
  forecast_sales: null, anomaly_flags: ['PNL_INCOMPLETE'],
};
const profitabilityFor = (row: TargetScenarioRow) => row.profitability ?? MISSING_PROFITABILITY;

type ProjectionInput = {
  scenario: TargetScenario | null;
  context: TargetCalculatorContext | null;
  regionalFilter: string;
  selectedLocationCodes: string[];
};

function useTargetRows(input: ProjectionInput) {
  const { scenario, context, regionalFilter, selectedLocationCodes } = input;
  const regionals = useMemo(
    () => scenario?.regional_summary.map((item) => item.regional) ?? context?.regionals ?? [],
    [context, scenario],
  );
  const baseRows = useMemo(
    () => scenario?.rows.filter((row) => regionalFilter === 'all' || row.regional === regionalFilter) ?? [],
    [regionalFilter, scenario],
  );
  const locationOptions = useMemo(
    () => baseRows.slice().sort((left, right) => left.locatie.localeCompare(right.locatie)),
    [baseRows],
  );
  const selectedLocationSet = useMemo(() => new Set(selectedLocationCodes), [selectedLocationCodes]);
  const filteredRows = useMemo(
    () => baseRows.filter((row) => selectedLocationSet.size === 0 || selectedLocationSet.has(row.site_code)),
    [baseRows, selectedLocationSet],
  );
  const displaySourceMonths = useMemo(() => {
    if (!scenario) return [];
    return [-13, -12, -1].map((offset) => {
      const month = shiftMonth(scenario.target_month, offset);
      return scenario.source_months.find((period) => period.month === month) ?? {
        month, label: monthLabel(month),
        role: offset === -1 ? 'floor_reference' : 'previous_year_reference',
      };
    });
  }, [scenario]);
  const tableTotals = useMemo(() => {
    const history = displaySourceMonths.map((source) => {
      const periods = filteredRows.map((row) => row.history.find((item) => item.month === source.month));
      const target = sum(periods.map((item) => item?.target ?? 0));
      const realized = sum(periods.map((item) => item?.realized ?? 0));
      return { month: source.month, target, realized, attainment: target > 0 ? realized * 100 / target : null };
    });
    const completeTotal = (selector: (row: TargetScenarioRow) => number | null | undefined) => {
      const values = filteredRows.map(selector);
      return values.every((value) => value != null) ? sum(values.map(Number)) : null;
    };
    return {
      history,
      normalizedWeight: filteredRows.reduce((total, row) => total + (row.normalized_weight ?? 0), 0),
      proposedTarget: sum(filteredRows.map((row) => row.proposed_target)),
      finalTarget: filteredRows.length > 0 && filteredRows.every((row) => row.final_target != null) ? sum(filteredRows.map((row) => Number(row.final_target))) : null,
      salary: sum(filteredRows.map((row) => profitabilityFor(row).salary_cost_at_90_pct)),
      operatingCosts: completeTotal((row) => profitabilityFor(row).operating_costs),
      breakEven: completeTotal((row) => profitabilityFor(row).break_even_gross_sales),
      forecast: completeTotal((row) => profitabilityFor(row).forecast_sales),
    };
  }, [displaySourceMonths, filteredRows]);
  return { regionals, locationOptions, selectedLocationSet, filteredRows, displaySourceMonths, tableTotals };
}

function useTargetCharts(input: ProjectionInput, rows: ReturnType<typeof useTargetRows>) {
  const { scenario, regionalFilter } = input;
  const sourceChart = useMemo(() => {
    if (!scenario) return [];
    return rows.displaySourceMonths.map((source) => {
      const values = rows.filteredRows.map((row) => row.history.find((history) => history.month === source.month));
      const showTarget = shouldShowHistoricalTarget(source);
      return {
        month: monthLabel(source.month),
        target: showTarget ? sum(values.map((value) => value?.target ?? 0)) : 0,
        realized: sum(values.map((value) => value?.realized ?? 0)),
        actualRealized: sum(values.map((value) => value?.actual_realized ?? value?.realized ?? 0)),
        isForecast: values.some((value) => value?.is_forecast), showTarget,
      };
    });
  }, [rows.displaySourceMonths, rows.filteredRows, scenario]);
  const regionalChart = useMemo(
    () => scenario?.regional_summary.filter((item) => regionalFilter === 'all' || item.regional === regionalFilter) ?? [],
    [regionalFilter, scenario],
  );
  return { sourceChart, regionalChart };
}

function useRegionalAllocation(scenario: TargetScenario | null) {
  return useMemo(() => {
    if (!scenario) return [];
    const previousYearBaseMonth = shiftMonth(scenario.target_month, -13);
    const previousYearTargetMonth = shiftMonth(scenario.target_month, -12);
    const previousMonth = shiftMonth(scenario.target_month, -1);
    const groups = new Map<string, TargetScenarioRow[]>();
    scenario.rows.forEach((row) => groups.set(row.regional, [...(groups.get(row.regional) ?? []), row]));
    const aggregate = (manager: string, rows: TargetScenarioRow[]) => {
      const realized = (row: TargetScenarioRow, month: string) => row.history.find((period) => period.month === month)?.realized ?? 0;
      const target = sum(rows.map((row) => row.proposed_target));
      const previous = sum(rows.map((row) => realized(row, previousMonth)));
      const previousYearBase = sum(rows.map((row) => realized(row, previousYearBaseMonth)));
      const previousYearTarget = sum(rows.map((row) => realized(row, previousYearTargetMonth)));
      const forecastValues = rows.map((row) => profitabilityFor(row).forecast_sales);
      const forecast = forecastValues.every((value) => value != null) ? sum(forecastValues.map(Number)) : null;
      const seasonalityPct = percentChangeValue(previousYearTarget, previousYearBase);
      const seasonalTarget = seasonalityPct == null ? null : previous * (1 + seasonalityPct / 100);
      const targetVsSeasonalPct = seasonalTarget == null ? null : percentChangeValue(target, seasonalTarget);
      const targetVsForecastPct = forecast == null ? null : percentChangeValue(target, forecast);
      const signal = targetVsForecastPct != null && targetVsForecastPct >= 5 ? 'Peste AI' : targetVsSeasonalPct != null && Math.round(targetVsSeasonalPct * 10) / 10 >= 3 ? 'Peste sezonier' : 'Echilibrat';
      return {
        manager, storeCount: rows.length, target, previous, previousYearTarget,
        forecast, seasonalityPct, seasonalTarget,
        targetVsPreviousPct: percentChangeValue(target, previous), targetVsSeasonalPct,
        targetVsPreviousYearPct: percentChangeValue(target, previousYearTarget),
        targetVsForecastPct, signal,
      };
    };
    const network = aggregate('Rețea', scenario.rows);
    return Array.from(groups.entries()).map(([manager, rows]) => {
      const item = aggregate(manager, rows);
      const targetShare = network.target > 0 ? item.target * 100 / network.target : 0;
      const previousShare = network.previous > 0 ? item.previous * 100 / network.previous : 0;
      const previousYearShare = network.previousYearTarget > 0 ? item.previousYearTarget * 100 / network.previousYearTarget : 0;
      const forecastShare = item.forecast != null && network.forecast ? item.forecast * 100 / network.forecast : null;
      return {
        ...item, targetShare, targetVsPreviousSharePp: targetShare - previousShare,
        targetVsPreviousYearSharePp: targetShare - previousYearShare,
        targetVsForecastSharePp: forecastShare == null ? null : targetShare - forecastShare,
      };
    }).sort((left, right) => right.target - left.target);
  }, [scenario]);
}

function useScenarioLabels(scenario: TargetScenario | null) {
  const activeSeasonalityLabel = useMemo(() => {
    const years = Number(scenario?.calculation_params?.seasonality_years ?? 1);
    return years > 1 ? `Multi-year ${years} ani` : 'Sezonalitate anul trecut';
  }, [scenario]);
  const displayWarnings = useMemo(
    () => scenario?.warnings.filter((warning) => {
      if (warning.startsWith('Formula foloseste sezonalitate')) return false;
      if (warning.startsWith('Perioada ') && warning.includes('forecastate')) return false;
      return !['2023-06', '2023-07'].some((month) => warning.includes(month));
    }) ?? [],
    [scenario],
  );
  return { activeSeasonalityLabel, displayWarnings };
}

export function useTargetScenarioProjections(input: ProjectionInput) {
  const rows = useTargetRows(input);
  const charts = useTargetCharts(input, rows);
  const regionalAllocation = useRegionalAllocation(input.scenario);
  const labels = useScenarioLabels(input.scenario);
  return { ...rows, ...charts, regionalAllocation, ...labels };
}
