import { useRef, type MouseEvent } from 'react';
import { Activity, Award, LayoutGrid, RefreshCw, Store, X } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { Bar, CartesianGrid, ComposedChart, ResponsiveContainer, Tooltip, XAxis, YAxis, type TooltipContentProps } from 'recharts';
import { fetchAgentHistory, fetchAgentProfile, type AgentHistoryPoint } from '../../api/agents';
import { queryKeys } from '../../lib/queryKeys';

const nf = new Intl.NumberFormat('ro-RO', { style: 'currency', currency: 'RON', maximumFractionDigits: 0 });
const nfNum = new Intl.NumberFormat('ro-RO');
interface AgentDetailsProps {
  agent: string;
  currentMonth: string;
}

type ChartTooltipProps = TooltipContentProps;

function AgentHistoryTooltip({ active, payload, label }: ChartTooltipProps) {
  if (!active || !payload?.length) return null;
  const point = payload[0]?.payload as AgentHistoryPoint | undefined;
  return (
    <div className="rounded-2xl border border-slate-200 bg-white/95 p-3 shadow-xl backdrop-blur-md dark:border-slate-700 dark:bg-slate-900/95">
      <p className="mb-2 text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400">{label}</p>
      <div className="space-y-1">
        <div className="text-sm font-medium text-slate-600 dark:text-slate-300">Vanzari: <span className="font-bold text-slate-900 dark:text-white">{nf.format(point?.total_sales ?? 0)}</span></div>
        <div className="text-sm font-medium text-slate-600 dark:text-slate-300">Cantitate: <span className="font-bold text-slate-900 dark:text-white">{nfNum.format(point?.total_quantity ?? 0)}</span></div>
        <div className="text-sm font-medium text-slate-600 dark:text-slate-300">Bonuri: <span className="font-bold text-slate-900 dark:text-white">{point?.receipt_count ?? 0}</span></div>
        <div className="text-sm font-medium text-slate-600 dark:text-slate-300">Magazine: <span className="font-bold text-slate-900 dark:text-white">{point?.active_store_count ?? 0}</span></div>
      </div>
    </div>
  );
}

function AgentSalesHistory({ history }: { history: Awaited<ReturnType<typeof fetchAgentHistory>> | undefined }) {
  return (
    <div className="glass rounded-3xl p-4">
      <h3 className="mb-4 text-sm font-bold">Istoric Vanzari</h3>
      <div className="h-64 w-full">
        {history && history.history.length > 0 ? (
          <ResponsiveContainer width="100%" height="100%" minWidth={1} minHeight={1}>
            <ComposedChart data={history.history} margin={{ top: 10, right: 0, left: -20, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" opacity={0.5} />
              <XAxis dataKey="month" axisLine={false} tickLine={false} tick={{ fontSize: 10, fill: '#64748b' }} dy={10} tickFormatter={(value) => value.split('-').reverse().join('.')} />
              <YAxis axisLine={false} tickLine={false} tick={{ fontSize: 10, fill: '#64748b' }} tickFormatter={(value) => `${value / 1000}k`} />
              <Tooltip content={AgentHistoryTooltip} />
              <Bar dataKey="total_sales" fill="#6366f1" radius={[4, 4, 0, 0]} maxBarSize={40} />
            </ComposedChart>
          </ResponsiveContainer>
        ) : <div className="flex h-full items-center justify-center text-xs text-slate-400">Nu exista istoric.</div>}
      </div>
    </div>
  );
}

export function AgentDetails({ agent, currentMonth }: AgentDetailsProps) {
  const { data: profile, isLoading: profileLoading } = useQuery({
    queryKey: queryKeys.agents.profile(agent, currentMonth),
    queryFn: ({ signal }) => fetchAgentProfile(agent, currentMonth, signal),
  });

  const { data: history, isLoading: historyLoading } = useQuery({
    queryKey: queryKeys.agents.history(agent),
    queryFn: ({ signal }) => fetchAgentHistory(agent, signal),
  });

  const loading = profileLoading || historyLoading;

  if (loading) {
    return (
      <div className="flex items-center justify-center p-12">
        <RefreshCw size={24} className="animate-spin text-indigo-500" />
      </div>
    );
  }

  if (!profile) return <div>Eroare la incarcare profil</div>;

  return (
    <div className="space-y-3 pb-24 lg:pb-6">
      <div className="glass rounded-3xl p-5">
        <div className="mb-6 flex items-start justify-between">
          <div>
            <h2 className="text-2xl font-black">{profile.agent}</h2>
            <p className="text-sm font-medium text-slate-500">
              Profil analizat fata de luna {currentMonth}
            </p>
          </div>
          <div className={`rounded-xl px-3 py-1.5 text-xs font-bold uppercase tracking-wider ${
            profile.current_status === 'active'
              ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400'
              : profile.current_status === 'inactive_recent'
              ? 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400'
              : 'bg-rose-100 text-rose-700 dark:bg-rose-900/30 dark:text-rose-400'
          }`}>
            {profile.current_status === 'active' ? 'Activ' : profile.current_status === 'inactive_recent' ? 'Inactiv recent' : 'Iesit'}
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div className="rounded-2xl bg-slate-50 p-3 dark:bg-slate-800/50">
            <div className="mb-1 text-[10px] font-bold uppercase tracking-wider text-slate-500">Prima luna</div>
            <div className="text-lg font-black">{profile.first_seen_month}</div>
          </div>
          <div className="rounded-2xl bg-slate-50 p-3 dark:bg-slate-800/50">
            <div className="mb-1 text-[10px] font-bold uppercase tracking-wider text-slate-500">Luni Active</div>
            <div className="text-lg font-black">{profile.active_months_count}</div>
          </div>
          <div className="rounded-2xl bg-slate-50 p-3 dark:bg-slate-800/50">
            <div className="mb-1 text-[10px] font-bold uppercase tracking-wider text-slate-500">Vanzari Carier</div>
            <div className="text-lg font-black">{nf.format(profile.career_total_sales)}</div>
          </div>
          <div className="rounded-2xl bg-slate-50 p-3 dark:bg-slate-800/50">
            <div className="mb-1 text-[10px] font-bold uppercase tracking-wider text-slate-500">Cea mai buna luna</div>
            <div className="text-lg font-black">{profile.best_month || '-'}</div>
            <div className="text-[10px] text-indigo-600 dark:text-indigo-400">{nf.format(profile.best_month_sales)}</div>
          </div>
        </div>

        <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
           <div className="flex items-center gap-3 rounded-2xl bg-slate-50 p-3 dark:bg-slate-800/50">
             <Store size={18} className="text-slate-400" />
             <div>
               <div className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Magazine</div>
               <div className="text-sm font-black">{profile.distinct_store_count}</div>
             </div>
           </div>
           <div className="flex items-center gap-3 rounded-2xl bg-slate-50 p-3 dark:bg-slate-800/50">
             <LayoutGrid size={18} className="text-slate-400" />
             <div>
               <div className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Firme</div>
               <div className="text-sm font-black">{profile.distinct_firma_count}</div>
             </div>
           </div>
           <div className="flex items-center gap-3 rounded-2xl bg-slate-50 p-3 dark:bg-slate-800/50">
             <Award size={18} className="text-slate-400" />
             <div>
               <div className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Reactivari</div>
               <div className="text-sm font-black">{profile.reactivation_count}</div>
             </div>
           </div>
           <div className="flex items-center gap-3 rounded-2xl bg-slate-50 p-3 dark:bg-slate-800/50">
             <Activity size={18} className="text-slate-400" />
             <div>
               <div className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Streak max</div>
               <div className="text-sm font-black">{profile.longest_active_streak} luni</div>
             </div>
           </div>
        </div>
      </div>

      <AgentSalesHistory history={history} />
    </div>
  );
}

// ======================== Agent Drawer ========================

interface AgentDrawerProps {
  agent: string;
  currentMonth: string;
  isOpen: boolean;
  onClose: () => void;
}

export function AgentDrawer({ agent, currentMonth, isOpen, onClose }: AgentDrawerProps) {
  const overlayRef = useRef<HTMLDivElement>(null);

  function handleOverlayClick(e: MouseEvent<HTMLDivElement>) {
    if (e.target === overlayRef.current) onClose();
  }

  if (!isOpen) return null;

  return (
    <div
      ref={overlayRef}
      onClick={handleOverlayClick}
      className="fixed inset-0 z-50 flex justify-end bg-black/30 backdrop-blur-sm transition-opacity"
    >
      <div className="animate-slide-in-right flex h-full w-full max-w-md flex-col bg-white/95 dark:bg-slate-900/95 shadow-2xl">
        {/* Header */}
        <div className="flex items-start justify-between border-b border-slate-200 px-6 py-5 dark:border-slate-700">
          <div>
            <h2 className="text-lg font-bold text-slate-800 dark:text-white">{agent}</h2>
            <p className="mt-1 text-sm text-slate-500">Profil agent</p>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-slate-800"
          >
            <X size={20} />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-4">
          <AgentDetails
            agent={agent}
            currentMonth={currentMonth}
          />
        </div>
      </div>

    </div>
  );
}
