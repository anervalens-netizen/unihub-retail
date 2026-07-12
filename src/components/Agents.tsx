import { useEffect, useMemo, useRef, useState } from 'react';
import { Search, Users, Activity, TrendingUp, UserPlus, UserMinus, UserCheck, RefreshCw, ChevronDown, ChevronUp, Award, LayoutGrid, Store, X } from 'lucide-react';
import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { useQuery } from '@tanstack/react-query';
import { getFilterOptions } from '../api/filters';
import type { AppFilters } from './MainLayout';
import type { FilterOptions } from '../api/types';
import { GrileSubtab } from './GrileSubtab';
import { AgentEvaluationSubtab } from './AgentEvaluationSubtab';
import { ErrorBoundary } from './ErrorBoundary';
import { ExportTableButton } from './ExportTableButton';
import { ALL_FIRMS, ALL_SCOPE, ALL_STORES } from '../lib/filterValues';
import { 
  fetchAgentsOverview, 
  fetchAgentsMovement, 
  fetchAgentsList,
  fetchAgentProfile,
  fetchAgentHistory,
  fetchStoreCoverage,
  AgentsQuery,
  AgentListItem,
  StoreCoverageItem
} from '../api/agents';

// formatters
const nf = new Intl.NumberFormat('ro-RO', { style: 'currency', currency: 'RON', maximumFractionDigits: 0 });
const nfNum = new Intl.NumberFormat('ro-RO');

interface AgentDetailsProps {
  agent: string;
  currentMonth: string;
}

function AgentDetails({ agent, currentMonth }: AgentDetailsProps) {
  const { data: profile, isLoading: profileLoading } = useQuery({
    queryKey: ['agents', 'profile', agent, currentMonth],
    queryFn: () => fetchAgentProfile(agent, currentMonth),
  });

  const { data: history, isLoading: historyLoading } = useQuery({
    queryKey: ['agents', 'history', agent],
    queryFn: () => fetchAgentHistory(agent),
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

      <div className="glass rounded-3xl p-4">
        <h3 className="mb-4 text-sm font-bold">Istoric Vanzari</h3>
        <div className="h-64 w-full">
          {history && history.history.length > 0 ? (
            <ResponsiveContainer width="100%" height="100%" minWidth={1} minHeight={1}>
              <ComposedChart data={history.history} margin={{ top: 10, right: 0, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" opacity={0.5} />
                <XAxis 
                  dataKey="month" 
                  axisLine={false} 
                  tickLine={false} 
                  tick={{ fontSize: 10, fill: '#64748b' }} 
                  dy={10} 
                  tickFormatter={(val) => val.split('-').reverse().join('.')}
                />
                <YAxis 
                  axisLine={false} 
                  tickLine={false} 
                  tick={{ fontSize: 10, fill: '#64748b' }} 
                  tickFormatter={(val) => `${val / 1000}k`}
                />
                <Tooltip 
                  content={({ active, payload, label }: any) => {
                    if (active && payload && payload.length) {
                      return (
                        <div className="rounded-2xl border border-slate-200 bg-white/95 p-3 shadow-xl backdrop-blur-md dark:border-slate-700 dark:bg-slate-900/95">
                          <p className="mb-2 text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400">
                            {label}
                          </p>
                          <div className="space-y-1">
                            <div className="text-sm font-medium text-slate-600 dark:text-slate-300">
                              Vanzari: <span className="font-bold text-slate-900 dark:text-white">{nf.format(payload[0].payload.total_sales)}</span>
                            </div>
                            <div className="text-sm font-medium text-slate-600 dark:text-slate-300">
                              Cantitate: <span className="font-bold text-slate-900 dark:text-white">{nfNum.format(payload[0].payload.total_quantity)}</span>
                            </div>
                            <div className="text-sm font-medium text-slate-600 dark:text-slate-300">
                              Bonuri: <span className="font-bold text-slate-900 dark:text-white">{payload[0].payload.receipt_count}</span>
                            </div>
                            <div className="text-sm font-medium text-slate-600 dark:text-slate-300">
                              Magazine: <span className="font-bold text-slate-900 dark:text-white">{payload[0].payload.active_store_count}</span>
                            </div>
                          </div>
                        </div>
                      );
                    }
                    return null;
                  }}
                />
                <Bar dataKey="total_sales" fill="#6366f1" radius={[4, 4, 0, 0]} maxBarSize={40} />
              </ComposedChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex h-full items-center justify-center text-xs text-slate-400">Nu exista istoric.</div>
          )}
        </div>
      </div>
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

function AgentDrawer({ agent, currentMonth, isOpen, onClose }: AgentDrawerProps) {
  const overlayRef = useRef<HTMLDivElement>(null);

  function handleOverlayClick(e: React.MouseEvent) {
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

// ======================== Main Agents Component ========================

interface AgentsProps {
  currentMonth: string;
  months: string[];
  filters: AppFilters;
}

function CustomTooltip({ active, payload, label }: any) {
  if (active && payload && payload.length) {
    const point = payload[0]?.payload;
    return (
      <div className="rounded-2xl border border-slate-200 bg-white/95 p-3 shadow-xl backdrop-blur-md dark:border-slate-700 dark:bg-slate-900/95">
        <p className="mb-2 text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400">
          {label}
        </p>
        {point?.is_baseline && (
          <p className="mb-2 max-w-56 text-[11px] font-medium leading-snug text-slate-500">
            Luna de start pentru tracking pe agent. Nu este tratata ca angajare masiva.
          </p>
        )}
        <div className="space-y-1">
          {payload.map((entry: any, i: number) => (
            <div key={i} className="flex items-center gap-3">
              <div
                className="h-2 w-2 rounded-full"
                style={{ backgroundColor: entry.color }}
              />
              <span className="text-sm font-medium text-slate-600 dark:text-slate-300">
                {entry.name}:
              </span>
              <span className="text-sm font-bold text-slate-900 dark:text-white">
                {entry.dataKey === 'churned_negative' ? Math.abs(entry.value) : entry.value}
              </span>
            </div>
          ))}
        </div>
      </div>
    );
  }
  return null;
}

export function Agents({ currentMonth, months: _months, filters }: AgentsProps) {
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [selectedAgent, setSelectedAgent] = useState<string | null>(() => {
    if (typeof window !== 'undefined') return localStorage.getItem('agents_selectedAgent') || null;
    return null;
  });
  const [activeTab, setActiveTab] = useState<'active' | 'movement' | 'inactive' | 'churned' | 'all'>(() => {
    if (typeof window !== 'undefined') return (localStorage.getItem('agents_activeTab') as any) || 'active';
    return 'active';
  });
  const [mainTab, setMainTab] = useState<'overview' | 'grile' | 'analysis'>(() => {
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem('agents_mainTab');
      if (saved === 'overview' || saved === 'grile' || saved === 'analysis') return saved;
    }
    return 'overview';
  });
  
  const [cardFirma, setCardFirma] = useState(ALL_FIRMS);
  const [cardMagazin, setCardMagazin] = useState(ALL_STORES);
  const [filterOptions, setFilterOptions] = useState<FilterOptions | null>(null);
  const [expandedSection, setExpandedSection] = useState<'active' | 'modified' | 'inactive' | null>(null);

  const queryParams = useMemo(() => {
    const p: AgentsQuery = { selected_month: currentMonth };
    if (filters.firma !== ALL_FIRMS) p.firma = filters.firma;
    if (filters.rm !== ALL_SCOPE) p.regional = filters.rm;
    if (filters.magazin !== ALL_STORES) p.site_code = filters.magazin;
    if (filters.agent !== ALL_SCOPE) p.agent = filters.agent;
    return p;
  }, [currentMonth, filters]);

  const { data: overview, isLoading: loadingOverview } = useQuery({
    queryKey: ['agents', 'overview', queryParams],
    queryFn: () => fetchAgentsOverview(queryParams),
  });

  const { data: movement } = useQuery({
    queryKey: ['agents', 'movement', queryParams],
    queryFn: () => fetchAgentsMovement(queryParams),
  });

  const { data: coverage, isLoading: loadingCoverage } = useQuery({
    queryKey: ['agents', 'coverage', queryParams],
    queryFn: () => fetchStoreCoverage(queryParams),
  });

  const listParams = useMemo(() => ({ ...queryParams, search: debouncedSearch || undefined }), [queryParams, debouncedSearch]);
  
  const { data: listResponse, isLoading: loadingList } = useQuery({
    queryKey: ['agents', 'list', listParams],
    queryFn: () => fetchAgentsList(listParams),
  });
  
  const list = useMemo(() => listResponse?.items || [], [listResponse?.items]);

  // Fetch filter options for card filters
  useEffect(() => {
    getFilterOptions(currentMonth).then(setFilterOptions).catch(() => setFilterOptions(null));
  }, [currentMonth]);

  // Persist state to localStorage
  useEffect(() => {
    localStorage.setItem('agents_mainTab', mainTab);
  }, [mainTab]);

  useEffect(() => {
    localStorage.setItem('agents_activeTab', activeTab);
  }, [activeTab]);

  useEffect(() => {
    if (selectedAgent) {
      localStorage.setItem('agents_selectedAgent', selectedAgent);
    } else {
      localStorage.removeItem('agents_selectedAgent');
    }
  }, [selectedAgent]);

  const filteredList = useMemo(() => {
    let result = list;
    if (activeTab === 'active') result = result.filter((ag: AgentListItem) => ag.current_status === 'active');
    if (activeTab === 'movement') result = result.filter((ag: AgentListItem) => ag.is_new || ag.is_reactivated);
    if (activeTab === 'inactive') result = result.filter((ag: AgentListItem) => ag.current_status === 'inactive_recent');
    if (activeTab === 'churned') result = result.filter((ag: AgentListItem) => ag.current_status === 'churned');
    if (cardFirma !== ALL_FIRMS && filterOptions) {
      const firmaMagazine = filterOptions.magazine.filter((m) => m.firma === cardFirma).map((m) => m.locatie || m.site_code);
      result = result.filter((ag: AgentListItem) => firmaMagazine.includes(ag.store_name || ''));
    }
    if (cardMagazin !== ALL_STORES) {
      result = result.filter((ag: AgentListItem) => ag.store_name === cardMagazin);
    }
    return result;
  }, [list, activeTab, cardFirma, cardMagazin, filterOptions]);

  const chartData = useMemo(() => {
    const points = (movement?.history ?? []).filter((p) => p.month >= '2025-01');
    return points.map((p, index) => {
      const isBaseline = p.is_baseline || p.month === '2025-01';
      const previous = index > 0 ? points[index - 1] : null;
      const newAgents = isBaseline ? 0 : p.new;
      const reactivatedAgents = isBaseline ? 0 : p.reactivated;
      const derivedExited = previous
        ? Math.max(0, previous.active + newAgents + reactivatedAgents - p.active)
        : 0;
      const exited = isBaseline ? 0 : Math.max(p.churned ?? 0, derivedExited);
      const netGrowth = isBaseline || !previous ? 0 : p.active - previous.active;

      return {
        ...p,
        is_baseline: isBaseline,
        new: newAgents,
        reactivated: reactivatedAgents,
        churned: exited,
        net_growth: netGrowth,
        churned_negative: -exited,
      };
    });
  }, [movement]);

  const maxMovement = useMemo(() => {
    const values = chartData.flatMap((p) => [p.new, p.reactivated, p.churned, Math.abs(p.net_growth)]);
    return Math.max(5, ...values) + 2;
  }, [chartData]);

  const churnAnalysis = useMemo(() => {
    const nonBaseline = chartData.filter((p) => !p.is_baseline);
    const currentPoint = chartData.find((p) => p.month === currentMonth) ?? chartData.at(-1);
    const currentPrevActive = currentPoint && !currentPoint.is_baseline
      ? Math.max(0, currentPoint.active - currentPoint.net_growth)
      : 0;
    const currentChurnRate = currentPrevActive > 0 && currentPoint
      ? (currentPoint.churned / currentPrevActive) * 100
      : null;
    const lastThree = nonBaseline.slice(-3);
    const avgChurnRate = lastThree.length > 0
      ? lastThree.reduce((sum, p) => {
          const prevActive = Math.max(0, p.active - p.net_growth);
          return sum + (prevActive > 0 ? (p.churned / prevActive) * 100 : 0);
        }, 0) / lastThree.length
      : null;
    const totalExited = nonBaseline.reduce((sum, p) => sum + p.churned, 0);
    return {
      currentChurnRate,
      avgChurnRate,
      totalExited,
      currentExited: currentPoint?.churned ?? 0,
      currentNetGrowth: currentPoint?.is_baseline ? 0 : currentPoint?.net_growth ?? 0,
    };
  }, [chartData, currentMonth]);

  const topFluxStores = useMemo(() => {
    return (coverage?.items ?? [])
      .filter((item) => item.has_changes)
      .map((item) => ({
        ...item,
        change_count: item.added_agents_count + item.removed_agents_count,
      }))
      .sort((a, b) => b.change_count - a.change_count || b.agent_count - a.agent_count || a.locatie.localeCompare(b.locatie))
      .slice(0, 5);
  }, [coverage]);

  const filterLabel = useMemo(() => {
    if (filters.agent !== ALL_SCOPE) return `Agent: ${filters.agent}`;
    if (filters.magazin !== ALL_STORES) return `Magazin: ${filters.magazin}`;
    if (filters.rm !== ALL_SCOPE) return `Regional: ${filters.rm}`;
    if (filters.firma !== ALL_FIRMS) return `Firma: ${filters.firma}`;
    return 'Toata selectia activa';
  }, [filters]);

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(search), 300);
    return () => clearTimeout(timer);
  }, [search]);



  if (selectedAgent) {
    return (
      <AgentDrawer
        agent={selectedAgent}
        currentMonth={currentMonth}
        isOpen={!!selectedAgent}
        onClose={() => setSelectedAgent(null)}
      />
    );
  }

  return (
    <div className="space-y-3 p-3 pb-24 lg:pb-6 pt-2">
      <div>
        <h1 className="text-xl font-bold tracking-tight">Agenti</h1>
        <p className="text-xs text-slate-500 dark:text-slate-400">
          Analiza echipei, miscare de personal si retentie
        </p>
      </div>

      <div className="flex gap-2 rounded-2xl bg-slate-100 p-1 dark:bg-slate-800">
        <button
          onClick={() => setMainTab('overview')}
          className={`flex-1 rounded-xl py-2 text-sm font-bold transition-all ${
            mainTab === 'overview'
              ? 'bg-white text-indigo-600 shadow-sm dark:bg-slate-700 dark:text-white'
              : 'text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200'
          }`}
        >
          Prezentare Generala
        </button>
        <button
          onClick={() => setMainTab('grile')}
          className={`flex-1 rounded-xl py-2 text-sm font-bold transition-all ${
            mainTab === 'grile'
              ? 'bg-white text-indigo-600 shadow-sm dark:bg-slate-700 dark:text-white'
              : 'text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200'
          }`}
        >
          Grile
        </button>
        <button
          onClick={() => setMainTab('analysis')}
          className={`flex-1 rounded-xl py-2 text-sm font-bold transition-all ${
            mainTab === 'analysis'
              ? 'bg-white text-indigo-600 shadow-sm dark:bg-slate-700 dark:text-white'
              : 'text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200'
          }`}
        >
          Analiza agenti
        </button>
      </div>

      {mainTab === 'analysis' ? (
        <ErrorBoundary>
          <AgentEvaluationSubtab />
        </ErrorBoundary>
      ) : mainTab === 'grile' ? (
        <ErrorBoundary>
          <GrileSubtab />
        </ErrorBoundary>
      ) : (
        <>
          {/* Zone A: Snapshot Luna Curenta */}
      <div className="glass rounded-3xl p-4">
        <div className="mb-3 flex items-start justify-between gap-3">
          <div>
            <h3 className="text-sm font-bold">Snapshot — {currentMonth}</h3>
            <p className="mt-1 text-xs leading-relaxed text-slate-500">{filterLabel}</p>
          </div>
          {loadingOverview && (
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-slate-100 dark:bg-slate-800">
              <RefreshCw size={14} className="animate-spin text-slate-400" />
            </div>
          )}
        </div>

        <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
          <div className="rounded-2xl bg-slate-50/80 p-3 dark:bg-slate-800/40">
            <div className="mb-2 flex items-center gap-2">
              <Users size={16} className="text-indigo-500" />
              <div className="text-xs font-bold text-slate-600 dark:text-slate-400">Activi</div>
            </div>
            <div className="text-2xl font-black">{overview?.active_count ?? '-'}</div>
          </div>
          <div className="rounded-2xl bg-emerald-50/50 p-3 dark:bg-emerald-900/10">
            <div className="mb-2 flex items-center gap-2">
              <UserPlus size={16} className="text-emerald-500" />
              <div className="text-xs font-bold text-slate-600 dark:text-slate-400">Noi</div>
            </div>
            <div className="text-2xl font-black text-emerald-600 dark:text-emerald-400">{overview?.new_count ?? '-'}</div>
          </div>
          <div className="rounded-2xl bg-amber-50/50 p-3 dark:bg-amber-900/10">
            <div className="mb-2 flex items-center gap-2">
              <UserCheck size={16} className="text-amber-500" />
              <div className="text-xs font-bold text-slate-600 dark:text-slate-400">Reactivati</div>
            </div>
            <div className="text-2xl font-black text-amber-600 dark:text-amber-400">{overview?.reactivated_count ?? '-'}</div>
          </div>
          <div className="rounded-2xl bg-rose-50/50 p-3 dark:bg-rose-900/10">
            <div className="mb-2 flex items-center gap-2">
              <UserMinus size={16} className="text-rose-500" />
              <div className="text-xs font-bold text-slate-600 dark:text-slate-400">Iesiti luna</div>
            </div>
            <div className="text-2xl font-black text-rose-600 dark:text-rose-400">{overview?.left_this_month_count ?? '-'}</div>
            <div className="mt-1 text-[10px] text-slate-500">fara vanzari fata de luna trecuta</div>
          </div>
          <div className="rounded-2xl bg-indigo-50/50 p-3 dark:bg-indigo-900/10">
            <div className="mb-2 flex items-center gap-2">
              <TrendingUp size={16} className="text-indigo-500" />
              <div className="text-xs font-bold text-slate-600 dark:text-slate-400">Retentie</div>
            </div>
            <div className="text-2xl font-black text-indigo-600 dark:text-indigo-400">
              {overview?.retention_rate != null ? `${overview.retention_rate}%` : '-'}
            </div>
          </div>
        </div>
      </div>

      {/* Zone B: Sanatate Echipă */}
      <div className="glass rounded-3xl p-4">
        <div className="mb-3">
          <h3 className="text-sm font-bold">Sanatate Echipă</h3>
          <p className="mt-1 text-xs leading-relaxed text-slate-500">Indicatori de stabilitate si trend</p>
        </div>

        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <div className="rounded-2xl bg-slate-50/80 p-3 dark:bg-slate-800/40">
            <div className="mb-2 flex items-center gap-2">
              <Users size={16} className="text-slate-500" />
              <div className="text-xs font-bold text-slate-600 dark:text-slate-400">Total Unici</div>
            </div>
            <div className="text-2xl font-black">{overview?.total_unique_agents ?? '-'}</div>
            <div className="mt-1 text-[10px] text-slate-500">in sistem</div>
          </div>
          <div className="rounded-2xl bg-blue-50/50 p-3 dark:bg-blue-900/10">
            <div className="mb-2 flex items-center gap-2">
              <Award size={16} className="text-blue-500" />
              <div className="text-xs font-bold text-slate-600 dark:text-slate-400">Vechime Medie</div>
            </div>
            <div className="text-2xl font-black text-blue-600 dark:text-blue-400">
              {overview?.avg_seniority_months != null ? `${overview.avg_seniority_months} luni` : '-'}
            </div>
          </div>
          <div className="rounded-2xl bg-purple-50/50 p-3 dark:bg-purple-900/10">
            <div className="mb-2 flex items-center gap-2">
              <Activity size={16} className="text-purple-500" />
              <div className="text-xs font-bold text-slate-600 dark:text-slate-400">Stabilitate</div>
            </div>
            <div className="text-2xl font-black text-purple-600 dark:text-purple-400">
              {overview?.stability_rate != null ? `${overview.stability_rate}%` : '-'}
            </div>
            <div className="mt-1 text-[10px] text-slate-500">&gt; 6 luni vechime</div>
          </div>
          <div className="rounded-2xl bg-rose-50/50 p-3 dark:bg-rose-900/10">
            <div className="mb-2 flex items-center gap-2">
              <UserMinus size={16} className="text-rose-500" />
              <div className="text-xs font-bold text-slate-600 dark:text-slate-400">Iesiti istoric</div>
            </div>
            <div className="text-2xl font-black text-rose-600 dark:text-rose-400">{overview?.churned_total_count ?? '-'}</div>
            <div className="mt-1 text-[10px] text-slate-500">absenti &ge; 2 luni</div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        <div className="glass rounded-3xl p-4">
          <div className="mb-3">
            <h3 className="text-sm font-bold">Analiza Churn</h3>
            <p className="mt-1 text-xs leading-relaxed text-slate-500">Iesiri de personal pentru snapshot {currentMonth}</p>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="rounded-2xl bg-rose-50/60 p-3 dark:bg-rose-900/10">
              <div className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Churn luna</div>
              <div className="mt-1 text-2xl font-black text-rose-600 dark:text-rose-400">
                {churnAnalysis.currentChurnRate != null ? `${churnAnalysis.currentChurnRate.toLocaleString('ro-RO', { maximumFractionDigits: 1 })}%` : '-'}
              </div>
              <div className="mt-1 text-[10px] text-slate-500">{churnAnalysis.currentExited} iesiti</div>
            </div>
            <div className="rounded-2xl bg-indigo-50/60 p-3 dark:bg-indigo-900/10">
              <div className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Net luna</div>
              <div className={`mt-1 text-2xl font-black ${churnAnalysis.currentNetGrowth < 0 ? 'text-rose-600 dark:text-rose-400' : 'text-emerald-600 dark:text-emerald-400'}`}>
                {churnAnalysis.currentNetGrowth > 0 ? '+' : ''}{churnAnalysis.currentNetGrowth}
              </div>
              <div className="mt-1 text-[10px] text-slate-500">activi vs luna trecuta</div>
            </div>
            <div className="rounded-2xl bg-slate-50/80 p-3 dark:bg-slate-800/40">
              <div className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Churn mediu 3 luni</div>
              <div className="mt-1 text-2xl font-black">
                {churnAnalysis.avgChurnRate != null ? `${churnAnalysis.avgChurnRate.toLocaleString('ro-RO', { maximumFractionDigits: 1 })}%` : '-'}
              </div>
            </div>
            <div className="rounded-2xl bg-slate-50/80 p-3 dark:bg-slate-800/40">
              <div className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Iesiri in trend</div>
              <div className="mt-1 text-2xl font-black">{churnAnalysis.totalExited}</div>
              <div className="mt-1 text-[10px] text-slate-500">din 2025-02 incoace</div>
            </div>
          </div>
        </div>

        <div className="glass rounded-3xl p-4">
          <div className="mb-3">
            <h3 className="text-sm font-bold">Top Magazine dupa Flux</h3>
            <p className="mt-1 text-xs leading-relaxed text-slate-500">Magazine cu cele mai multe intrari si iesiri de agenti</p>
          </div>
          <div className="space-y-2">
            {topFluxStores.length === 0 && (
              <div className="rounded-2xl bg-slate-50 p-4 text-center text-xs text-slate-500 dark:bg-slate-800/40">
                Nu exista modificari in selectia curenta.
              </div>
            )}
            {topFluxStores.map((item) => (
              <div key={item.site_code} className="flex items-center justify-between gap-3 rounded-2xl bg-slate-50 px-3 py-2 dark:bg-slate-800/40">
                <div className="min-w-0">
                  <div className="truncate text-xs font-bold text-slate-700 dark:text-slate-200">{item.locatie || item.site_code}</div>
                  <div className="mt-0.5 text-[10px] text-slate-500">{item.asm} · {item.change_reason || 'modificat'}</div>
                </div>
                <div className="flex shrink-0 items-center gap-1">
                  {item.added_agents_count > 0 && (
                    <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-bold text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300">
                      +{item.added_agents_count}
                    </span>
                  )}
                  {item.removed_agents_count > 0 && (
                    <span className="rounded-full bg-rose-100 px-2 py-0.5 text-[10px] font-bold text-rose-700 dark:bg-rose-900/40 dark:text-rose-300">
                      -{item.removed_agents_count}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="glass rounded-3xl p-4">
        <div className="mb-4">
          <h3 className="text-sm font-bold">Miscare de personal</h3>
          <p className="mt-1 text-[11px] text-slate-500">Intrari, iesiri si efectiv activ. 01.2025 este baseline de tracking.</p>
        </div>
        
        <div className="h-64 w-full">
          {chartData.length > 0 ? (
            <ResponsiveContainer width="100%" height="100%" minWidth={1} minHeight={1}>
              <ComposedChart data={chartData} margin={{ top: 10, right: 0, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" opacity={0.5} />
                <XAxis 
                  dataKey="month" 
                  axisLine={false} 
                  tickLine={false} 
                  tick={{ fontSize: 10, fill: '#64748b' }} 
                  dy={10} 
                  tickFormatter={(val) => val.split('-').reverse().join('.')}
                />
                <YAxis 
                  yAxisId="movement"
                  axisLine={false} 
                  tickLine={false} 
                  tick={{ fontSize: 10, fill: '#64748b' }} 
                  domain={[-maxMovement, maxMovement]}
                  tickFormatter={(val) => `${Math.abs(Number(val))}`}
                />
                <YAxis
                  yAxisId="active"
                  orientation="right"
                  axisLine={false}
                  tickLine={false}
                  tick={{ fontSize: 10, fill: '#64748b' }}
                />
                <Tooltip content={<CustomTooltip />} />
                <Legend 
                  wrapperStyle={{ fontSize: '11px', paddingTop: '10px' }} 
                  iconType="circle"
                  iconSize={8}
                />
                <Bar yAxisId="movement" dataKey="new" name="Noi" stackId="in" fill="#10b981" barSize={12} radius={[4, 4, 0, 0]} />
                <Bar yAxisId="movement" dataKey="reactivated" name="Reactivati" stackId="in" fill="#f59e0b" radius={[4, 4, 0, 0]} />
                <Bar yAxisId="movement" dataKey="churned_negative" name="Iesiti" fill="#e11d48" barSize={12} radius={[0, 0, 4, 4]} />
                <Line yAxisId="active" type="monotone" dataKey="active" name="Total Activi" stroke="#6366f1" strokeWidth={3} dot={{ r: 3, strokeWidth: 2 }} />
                <Line yAxisId="movement" type="monotone" dataKey="net_growth" name="Net" stroke="#8b5cf6" strokeWidth={2} strokeDasharray="5 5" dot={{ r: 2 }} />
              </ComposedChart>
            </ResponsiveContainer>
          ) : (
             <div className="flex h-full items-center justify-center text-xs text-slate-400">
               Nu exista date de miscare.
             </div>
          )}
        </div>
      </div>

      {/* Store Coverage Section */}
      <div className="glass rounded-3xl p-4">
        <div className="mb-3 flex items-start justify-between gap-3">
          <div>
            <h3 className="text-sm font-bold">Magazine si Flux</h3>
            <p className="mt-1 text-xs leading-relaxed text-slate-500">Acoperire agenti pe magazine</p>
          </div>
          {loadingCoverage && (
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-slate-100 dark:bg-slate-800">
              <RefreshCw size={14} className="animate-spin text-slate-400" />
            </div>
          )}
        </div>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          {/* Active */}
          <button
            onClick={() => setExpandedSection(prev => prev === 'active' ? null : 'active')}
            className="rounded-2xl bg-emerald-50/50 p-3 dark:bg-emerald-900/10 text-left hover:bg-emerald-100/60 dark:hover:bg-emerald-900/20 transition-colors"
          >
            <div className="mb-2 flex items-center justify-between gap-1">
              <div className="flex items-center gap-2">
                <Store size={16} className="text-emerald-500" />
                <div className="text-xs font-bold text-slate-600 dark:text-slate-400">Active</div>
              </div>
              {expandedSection === 'active'
                ? <ChevronUp size={12} className="text-slate-400 shrink-0" />
                : <ChevronDown size={12} className="text-slate-400 shrink-0" />}
            </div>
            <div className="text-2xl font-black text-emerald-600 dark:text-emerald-400">
              {coverage ? coverage.active_stores_count : '-'}
            </div>
          </button>

          {/* Cu Modificări */}
          <button
            onClick={() => setExpandedSection(prev => prev === 'modified' ? null : 'modified')}
            className="rounded-2xl bg-amber-50/50 p-3 dark:bg-amber-900/10 text-left hover:bg-amber-100/60 dark:hover:bg-amber-900/20 transition-colors"
          >
            <div className="mb-2 flex items-center justify-between gap-1">
              <div className="flex items-center gap-2">
                <Store size={16} className="text-amber-500" />
                <div className="text-xs font-bold text-slate-600 dark:text-slate-400">Cu Modificări</div>
              </div>
              {expandedSection === 'modified'
                ? <ChevronUp size={12} className="text-slate-400 shrink-0" />
                : <ChevronDown size={12} className="text-slate-400 shrink-0" />}
            </div>
            <div className="text-2xl font-black text-amber-600 dark:text-amber-400">
              {coverage ? coverage.modified_stores_count : '-'}
            </div>
            <div className="mt-1 text-[10px] text-slate-500">intrari / iesiri agenti</div>
          </button>

          {/* Inactive */}
          <button
            onClick={() => setExpandedSection(prev => prev === 'inactive' ? null : 'inactive')}
            className="rounded-2xl bg-slate-50/80 p-3 dark:bg-slate-800/40 text-left hover:bg-slate-100/60 dark:hover:bg-slate-800/60 transition-colors"
          >
            <div className="mb-2 flex items-center justify-between gap-1">
              <div className="flex items-center gap-2">
                <Store size={16} className="text-slate-500" />
                <div className="text-xs font-bold text-slate-600 dark:text-slate-400">Inactive</div>
              </div>
              {expandedSection === 'inactive'
                ? <ChevronUp size={12} className="text-slate-400 shrink-0" />
                : <ChevronDown size={12} className="text-slate-400 shrink-0" />}
            </div>
            <div className="text-2xl font-black">
              {coverage ? coverage.closed_stores_count : '-'}
            </div>
            <div className="mt-1 text-[10px] text-slate-500">&gt; 3 luni fara activitate</div>
          </button>
        </div>

        {/* Active list */}
        {coverage && expandedSection === 'active' && (
          <div className="mt-3 max-h-56 overflow-y-auto space-y-1">
            <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-1">
              Magazine active ({coverage.active_stores_count})
            </div>
            {coverage.items
              .filter((item: StoreCoverageItem) => item.status === 'covered')
              .map((item: StoreCoverageItem) => (
                <div key={item.site_code} className="flex items-center justify-between rounded-xl bg-emerald-50/50 px-3 py-2 dark:bg-emerald-900/10">
                  <div className="min-w-0 flex-1">
                    <span className="text-xs font-bold text-slate-700 dark:text-slate-200 truncate block">{item.locatie || item.site_code}</span>
                    <span className="text-[10px] text-slate-400">{item.asm}</span>
                  </div>
                  <span className="ml-2 shrink-0 text-[10px] font-bold text-emerald-600">{item.agent_count} ag.</span>
                </div>
              ))}
          </div>
        )}

        {/* Cu Modificări list */}
        {coverage && expandedSection === 'modified' && (
          <div className="mt-3 max-h-56 overflow-y-auto space-y-1">
            <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-1">
              Magazine cu modificări ({coverage.modified_stores_count})
            </div>
            {coverage.items
              .filter((item: StoreCoverageItem) => item.has_changes)
              .map((item: StoreCoverageItem) => (
                <div key={item.site_code} className="flex items-center justify-between gap-3 rounded-xl bg-amber-50/50 px-3 py-2 dark:bg-amber-900/10">
                  <div className="min-w-0 flex-1">
                    <span className="text-xs font-bold text-slate-700 dark:text-slate-200 truncate block">{item.locatie || item.site_code}</span>
                    <span className="text-[10px] text-slate-400">
                      {item.asm} · {item.change_reason || 'modificat'} · {item.previous_agent_count} &rarr; {item.agent_count} ag.
                    </span>
                  </div>
                  <div className="ml-2 flex shrink-0 items-center gap-1">
                    {item.added_agents_count > 0 && (
                      <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-bold text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300">
                        +{item.added_agents_count}
                      </span>
                    )}
                    {item.removed_agents_count > 0 && (
                      <span className="rounded-full bg-rose-100 px-2 py-0.5 text-[10px] font-bold text-rose-700 dark:bg-rose-900/40 dark:text-rose-300">
                        -{item.removed_agents_count}
                      </span>
                    )}
                  </div>
                </div>
              ))}
          </div>
        )}

        {/* Inactive list */}
        {coverage && expandedSection === 'inactive' && coverage.closed_stores_count > 0 && (
          <div className="mt-3 max-h-56 overflow-y-auto space-y-1">
            <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-1">
              Magazine inactive ({coverage.closed_stores_count}) — &gt; 3 luni fara activitate
            </div>
            {coverage.items
              .filter((item: StoreCoverageItem) => item.status === 'closed')
              .map((item: StoreCoverageItem) => (
                <div key={item.site_code} className="flex items-center justify-between rounded-xl bg-slate-100/60 px-3 py-2 dark:bg-slate-800/40">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-bold text-slate-600 dark:text-slate-300 truncate">{item.locatie || item.site_code}</span>
                      <span className="shrink-0 text-[10px] text-slate-400">{item.asm}</span>
                    </div>
                    <div className="text-[10px] text-slate-400">{item.firma} · {item.regional}</div>
                  </div>
                  <span className="ml-2 shrink-0 text-[10px] font-bold text-slate-400">{item.agent_count} ag.</span>
                </div>
              ))}
          </div>
        )}
      </div>

      <div className="glass rounded-3xl p-4">
        <div className="mb-4 flex items-center justify-between gap-3">
          <div>
            <h3 className="text-sm font-bold">Lista Agenti</h3>
            <p className="text-[11px] text-slate-500">
              {filteredList.length === list.length ? `Toti (${list.length})` : `${filteredList.length} din ${list.length}`} {list.length === 200 ? '(maxim 200)' : ''}
            </p>
          </div>
          <div className="flex items-center gap-2">
            {loadingList && <RefreshCw size={14} className="animate-spin text-slate-400" />}
            <ExportTableButton
              filename={`agenti_${currentMonth}`}
              sheetName={`Agenti ${currentMonth}`}
              rows={filteredList}
              columns={[
                { header: 'Agent', value: (row) => row.agent },
                { header: 'Firma', value: (row) => row.firma ?? '' },
                { header: 'Magazin', value: (row) => row.store_name ?? '' },
                { header: 'Status', value: (row) => row.current_status },
                { header: 'Nou', value: (row) => row.is_new ? 'Da' : 'Nu' },
                { header: 'Reactivat', value: (row) => row.is_reactivated ? 'Da' : 'Nu' },
                { header: 'Vanzari', value: (row) => nf.format(row.total_sales) },
                { header: 'Cantitate', value: (row) => nfNum.format(row.total_quantity) },
              ]}
            />
          </div>
        </div>

        <div className="mb-4 flex gap-2 flex-wrap">
          {[
            { key: 'active' as const, label: 'Activi' },
            { key: 'movement' as const, label: 'Miscari' },
            { key: 'inactive' as const, label: 'Inactiv' },
            { key: 'churned' as const, label: 'Iesiti' },
            { key: 'all' as const, label: ALL_SCOPE },
          ].map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`rounded-xl px-3 py-1.5 text-xs font-bold transition-colors ${
                activeTab === tab.key
                  ? 'bg-indigo-500 text-white'
                  : 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
        
        <label className="mb-4 flex items-center gap-2 rounded-2xl border border-slate-200 bg-slate-50 px-3 py-3 text-sm dark:border-slate-700 dark:bg-slate-800">
          <Search size={16} className="text-slate-400" />
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Cauta dupa nume agent..."
            className="w-full bg-transparent outline-none placeholder:text-slate-400"
          />
        </label>

        <div className="mb-4 grid grid-cols-2 gap-2">
          <div>
            <label className="mb-1 block text-[10px] font-bold uppercase text-slate-500">Firma</label>
            <div className="relative">
              <select
                value={cardFirma}
                onChange={(e) => { setCardFirma(e.target.value); setCardMagazin(ALL_STORES); }}
                className="w-full appearance-none rounded-xl border border-slate-200 bg-slate-50 px-2 py-2 pr-6 text-xs outline-none dark:border-slate-700 dark:bg-slate-800"
              >
                <option value={ALL_FIRMS}>Toate firmele</option>
                {filterOptions?.firme.sort().map((firma) => (
                  <option key={firma} value={firma}>{firma}</option>
                ))}
              </select>
              <ChevronDown size={12} className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-slate-400" />
            </div>
          </div>
          <div>
            <label className="mb-1 block text-[10px] font-bold uppercase text-slate-500">Magazin</label>
            <div className="relative">
              <select
                value={cardMagazin}
                onChange={(e) => setCardMagazin(e.target.value)}
                disabled={!filterOptions}
                className="w-full appearance-none rounded-xl border border-slate-200 bg-slate-50 px-2 py-2 pr-6 text-xs outline-none disabled:opacity-50 dark:border-slate-700 dark:bg-slate-800"
              >
                <option value={ALL_STORES}>Toate</option>
                {Array.from(new Set(filterOptions?.magazine
                  .filter((m) => cardFirma === ALL_FIRMS || m.firma === cardFirma)
                  .map((m) => m.locatie || m.site_code) || [])).sort()
                  .map((locatie) => (
                    <option key={locatie} value={locatie}>{locatie}</option>
                  ))}
              </select>
              <ChevronDown size={12} className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-slate-400" />
            </div>
          </div>
        </div>

        <div className="max-h-96 overflow-y-auto space-y-2 pr-1">
          {filteredList.length === 0 && !loadingList ? (
            <div className="py-8 text-center text-sm text-slate-500">Niciun agent in aceasta categorie</div>
          ) : (
            filteredList.map((ag: AgentListItem) => (
              <button
                key={ag.agent}
                onClick={() => setSelectedAgent(ag.agent)}
                className="flex w-full items-center justify-between rounded-2xl bg-slate-50 px-4 py-3 text-left transition-colors hover:bg-slate-100 dark:bg-slate-800/60 dark:hover:bg-slate-800"
              >
                <div>
                  <div className="font-bold text-slate-800 dark:text-slate-200">{ag.agent}</div>
                  {ag.store_name && <div className="text-[10px] text-slate-500">{ag.store_name}</div>}
                  <div className="mt-1 flex items-center gap-2">
                    {ag.current_status === 'active' && <span className="text-[10px] font-bold text-emerald-600 dark:text-emerald-400">ACTIV</span>}
                    {ag.current_status === 'inactive_recent' && <span className="text-[10px] font-bold text-amber-600 dark:text-amber-400">INACTIV RECENT</span>}
                    {ag.current_status === 'churned' && <span className="text-[10px] font-bold text-rose-600 dark:text-rose-400">IESIT</span>}
                    
                    {ag.is_new && <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-[9px] font-bold uppercase text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-400">Nou</span>}
                    {ag.is_reactivated && <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[9px] font-bold uppercase text-amber-700 dark:bg-amber-900/40 dark:text-amber-400">Reactivat</span>}
                  </div>
                </div>
                <div className="text-right">
                  <div className="text-sm font-black">{nf.format(ag.total_sales)}</div>
                  <div className="text-[10px] text-slate-500">{nfNum.format(ag.total_quantity)} buc</div>
                </div>
              </button>
            ))
          )}
        </div>
      </div>
      </>
      )}

    </div>
  );
}
