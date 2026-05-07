import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { SalaryEvolutionPoint } from '../api/salarii';

interface Props {
  data: SalaryEvolutionPoint[];
}

function formatCurrency(val: any): string {
  if (val === undefined || val === null) return '0';
  const value = typeof val === 'string' ? parseFloat(val) : val;
  if (isNaN(value)) return '0';
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(0)}K`;
  return value.toFixed(0);
}

const COLORS = {
  total: '#94a3b8',    // slate-400
  mobicell: '#6366f1', // indigo-500
  mobiup: '#10b981',   // emerald-500
};

export function SalaryAreaChart({ data }: Props) {
  const safeData = Array.isArray(data) ? data : [];
  if (!safeData.length) {
    return (
      <div className="flex items-center justify-center h-60 text-slate-400 text-sm">
        Nu sunt date disponibile
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={240} minWidth={1} minHeight={1}>
      <AreaChart data={safeData} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="gradientTotal" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor={COLORS.total} stopOpacity={0.15} />
            <stop offset="95%" stopColor={COLORS.total} stopOpacity={0.02} />
          </linearGradient>
          <linearGradient id="gradientMobicell" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor={COLORS.mobicell} stopOpacity={0.2} />
            <stop offset="95%" stopColor={COLORS.mobicell} stopOpacity={0.02} />
          </linearGradient>
          <linearGradient id="gradientMobiup" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor={COLORS.mobiup} stopOpacity={0.2} />
            <stop offset="95%" stopColor={COLORS.mobiup} stopOpacity={0.02} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
        <XAxis
          dataKey="month"
          tick={{ fontSize: 11, fill: '#94a3b8' }}
          tickLine={false}
          axisLine={{ stroke: '#e2e8f0' }}
        />
        <YAxis
          tickFormatter={formatCurrency}
          tick={{ fontSize: 11, fill: '#94a3b8' }}
          tickLine={false}
          axisLine={false}
          width={56}
        />
        <Tooltip
          formatter={(value: number) => [formatCurrency(value) + ' RON', '']}
          contentStyle={{
            background: '#1e293b',
            border: 'none',
            borderRadius: 8,
            color: '#fff',
            fontSize: 12,
          }}
          labelStyle={{ color: '#94a3b8', marginBottom: 4 }}
        />
        <Legend
          wrapperStyle={{ fontSize: 12, paddingTop: 12 }}
          formatter={(value) =>
            value === 'total' ? 'Total' : value === 'mobicell' ? 'Mobicell' : 'Mobiup'
          }
        />
        <Area
          type="monotone"
          dataKey="total"
          stroke={COLORS.total}
          strokeWidth={2}
          fill="url(#gradientTotal)"
          dot={false}
        />
        <Area
          type="monotone"
          dataKey="mobicell"
          stroke={COLORS.mobicell}
          strokeWidth={1.5}
          fill="url(#gradientMobicell)"
          dot={false}
        />
        <Area
          type="monotone"
          dataKey="mobiup"
          stroke={COLORS.mobiup}
          strokeWidth={1.5}
          fill="url(#gradientMobiup)"
          dot={false}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}
