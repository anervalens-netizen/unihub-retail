import { useState } from 'react';
import { Sparkles } from 'lucide-react';
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { FirmaBadge } from '../../components/FirmaBadge';
import { Metric } from '../../components/common/DataDisplay';
import { SegmentedTabs } from '../../components/common/SegmentedTabs';
import { SortableTable } from './SortableTable';
import { formatInt, formatPercent } from '../../lib/formatters';
import type {
  PremiumGlassAnalysis,
  PremiumGlassAgentStat,
  PremiumGlassManagerStat,
  PremiumGlassModelStat,
  PremiumGlassStoreStat,
  PremiumGlassSurfaceMode,
  PremiumGlassSurfaceStat,
} from '../../api/generated/runtime-types';

const PREMIUM_SURFACE_OPTIONS: Array<{ value: PremiumGlassSurfaceMode; label: string }> = [
  { value: 'all', label: 'Toate' },
  { value: 'screen', label: 'Ecran' },
  { value: 'camera', label: 'Camera' },
];

export function PremiumGlassFocusSection({
  analysis,
  surfaceMode,
  onSurfaceModeChange,
}: {
  analysis: PremiumGlassAnalysis | null;
  surfaceMode: PremiumGlassSurfaceMode;
  onSurfaceModeChange: (mode: PremiumGlassSurfaceMode) => void;
}) {
  const [mobileDetail, setMobileDetail] = useState<'overview' | 'models' | 'stores' | 'agents'>('overview');
  const summary = analysis?.summary;
  const modelChartData = (analysis?.models ?? []).map((model) => ({
    model: model.model_label.replace('Samsung ', 'S. '),
    Premium: model.premium_qty,
    Rest: model.regular_qty,
  }));
  const modelChartHeight = Math.max(224, modelChartData.length * 30);

  return (
    <div className="space-y-3">
      <div className="glass rounded-4xl border border-emerald-100 bg-linear-to-br from-emerald-50 via-white to-white p-4 dark:border-emerald-900/30 dark:from-emerald-950/20 dark:via-slate-900 dark:to-slate-900">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2 text-emerald-600 dark:text-emerald-400">
            <Sparkles size={16} />
            <span className="text-[11px] font-bold uppercase tracking-[0.22em]">Folii Premium</span>
          </div>
          <div className="inline-flex rounded-xl border border-emerald-200 bg-white p-1 text-[11px] font-bold shadow-xs dark:border-emerald-900/60 dark:bg-slate-900">
            {PREMIUM_SURFACE_OPTIONS.map((option) => (
              <button
                key={option.value}
                type="button"
                onClick={() => onSurfaceModeChange(option.value)}
                className={`min-h-11 rounded-lg px-3 py-2 transition lg:min-h-0 lg:py-1.5 ${
                  surfaceMode === option.value
                    ? 'bg-emerald-600 text-white shadow-sm'
                    : 'text-slate-500 hover:bg-emerald-50 hover:text-emerald-700 dark:text-slate-300 dark:hover:bg-emerald-950/50 dark:hover:text-emerald-200'
                }`}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>
        <h4 className="text-base font-black tracking-tight">Ecran + camera premium</h4>
        <p className="mt-1 text-xs text-slate-600 dark:text-slate-300">
          Categoria Folii Sticla: ecran premium dupa SAPPHIRE, CERAMIC si CORNING, plus camera premium din lista operationala.
        </p>
        <div className="mt-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
          <Metric label="Total folii" value={formatInt(summary?.total_qty ?? 0)} />
          <Metric label="Premium" value={formatInt(summary?.premium_qty ?? 0)} />
          <Metric label="Rest modele" value={formatInt(summary?.regular_qty ?? 0)} />
          <Metric label="Share cant." value={formatPercent(summary?.premium_qty_share_pct ?? null)} />
        </div>
      </div>

      {analysis && (
        <SegmentedTabs<'overview' | 'models' | 'stores' | 'agents'>
          ariaLabel="Detalii folii premium pe mobil"
          className="lg:hidden"
          level="secondary"
          options={[
            { value: 'overview', label: 'Sumar' },
            { value: 'models', label: 'Modele' },
            { value: 'stores', label: 'Magazine' },
            { value: 'agents', label: 'Agenți' },
          ]}
          value={mobileDetail}
          onChange={setMobileDetail}
        />
      )}

      {analysis && (
        <>
          <div className={`grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(280px,360px)] ${mobileDetail !== 'overview' ? 'hidden lg:grid' : ''}`}>
            <div className="glass rounded-3xl p-4">
              <div className="mb-3">
                <h3 className="text-sm font-bold">Premium vs rest pe modele</h3>
                <p className="text-[11px] text-slate-500">Modelele compatibile pe suprafata selectata</p>
              </div>
              <div className="min-w-0" style={{ height: modelChartData.length === 0 ? 224 : modelChartHeight }}>
                {modelChartData.length === 0 ? (
                  <div className="flex h-full items-center justify-center rounded-2xl bg-slate-50 text-xs font-semibold text-slate-500 dark:bg-slate-800/50">
                    Nu exista vanzari eligibile pentru filtrarea curenta.
                  </div>
                ) : (
                  <ResponsiveContainer width="100%" height="100%" minWidth={1} minHeight={1}>
                    <BarChart data={modelChartData} layout="vertical" margin={{ top: 4, right: 8, left: 8, bottom: 4 }}>
                      <CartesianGrid strokeDasharray="3 3" horizontal={false} opacity={0.15} />
                      <XAxis type="number" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
                      <YAxis dataKey="model" type="category" width={104} tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
                      <Tooltip formatter={(value: unknown) => formatInt(Number(value))} />
                      <Legend />
                      <Bar dataKey="Premium" stackId="qty" fill="#059669" radius={[0, 6, 6, 0]} />
                      <Bar dataKey="Rest" stackId="qty" fill="#cbd5e1" radius={[0, 6, 6, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                )}
              </div>
            </div>
            <PremiumGlassSurfaceBreakdown rows={analysis.surfaces ?? []} />
          </div>
          <div className="grid gap-3 lg:grid-cols-2">
            <div className={mobileDetail !== 'models' ? 'hidden lg:block' : ''}><PremiumGlassModelTable rows={analysis.models} /></div>
            <div className={mobileDetail !== 'overview' ? 'hidden lg:block' : ''}><PremiumGlassManagerTable rows={analysis.managers} /></div>
            <div className={mobileDetail !== 'stores' ? 'hidden lg:block' : ''}><PremiumGlassStoreTable rows={analysis.stores} /></div>
            <div className={mobileDetail !== 'agents' ? 'hidden lg:block' : ''}><PremiumGlassAgentTable rows={analysis.agents} /></div>
          </div>
        </>
      )}
    </div>
  );
}
function PremiumGlassSurfaceBreakdown({ rows }: { rows: PremiumGlassSurfaceStat[] }) {
  return (
    <div className="glass rounded-3xl p-4">
      <div className="mb-3">
        <h3 className="text-sm font-bold">Ecran vs camera</h3>
        <p className="text-[11px] text-slate-500">Camera vine din lista operationala cu Premium = da/nu</p>
      </div>
      <SortableTable<PremiumGlassSurfaceStat>
        rows={rows}
        defaultSortKey="total_qty"
        exportFilename="focus-folii-premium-ecran-camera"
        exportSheetName="Ecran camera folii"
        columns={[
          { key: 'surface_label', label: 'Tip', render: (row) => <span className="font-semibold">{row.surface_label}</span> },
          { key: 'premium_qty', label: 'Premium', align: 'right', render: (row) => <span className="font-black text-emerald-600">{formatInt(row.premium_qty)}</span> },
          { key: 'regular_qty', label: 'Rest', align: 'right', render: (row) => formatInt(row.regular_qty) },
          { key: 'premium_qty_share_pct', label: 'Share', align: 'right', render: (row) => formatPercent(row.premium_qty_share_pct) },
        ]}
      />
    </div>
  );
}
function PremiumGlassModelTable({ rows }: { rows: PremiumGlassModelStat[] }) {
  return (
    <div className="glass rounded-3xl p-4">
      <div className="mb-3">
        <h3 className="text-sm font-bold">Comparatie pe modele</h3>
        <p className="text-[11px] text-slate-500">Premium vs rest pentru acelasi model compatibil</p>
      </div>
      <SortableTable<PremiumGlassModelStat>
        rows={rows}
        defaultSortKey="total_qty"
        exportFilename="focus-folii-premium-modele"
        exportSheetName="Modele folii premium"
        exportColumns={[
          { header: 'Model', value: (row) => row.model_label },
          { header: 'Premium', value: (row) => row.premium_qty, format: 'integer' },
          { header: 'Rest', value: (row) => row.regular_qty, format: 'integer' },
          { header: 'Share', value: (row) => row.premium_qty_share_pct, format: 'percentPoints' },
        ]}
        columns={[
          { key: 'model_label', label: 'Model', render: (row) => <span className="font-semibold">{row.model_label}</span> },
          { key: 'premium_qty', label: 'Premium', align: 'right', render: (row) => <span className="font-black text-emerald-600">{formatInt(row.premium_qty)}</span> },
          { key: 'regular_qty', label: 'Rest', align: 'right', render: (row) => formatInt(row.regular_qty) },
          { key: 'premium_qty_share_pct', label: 'Share', align: 'right', render: (row) => formatPercent(row.premium_qty_share_pct) },
        ]}
      />
    </div>
  );
}

function PremiumGlassManagerTable({ rows }: { rows: PremiumGlassManagerStat[] }) {
  return (
    <div className="glass rounded-3xl p-4">
      <div className="mb-3">
        <h3 className="text-sm font-bold">Manageri</h3>
        <p className="text-[11px] text-slate-500">Cei 6 manageri activi, dupa cantitate premium</p>
      </div>
      <SortableTable<PremiumGlassManagerStat>
        rows={rows}
        defaultSortKey="premium_qty"
        exportFilename="focus-folii-premium-manageri"
        exportSheetName="Manageri folii premium"
        exportColumns={[
          { header: 'Manager', value: (row) => row.manager },
          { header: 'Premium', value: (row) => row.premium_qty, format: 'integer' },
          { header: 'Rest', value: (row) => row.regular_qty, format: 'integer' },
          { header: 'Share', value: (row) => row.premium_qty_share_pct, format: 'percentPoints' },
          { header: 'Magazine', value: (row) => row.store_count, format: 'integer' },
          { header: 'Agenti', value: (row) => row.agent_count, format: 'integer' },
        ]}
        columns={[
          { key: 'manager', label: 'Manager', render: (row) => <span className="font-semibold">{row.manager}</span> },
          { key: 'premium_qty', label: 'Premium', align: 'right', render: (row) => <span className="font-black text-emerald-600">{formatInt(row.premium_qty)}</span> },
          { key: 'regular_qty', label: 'Rest', align: 'right', render: (row) => formatInt(row.regular_qty) },
          { key: 'premium_qty_share_pct', label: 'Share', align: 'right', render: (row) => formatPercent(row.premium_qty_share_pct) },
          { key: 'store_count', label: 'Mag.', align: 'right', render: (row) => formatInt(row.store_count) },
          { key: 'agent_count', label: 'Ag.', align: 'right', render: (row) => formatInt(row.agent_count) },
        ]}
      />
    </div>
  );
}

function PremiumGlassStoreTable({ rows }: { rows: PremiumGlassStoreStat[] }) {
  return (
    <div className="glass rounded-3xl p-4">
      <div className="mb-3">
        <h3 className="text-sm font-bold">Magazine</h3>
        <p className="text-[11px] text-slate-500">Toate magazinele cu vanzari eligibile, dupa cantitate premium</p>
      </div>
      <SortableTable<PremiumGlassStoreStat>
        rows={rows}
        defaultSortKey="premium_qty"
        exportFilename="focus-folii-premium-magazine"
        exportSheetName="Magazine folii premium"
        exportColumns={[
          { header: 'Firma', value: (row) => row.firma },
          { header: 'Magazin', value: (row) => row.locatie },
          { header: 'Premium', value: (row) => row.premium_qty, format: 'integer' },
          { header: 'Rest', value: (row) => row.regular_qty, format: 'integer' },
          { header: 'Share', value: (row) => row.premium_qty_share_pct, format: 'percentPoints' },
        ]}
        columns={[
          {
            key: 'locatie',
            label: 'Magazin',
            render: (row) => {
              const store = row;
              return (
                <span className="flex items-center">
                  <FirmaBadge firma={store.firma} />
                  <span className="max-w-[110px] truncate font-semibold" title={store.locatie}>{store.locatie}</span>
                </span>
              );
            },
          },
          { key: 'premium_qty', label: 'Premium', align: 'right', render: (row) => <span className="font-black text-emerald-600">{formatInt(row.premium_qty)}</span> },
          { key: 'regular_qty', label: 'Rest', align: 'right', render: (row) => formatInt(row.regular_qty) },
          { key: 'premium_qty_share_pct', label: 'Share', align: 'right', render: (row) => formatPercent(row.premium_qty_share_pct) },
        ]}
      />
    </div>
  );
}

function PremiumGlassAgentTable({ rows }: { rows: PremiumGlassAgentStat[] }) {
  return (
    <div className="glass rounded-3xl p-4">
      <div className="mb-3">
        <h3 className="text-sm font-bold">Agenti</h3>
        <p className="text-[11px] text-slate-500">Toti agentii cu vanzari eligibile, dupa cantitate premium</p>
      </div>
      <SortableTable<PremiumGlassAgentStat>
        rows={rows}
        defaultSortKey="premium_qty"
        exportFilename="focus-folii-premium-agenti"
        exportSheetName="Agenti folii premium"
        exportColumns={[
          { header: 'Agent', value: (row) => row.agent },
          { header: 'Firma', value: (row) => row.firma },
          { header: 'Magazin', value: (row) => row.locatie },
          { header: 'Premium', value: (row) => row.premium_qty, format: 'integer' },
          { header: 'Rest', value: (row) => row.regular_qty, format: 'integer' },
          { header: 'Share', value: (row) => row.premium_qty_share_pct, format: 'percentPoints' },
        ]}
        columns={[
          {
            key: 'agent',
            label: 'Agent',
            render: (row) => {
              const agent = row;
              return (
                <span className="block max-w-[120px] truncate font-semibold" title={`${agent.agent} - ${agent.locatie}`}>
                  {agent.agent}
                </span>
              );
            },
          },
          { key: 'premium_qty', label: 'Premium', align: 'right', render: (row) => <span className="font-black text-emerald-600">{formatInt(row.premium_qty)}</span> },
          { key: 'regular_qty', label: 'Rest', align: 'right', render: (row) => formatInt(row.regular_qty) },
          { key: 'premium_qty_share_pct', label: 'Share', align: 'right', render: (row) => formatPercent(row.premium_qty_share_pct) },
        ]}
      />
    </div>
  );
}
