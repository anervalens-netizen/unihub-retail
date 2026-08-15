import type { ReactNode } from 'react';
import {
  BadgePercent,
  Building2,
  CalendarDays,
  Gift,
  Sparkles,
  Tag,
} from 'lucide-react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { CampaignsPromotionsResponse } from '../api/generated/runtime-types';
import { formatCurrency, formatInt } from '../lib/formatters';
import type { ExportColumn } from '../lib/tableExport';
import { ExportTableButton } from './ExportTableButton';
import { IncentiveQualificationSummary } from './IncentiveQualificationSummary';

interface IncentiveDesktopHeaderProps {
  promoData: CampaignsPromotionsResponse | null;
  months: string[];
  value: string;
  onChange: (month: string) => void;
  currentMonth: string;
  sectionLabel?: string;
  title?: string;
  description?: string;
}

function monthLabel(month: string): string {
  const [year, monthNumber] = month.split('-').map(Number);
  if (!year || !monthNumber) return month;
  return new Intl.DateTimeFormat('ro-RO', {
    month: 'long',
    year: 'numeric',
    timeZone: 'UTC',
  }).format(new Date(Date.UTC(year, monthNumber - 1, 1)));
}

export function IncentiveDesktopHeader({
  promoData,
  months,
  value,
  onChange,
  currentMonth,
  sectionLabel = 'Incentive',
  title = 'Incentive',
  description,
}: IncentiveDesktopHeaderProps) {
  return (
    <section className="hidden items-start justify-between gap-6 rounded-2xl border border-slate-200/80 bg-white/85 px-5 py-4 shadow-sm backdrop-blur lg:flex dark:border-slate-800 dark:bg-slate-900/80">
      <div className="min-w-0">
        <div className="mb-1 flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.16em] text-indigo-600 dark:text-indigo-300">
          <span>Focus</span>
          <span className="text-slate-300 dark:text-slate-600">/</span>
          <span>{sectionLabel}</span>
        </div>
        <h1 className="text-2xl font-black tracking-tight text-slate-950 dark:text-white">
          {title} — <span className="capitalize">{monthLabel(value)}</span>
        </h1>
        <p className="mt-1 max-w-3xl text-xs text-slate-500 dark:text-slate-400">
          {description || promoData?.incentive_description || 'Performanța programelor de incentive și situația calificării curente.'}
        </p>
      </div>
      <label className="shrink-0">
        <span className="mb-1 block text-[10px] font-bold uppercase tracking-[0.16em] text-slate-400">Perioada</span>
        <select
          value={value}
          onChange={(event) => onChange(event.target.value)}
          className="min-w-44 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-bold text-slate-700 shadow-xs outline-none transition focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:focus:ring-indigo-950"
        >
          {months.map((month) => (
            <option key={month} value={month}>
              {monthLabel(month)}{month === currentMonth ? ' · curent' : ''}
            </option>
          ))}
        </select>
      </label>
    </section>
  );
}

function KpiCard({
  icon,
  label,
  value,
  tone,
}: {
  icon: ReactNode;
  label: string;
  value: string;
  tone: string;
}) {
  return (
    <div className="min-w-0 rounded-2xl border border-slate-200/80 bg-white/90 px-4 py-3 shadow-sm dark:border-slate-800 dark:bg-slate-900/80">
      <div className="flex items-center gap-2">
        <span className={'flex h-8 w-8 shrink-0 items-center justify-center rounded-xl ' + tone}>{icon}</span>
        <div className="min-w-0">
          <div className="truncate text-[10px] font-bold uppercase tracking-[0.12em] text-slate-400">{label}</div>
          <div className="mt-0.5 truncate text-xl font-black tracking-tight text-slate-950 dark:text-white">{value}</div>
        </div>
      </div>
    </div>
  );
}

type IncentiveCategory = CampaignsPromotionsResponse['incentive_category_breakdown'][number];

const CATEGORY_EXPORT_COLUMNS: ExportColumn<IncentiveCategory>[] = [
  { header: 'Categorie', value: (row) => row.label },
  { header: 'Cantitate calificata', value: (row) => row.qualified_qty, format: 'integer' },
  { header: 'Cantitate totala', value: (row) => row.qty, format: 'integer' },
  { header: 'Incentive calculat', value: (row) => row.value, format: 'currency' },
  { header: 'Incentive total', value: (row) => row.potential, format: 'currency' },
];

function IncentiveKpis({ promoData }: { promoData: CampaignsPromotionsResponse | null }) {
  return (
    <div className="grid grid-cols-4 gap-3">
      <KpiCard icon={<Tag size={16} />} label="Unități vândute" value={promoData ? formatInt(promoData.incentive_sold_qty) : '—'} tone="bg-indigo-50 text-indigo-600 dark:bg-indigo-950/50 dark:text-indigo-300" />
      <KpiCard icon={<BadgePercent size={16} />} label="Eligibile după promo" value={promoData?.incentive_qty != null ? formatInt(promoData.incentive_qty) : '—'} tone="bg-emerald-50 text-emerald-600 dark:bg-emerald-950/50 dark:text-emerald-300" />
      <KpiCard icon={<Building2 size={16} />} label="În magazine calificate" value={promoData?.incentive_qualified_qty != null ? formatInt(promoData.incentive_qualified_qty) : '—'} tone="bg-violet-50 text-violet-600 dark:bg-violet-950/50 dark:text-violet-300" />
      <KpiCard icon={<Gift size={16} />} label="Incentive calculat" value={promoData?.incentive_value != null ? formatCurrency(promoData.incentive_value) : '—'} tone="bg-amber-50 text-amber-600 dark:bg-amber-950/50 dark:text-amber-300" />
    </div>
  );
}

export function IncentiveDesktopDashboard({
  promoData,
  month,
}: {
  promoData: CampaignsPromotionsResponse | null;
  month: string;
}) {
  const periods = promoData?.incentive_periods ?? [];
  const categories = [...(promoData?.incentive_category_breakdown ?? [])]
    .sort((left, right) => right.qty - left.qty || left.label.localeCompare(right.label, 'ro'));
  const tiers = promoData?.incentive_categories ?? [];
  const chartRows = categories.map((row) => ({ name: row.label, Calificate: row.qualified_qty, Total: row.qty }));
  return (
    <div className="hidden space-y-3 lg:block">
      <IncentiveKpis promoData={promoData} />
      <div className="grid gap-3 lg:grid-cols-2 xl:grid-cols-12">
        <section className="min-w-0 rounded-2xl border border-slate-200/80 bg-white/90 p-4 shadow-sm lg:col-span-2 xl:col-span-6 dark:border-slate-800 dark:bg-slate-900/80">
          <div className="mb-2 flex items-start justify-between gap-3">
            <div>
              <div className="flex items-center gap-2 text-indigo-600 dark:text-indigo-300">
                <Sparkles size={15} />
                <h2 className="text-sm font-black">Performanță pe categorii</h2>
              </div>
              <p className="mt-1 text-[11px] text-slate-500">Cantitate calificată comparată cu totalul eligibil.</p>
            </div>
            {categories.length > 0 && (
              <ExportTableButton
                filename={'focus-incentive-categorii-' + month}
                sheetName="Categorii incentive"
                rows={categories}
                columns={CATEGORY_EXPORT_COLUMNS}
              />
            )}
          </div>
          {chartRows.length > 0 ? (
            <div className="h-[248px]">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartRows} layout="vertical" margin={{ top: 8, right: 18, bottom: 6, left: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#e2e8f0" />
                  <XAxis type="number" tick={{ fontSize: 10 }} tickFormatter={(value) => formatInt(Number(value))} />
                  <YAxis type="category" dataKey="name" width={118} tick={{ fontSize: 10 }} />
                  <Tooltip formatter={(value) => formatInt(Number(value))} />
                  <Legend iconType="circle" wrapperStyle={{ fontSize: 10 }} />
                  <Bar dataKey="Total" fill="#c7d2fe" radius={[0, 5, 5, 0]} maxBarSize={14} />
                  <Bar dataKey="Calificate" fill="#4f46e5" radius={[0, 5, 5, 0]} maxBarSize={14} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className="flex h-[248px] items-center justify-center rounded-xl bg-slate-50 text-xs font-semibold text-slate-400 dark:bg-slate-950/40">
              Nu există încă detaliu pe categorii pentru perioada selectată.
            </div>
          )}
        </section>
        <section className="min-w-0 rounded-2xl border border-indigo-100 bg-indigo-50/40 p-4 shadow-sm xl:col-span-4 dark:border-indigo-900/50 dark:bg-indigo-950/20">
          <div className="mb-3 flex items-center justify-between gap-2">
            <div className="flex items-center gap-2 text-indigo-700 dark:text-indigo-300">
              <Gift size={15} />
              <h2 className="text-sm font-black">{periods.length > 1 ? 'Mecanisme active' : 'Mecanism curent'}</h2>
            </div>
            {promoData && promoData.incentive_product_count > 0 && (
              <span className="rounded-full bg-white px-2 py-1 text-[10px] font-bold text-indigo-700 shadow-xs dark:bg-slate-900 dark:text-indigo-300">
                {formatInt(promoData.incentive_product_count)} coduri
              </span>
            )}
          </div>
          <div className="space-y-2">
            {periods.length > 0 ? periods.map((period) => (
              <div key={period.start_date + '-' + period.end_date} className="rounded-xl border border-indigo-100 bg-white/90 p-3 dark:border-indigo-900/50 dark:bg-slate-900/70">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <div className="text-xs font-black text-slate-900 dark:text-white">{period.label}</div>
                    <div className="mt-0.5 text-[10px] font-semibold text-slate-400">{period.start_date} — {period.end_date}</div>
                  </div>
                  <span className="text-[10px] font-bold text-indigo-600 dark:text-indigo-300">{formatInt(period.product_count)} produse în incentive</span>
                </div>
                <div className="mt-3">
                  <div>
                    <div className="text-[9px] font-bold uppercase tracking-wide text-slate-400">Valoare / unitate eligibilă</div>
                    <div className="mt-0.5 text-[11px] font-black">{period.reward_values.map((value) => formatInt(value) + ' RON').join(' · ')}</div>
                  </div>
                  <p className="mt-2 text-[10px] leading-relaxed text-slate-500 dark:text-slate-400">Se aplică valoarea produsului activă la data vânzării, după excluderea unităților promo. La 90–99,99% din target se acordă 50%; de la 100%, integral.</p>
                </div>
              </div>
            )) : (
              <div className="rounded-xl border border-indigo-100 bg-white/80 p-3 text-xs text-slate-500 dark:border-indigo-900/50 dark:bg-slate-900/60 dark:text-slate-300">
                {promoData?.incentive_description || 'Nu există mecanism activ în perioada selectată.'}
              </div>
            )}
          </div>
          <IncentiveQualificationSummary promoData={promoData} className="mt-3" />
        </section>
        <aside className="min-w-0 rounded-2xl border border-slate-200/80 bg-slate-50/90 p-4 shadow-sm xl:col-span-2 dark:border-slate-800 dark:bg-slate-900/70">
          <div className="flex items-center gap-2 text-slate-700 dark:text-slate-200">
            <CalendarDays size={15} />
            <h2 className="text-sm font-black">Context</h2>
          </div>
          <div className="mt-3 rounded-xl bg-white p-3 dark:bg-slate-950/50">
            <div className="text-[9px] font-bold uppercase tracking-[0.14em] text-slate-400">Perioadă</div>
            <div className="mt-1 text-xs font-black capitalize">{monthLabel(month)}</div>
          </div>
          {tiers.length > 0 && (
            <div className="mt-3 border-t border-slate-200 pt-3 dark:border-slate-700">
              <div className="text-[9px] font-bold uppercase tracking-[0.14em] text-slate-400">Tier-uri vândute</div>
              <div className="mt-2 flex flex-wrap gap-1">
                {tiers.map((tier) => (
                  <span key={tier.label} className="rounded-full bg-indigo-50 px-2 py-1 text-[9px] font-bold text-indigo-700 dark:bg-indigo-950/40 dark:text-indigo-300">
                    {tier.label}: {formatInt(tier.qty)}
                  </span>
                ))}
              </div>
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}
