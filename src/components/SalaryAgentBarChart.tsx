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

function formatCurrency(val: any): string {
  if (val === undefined || val === null) return '0';
  const value = typeof val === 'string' ? parseFloat(val) : val;
  if (isNaN(value)) return '0';
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}K`;
  return value.toFixed(0);
}

const COLOR_MOBICELL = '#6366f1';
const COLOR_MOBIUP = '#10b981';

export function SalaryAgentBarChart({ data }: Props) {
  const safeData = Array.isArray(data) ? data : [];
  const chartData = safeData.map((r) => ({
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
    <ResponsiveContainer width="100%" height={180} minWidth={0}>
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
          formatter={(value: number) => [`${value.toLocaleString()} RON`, 'Salariu']}
          contentStyle={{
            background: '#1e293b',
            border: 'none',
            borderRadius: 8,
            color: '#fff',
            fontSize: 12,
          }}
          labelStyle={{ color: '#94a3b8', marginBottom: 4 }}
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
