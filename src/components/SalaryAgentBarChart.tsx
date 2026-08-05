import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { SalaryAgentHistoryRecord } from '../api/salarii';

interface Props {
  data: SalaryAgentHistoryRecord[];
}

function formatMonth(year: number, month: number): string {
  const months = ['Ian', 'Feb', 'Mar', 'Apr', 'Mai', 'Iun', 'Iul', 'Aug', 'Sep', 'Oct', 'Noi', 'Dec'];
  return `${months[month - 1]}-${String(year).slice(2)}`;
}

function formatCurrency(val: unknown): string {
  if (val === undefined || val === null) return '0';
  const value = typeof val === 'string' ? parseFloat(val) : typeof val === 'number' ? val : Number(val);
  if (isNaN(value)) return '0';
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}K`;
  return value.toFixed(0);
}

const COLOR_MOBICELL = '#6366f1';
const COLOR_MOBIUP = '#10b981';

function SalaryTooltip({ active, payload, label }: {
  active?: boolean;
  payload?: Array<{ value?: unknown }>;
  label?: string | number;
}) {
  if (!active || !payload?.length) return null;
  const value = Number(payload[0]?.value ?? 0);

  return (
    <div className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs shadow-xl">
      <div className="mb-1 text-slate-300">{label}</div>
      <div className="font-medium text-white">
        Salariu: {value.toLocaleString('ro-RO')} RON
      </div>
    </div>
  );
}

export function SalaryAgentBarChart({ data }: Props) {
  const safeData = Array.isArray(data) ? data : [];
  const chartData = [...safeData]
    .sort((a, b) => a.year * 100 + a.month - (b.year * 100 + b.month))
    .map((r) => ({
      label: formatMonth(r.year, r.month),
      total_salary: r.total_salary,
      company: r.company_name,
    }));

  if (!chartData.length) {
    return (
      <div className="flex items-center justify-center h-40 text-slate-400 text-sm">
        Nu sunt date disponibile
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={180} minWidth={1} minHeight={1}>
      <BarChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
        <XAxis
          dataKey="label"
          tick={{ fontSize: 10, fill: '#94a3b8' }}
          tickLine={false}
          axisLine={{ stroke: '#e2e8f0' }}
        />
        <YAxis
          tickFormatter={formatCurrency}
          tick={{ fontSize: 10, fill: '#94a3b8' }}
          tickLine={false}
          axisLine={false}
          width={48}
        />
        <Tooltip
          content={<SalaryTooltip />}
          cursor={{ fill: 'rgba(15, 23, 42, 0.08)' }}
        />
        <Bar dataKey="total_salary" radius={[4, 4, 0, 0]}>
          {chartData.map((entry, index) => (
            <Cell
              key={`cell-${index}`}
              fill={entry.company === 'Mobicell' ? COLOR_MOBICELL : COLOR_MOBIUP}
            />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
