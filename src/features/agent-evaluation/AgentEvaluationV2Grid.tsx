import type { AgentEvaluationV2Row } from '../../api/agents';
import { DataGrid, type DataGridColumn } from '../../components/common/DataGrid';
import type { ExportColumn } from '../../lib/tableExport';
import {
  FirmBadge,
  formatMoney,
  formatNumber,
  formatPct,
  MonthLabel,
} from './AgentEvaluationControls';
import {
  componentWeights,
  flagLabel,
  referenceLabel,
  score100Color,
  targetSourceLabel,
} from './AgentEvaluationTables';

type V2ColumnKey =
  | 'month'
  | 'agent'
  | 'total_sales'
  | 'total_score'
  | 'eligibility_status'
  | 'target_pct'
  | 'daily_vs_reference_pct'
  | 'bonuri_pct'
  | 'focus_pct'
  | 'premium_glass_pct'
  | 'value_reper'
  | 'trend_daily_pct';

export const V2_EXPORT_COLUMNS: ExportColumn<AgentEvaluationV2Row>[] = [
  { header: 'Luna', value: (row) => row.month, format: 'month' },
  { header: 'Firma', value: (row) => row.firma },
  { header: 'Agent', value: (row) => row.agent },
  { header: 'Magazin', value: (row) => row.locatie },
  { header: 'Vanzare', value: (row) => row.total_sales, format: 'currency' },
  { header: 'Scor', value: (row) => row.total_score, format: 'number' },
  { header: 'Rating', value: (row) => row.rating },
  { header: 'Status', value: (row) => row.eligibility_status },
  { header: 'Flaguri', value: (row) => row.confidence_flags.map(flagLabel).join(', ') },
  { header: '% Target', value: (row) => row.target_pct, format: 'percentPoints' },
  { header: 'Productivitate vs reper', value: (row) => row.daily_vs_reference_pct, format: 'percentPoints' },
  { header: 'Bon2Acc', value: (row) => row.bonuri_pct, format: 'percentPoints' },
  { header: 'Focus', value: (row) => row.focus_pct, format: 'percentPoints' },
  { header: 'Folii Premium', value: (row) => row.premium_glass_pct, format: 'percentPoints' },
  { header: 'Valoare reper', value: (row) => row.value_reper, format: 'number' },
  { header: 'Trend 3 luni', value: (row) => row.trend_daily_pct, format: 'percentPoints' },
];

function ComponentScore({
  value,
  score,
  weight,
  suffix = '%',
  sub,
}: {
  value: number | null;
  score: number | null;
  weight: number;
  suffix?: '%' | 'lei';
  sub?: string;
}) {
  const scoreClass = score === null
    ? 'text-slate-400'
    : score >= weight * 0.66
      ? 'text-green-600 dark:text-green-400'
      : score > 0
        ? 'text-amber-600 dark:text-amber-400'
        : 'text-red-600 dark:text-red-400';
  return <div className="text-right text-xs">
    <div className="font-medium text-slate-700 dark:text-slate-200">
      {suffix === 'lei' ? formatNumber(value, 0) : formatPct(value)}
    </div>
    {sub && <div className="text-[10px] text-slate-400">{sub}</div>}
    <div className={`text-[10px] font-semibold ${scoreClass}`}>
      {score === null ? '-' : `${Number(score).toFixed(1)}/${weight}`}
    </div>
  </div>;
}

function v2Columns(): DataGridColumn<AgentEvaluationV2Row, V2ColumnKey>[] {
  return [
    {
      key: 'month', label: 'Lună', value: (row) => row.month, defaultDirection: 'asc',
      filter: { kind: 'text', placeholder: 'Lună' },
      render: (row) => <span className="font-medium text-slate-600 dark:text-slate-300"><MonthLabel month={row.month} /></span>,
    },
    {
      key: 'agent', label: 'Agent', value: (row) => `${row.agent} ${row.locatie}`, defaultDirection: 'asc',
      searchValue: (row) => `${row.agent} ${row.locatie} ${row.firma}`,
      filter: { kind: 'text', placeholder: 'Agent / magazin' },
      render: (row) => <div className="min-w-[150px] max-w-[190px]">
        <div className="truncate font-semibold text-slate-800 dark:text-slate-100">{row.agent}</div>
        <div className="mt-0.5 flex min-w-0 items-center gap-1"><FirmBadge firma={row.firma} /><span className="truncate text-[10px] text-slate-400">{row.locatie}</span></div>
      </div>,
    },
    {
      key: 'total_sales', label: 'Vânzare', value: (row) => row.total_sales,
      filter: { kind: 'number' }, headerClassName: 'text-right', cellClassName: 'px-1.5 py-1 text-right align-middle',
      render: (row) => <div><div className="font-semibold text-slate-700 dark:text-slate-200">{formatMoney(row.total_sales)}</div><div className="text-[10px] text-slate-400">{row.working_days} zile · {row.receipt_count} bonuri</div></div>,
    },
    {
      key: 'total_score', label: 'Scor', value: (row) => row.total_score,
      filter: { kind: 'number', step: 0.1 }, headerClassName: 'text-right', cellClassName: 'px-1.5 py-1 text-right align-middle',
      render: (row) => <div className="whitespace-nowrap"><span className={`inline-flex rounded-full px-2 py-1 font-bold tabular-nums ${score100Color(row.total_score, row.eligibility_status)}`}>{row.total_score === null ? '-' : Number(row.total_score).toFixed(1)}</span><div className="mt-0.5 text-[10px] text-slate-400">{row.rating}</div></div>,
    },
    {
      key: 'eligibility_status', label: 'Status', value: (row) => row.eligibility_status, defaultDirection: 'asc',
      filter: { kind: 'enum', options: [{ value: 'eligibil', label: 'eligibil' }, { value: 'insuficient', label: 'insuficient' }] },
      searchValue: (row) => `${row.eligibility_status} ${row.confidence_flags.map(flagLabel).join(' ')}`,
      render: (row) => <div className="min-w-[145px]"><div className={`inline-flex rounded-full px-2 py-0.5 text-[10px] font-semibold ${row.eligibility_status === 'eligibil' ? 'bg-green-50 text-green-700 dark:bg-green-950/40 dark:text-green-300' : 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300'}`}>{row.eligibility_status}</div><div className="mt-1 flex max-w-[155px] flex-wrap gap-1">{row.confidence_flags.slice(0, 3).map((flag) => <span key={flag} className="rounded-full bg-slate-100 px-1.5 py-0.5 text-[9px] text-slate-500 dark:bg-slate-800 dark:text-slate-400">{flagLabel(flag)}</span>)}</div></div>,
    },
    {
      key: 'target_pct', label: 'Target', value: (row) => row.target_pct, filter: { kind: 'number', step: 0.1 },
      headerClassName: 'text-right', cellClassName: 'px-1.5 py-1 text-right align-middle',
      render: (row) => <ComponentScore value={row.target_pct} score={row.target_score} weight={componentWeights(row).target} sub={`${targetSourceLabel(row.target_source)} · punctaj lunar`} />,
    },
    {
      key: 'daily_vs_reference_pct', label: 'Productivitate', value: (row) => row.daily_vs_reference_pct, filter: { kind: 'number', step: 0.1 },
      headerClassName: 'text-right', cellClassName: 'px-1.5 py-1 text-right align-middle',
      render: (row) => <ComponentScore value={row.daily_vs_reference_pct} score={row.daily_score} weight={componentWeights(row).daily} sub={`${formatNumber(row.daily_average, 0)} lei/zi vs ${referenceLabel(row.daily_reference_type)}`} />,
    },
    {
      key: 'bonuri_pct', label: 'Bon2Acc', value: (row) => row.bonuri_pct, filter: { kind: 'number', step: 0.1 },
      headerClassName: 'text-right', cellClassName: 'px-1.5 py-1 text-right align-middle',
      render: (row) => <ComponentScore value={row.bonuri_pct} score={row.bonuri_score} weight={componentWeights(row).bonuri} />,
    },
    {
      key: 'focus_pct', label: 'Focus', value: (row) => row.focus_pct, filter: { kind: 'number', step: 0.1 },
      headerClassName: 'text-right', cellClassName: 'px-1.5 py-1 text-right align-middle',
      render: (row) => <ComponentScore value={row.focus_pct} score={row.focus_score} weight={componentWeights(row).focus} />,
    },
    {
      key: 'premium_glass_pct', label: 'Folii Premium', value: (row) => row.premium_glass_pct, filter: { kind: 'number', step: 0.1 },
      headerClassName: 'text-right', cellClassName: 'px-1.5 py-1 text-right align-middle',
      render: (row) => <ComponentScore value={row.premium_glass_pct} score={row.premium_glass_score} weight={componentWeights(row).premium} sub={`${row.premium_glass_qty}/${row.glass_qty}`} />,
    },
    {
      key: 'value_reper', label: 'Valoare reper', value: (row) => row.value_reper, filter: { kind: 'number' },
      headerClassName: 'text-right', cellClassName: 'px-1.5 py-1 text-right align-middle',
      render: (row) => <ComponentScore value={row.value_reper} score={row.value_reper_score} weight={componentWeights(row).value} suffix="lei" />,
    },
    {
      key: 'trend_daily_pct', label: 'Trend', value: (row) => row.trend_daily_pct, filter: { kind: 'number', step: 0.1 },
      headerClassName: 'text-right', cellClassName: 'px-1.5 py-1 text-right align-middle',
      render: (row) => {
        const trendClass = row.trend_direction === 'up'
          ? 'text-green-600 dark:text-green-400'
          : row.trend_direction === 'down'
            ? 'text-red-600 dark:text-red-400'
            : 'text-slate-500 dark:text-slate-400';
        return <div className="text-right"><div className={`font-semibold ${trendClass}`}>{row.trend_daily_pct === null ? '-' : `${Number(row.trend_daily_pct).toFixed(1)}%`}</div><div className="text-[10px] text-slate-400">vs 3 luni</div></div>;
      },
    },
  ];
}

const V2_COLUMNS = v2Columns();

export function AgentEvaluationV2Grid({ rows }: { rows: readonly AgentEvaluationV2Row[] }) {
  return <DataGrid<AgentEvaluationV2Row, V2ColumnKey>
    title="Punctaj 0–100"
    subtitle="Evaluare agenți"
    rows={rows}
    columns={V2_COLUMNS}
    initialSort={[{ key: 'total_score', direction: 'desc' }]}
    rowKey={(row) => `${row.month}:${row.site_code}:${row.agent}`}
    exportFilename="management_agenti_evaluare_noua"
    exportSheetName="Punctaj 0-100"
    exportColumns={V2_EXPORT_COLUMNS}
    emptyLabel="Fără agenți pentru filtrele selectate."
  />;
}
