import React, { useEffect, useMemo, useRef, useState } from 'react';
import { CalendarRange, Search, Users, Activity, TrendingUp, UserPlus, UserMinus, UserCheck, RefreshCw, ChevronLeft, ChevronDown, Calendar, Award, LayoutGrid, Store, FileText, X } from 'lucide-react';
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
import { getFilterOptions } from '../api/filters';
import type { AppFilters } from './MainLayout';
import type { FilterOptions } from '../api/types';
import { SalariiSubtab } from './SalariiSubtab';
import { ErrorBoundary } from './ErrorBoundary';
import { 
  fetchAgentsOverview, 
  fetchAgentsMovement, 
  fetchAgentsList,
  fetchAgentProfile,
  fetchAgentHistory,
  fetchStoreCoverage,
  AgentsQuery,
  AgentsOverviewResponse,
  AgentMovementResponse,
  AgentListResponse,
  AgentListItem,
  AgentProfileResponse,
  AgentHistoryResponse,
  StoreCoverageResponse,
  StoreCoverageItem
} from '../api/agents';

// formatters
const nf = new Intl.NumberFormat('ro-RO', { style: 'currency', currency: 'RON', maximumFractionDigits: 0 });
const nfNum = new Intl.NumberFormat('ro-RO');

interface AgentDetailsProps {
  agent: string;
  currentMonth: string;
  onBack?: () => void;
}

function AgentDetails({ agent, currentMonth, onBack }: AgentDetailsProps) {
  const [profile, setProfile] = useState<AgentProfileResponse | null>(null);
  const [history, setHistory] = useState<AgentHistoryResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    async function load() {
      setLoading(true);
      try {
        const [prof, hist] = await Promise.all([
          fetchAgentProfile(agent, currentMonth),
          fetchAgentHistory(agent)
        ]);
        if (active) {
          setProfile(prof);
          setHistory(hist);
        }
      } catch (e) {
        console.error(e);
      } finally {
        if (active) setLoading(false);
      }
    }
    load();
    return () => { active = false; };
  }, [agent, currentMonth]);

  if (loading) {
    return (
      <div className="flex items-center justify-center p-12">
        <RefreshCw size={24} className="animate-spin text-indigo-500" />
      </div>
    );
  }

  if (!profile) return <div>Eroare la incarcare profil</div>;

  return (
    <div className="space-y-3 pb-24">
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
            <ResponsiveContainer width="100%" height="100%" minWidth={0}>
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
      <div
        className="flex h-full w-full max-w-md flex-col bg-white/95 dark:bg-slate-900/95 shadow-2xl"
        style={{ animation: 'slideInRight 300ms ease-out' }}
      >
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
            onBack={onClose}
          />
        </div>
      </div>

      <style>{`
        @keyframes slideInRight {
          from { transform: translateX(100%); }
          to { transform: translateX(0); }
        }
      `}</style>
    </div>
  );
}

// ======================== Main Agents Component ========================

interface AgentsProps {
  currentMonth: string;
  months: string[];
  filters: AppFilters;
  user: import('../api/types').AuthUser | null;
}

export function Agents({ currentMonth, months, filters, user }: AgentsProps) {
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [selectedAgent, setSelectedAgent] = useState<string | null>(() => {
    if (typeof window !== 'undefined') return localStorage.getItem('agents_selectedAgent') || null;
    return null;
  });
  const [activeTab, setActiveTab] = useState<'active' | 'movement' | 'inactive' | 'all'>(() => {
    if (typeof window !== 'undefined') return (localStorage.getItem('agents_activeTab') as any) || 'active';
    return 'active';
  });
  const [mainTab, setMainTab] = useState<'overview' | 'salarii'>(() => {
    if (typeof window !== 'undefined') return (localStorage.getItem('agents_mainTab') as any) || 'overview';
    return 'overview';
  });
  
  const [overview, setOverview] = useState<AgentsOverviewResponse | null>(null);
  const [movement, setMovement] = useState<AgentMovementResponse | null>(null);
  const [coverage, setCoverage] = useState<StoreCoverageResponse | null>(null);
  const [list, setList] = useState<AgentListItem[]>([]);
  const [loadingOverview, setLoadingOverview] = useState(false);
  const [loadingList, setLoadingList] = useState(false);
  const [loadingCoverage, setLoadingCoverage] = useState(false);
  const [cardFirma, setCardFirma] = useState('Toate');
  const [cardMagazin, setCardMagazin] = useState('Toate');
  const [filterOptions, setFilterOptions] = useState<FilterOptions | null>(null);

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
    if (activeTab === 'inactive') result = result.filter((ag: AgentListItem) => ag.current_status === 'inactive_recent' || ag.current_status === 'churned');
    if (cardFirma !== 'Toate' && filterOptions) {
      const firmaMagazine = filterOptions.magazine.filter((m) => m.firma === cardFirma).map((m) => m.locatie || m.site_code);
      result = result.filter((ag: AgentListItem) => firmaMagazine.includes(ag.store_name || ''));
    }
    if (cardMagazin !== 'Toate') {
      result = result.filter((ag: AgentListItem) => ag.store_name === cardMagazin);
    }
    return result;
  }, [list, activeTab, cardFirma, cardMagazin, filterOptions]);

  const filteredCount = useMemo(() => {
    if (activeTab === 'active') return list.filter((ag: AgentListItem) => ag.current_status === 'active').length;
    if (activeTab === 'movement') return list.filter((ag: AgentListItem) => ag.is_new || ag.is_reactivated).length;
    if (activeTab === 'inactive') return list.filter((ag: AgentListItem) => ag.current_status === 'inactive_recent' || ag.current_status === 'churned').length;
    return list.length;
  }, [list, activeTab]);

  const filterLabel = useMemo(() => {
    if (filters.agent !== 'Toti') return `Agent: ${filters.agent}`;
    if (filters.magazin !== 'Toate') return `Magazin: ${filters.magazin}`;
    if (filters.asm !== 'Toti') return `ASM: ${filters.asm}`;
    if (filters.rm !== 'Toti') return `Regional: ${filters.rm}`;
    if (filters.firma !== 'Toate') return `Firma: ${filters.firma}`;
    return 'Toata selectia activa';
  }, [filters]);

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(search), 300);
    return () => clearTimeout(timer);
  }, [search]);

  // Load Overview & Movement
  useEffect(() => {
    let active = true;
    async function load() {
      setLoadingOverview(true);
      setLoadingCoverage(true);
      try {
        const p: AgentsQuery = { selected_month: currentMonth };
        if (filters.firma !== 'Toate') p.firma = filters.firma;
        if (filters.rm !== 'Toti') p.regional = filters.rm;
        if (filters.asm !== 'Toti') p.asm = filters.asm;
        if (filters.magazin !== 'Toate') p.site_code = filters.magazin;
        if (filters.agent !== 'Toti') p.agent = filters.agent;

        const [ov, mv, cv] = await Promise.all([
          fetchAgentsOverview(p),
          fetchAgentsMovement(p),
          fetchStoreCoverage(p)
        ]);

        if (active) {
          setOverview(ov);
          setMovement(mv);
          setCoverage(cv);
        }
      } catch (err) {
        console.error(err);
      } finally {
        if (active) {
          setLoadingOverview(false);
          setLoadingCoverage(false);
        }
      }
    }
    load();
    return () => { active = false; };
  }, [currentMonth, filters]);

  // Load List
  useEffect(() => {
    let active = true;
    async function load() {
      setLoadingList(true);
      try {
        const p: AgentsQuery = { selected_month: currentMonth };
        if (filters.firma !== 'Toate') p.firma = filters.firma;
        if (filters.rm !== 'Toti') p.regional = filters.rm;
        if (filters.asm !== 'Toti') p.asm = filters.asm;
        if (filters.magazin !== 'Toate') p.site_code = filters.magazin;
        if (debouncedSearch) p.search = debouncedSearch;

        const data = await fetchAgentsList(p);
        if (active) setList(data.items);
      } catch (err) {
        console.error(err);
      } finally {
        if (active) setLoadingList(false);
      }
    }
    load();
    return () => { active = false; };
  }, [currentMonth, filters, debouncedSearch]);

  // Load Coverage
  useEffect(() => {
    let active = true;
    async function load() {
      setLoadingCoverage(true);
      try {
        const p: AgentsQuery = { selected_month: currentMonth };
        if (filters.firma !== 'Toate') p.firma = filters.firma;
        if (filters.rm !== 'Toti') p.regional = filters.rm;
        if (filters.asm !== 'Toti') p.asm = filters.asm;
        if (filters.magazin !== 'Toate') p.site_code = filters.magazin;
        if (filters.agent !== 'Toti') p.agent = filters.agent;

        const data = await fetchStoreCoverage(p);
        if (active) setCoverage(data);
      } catch (err) {
        console.error(err);
      } finally {
        if (active) setLoadingCoverage(false);
      }
    }
    load();
    return () => { active = false; };
  }, [currentMonth, filters]);

  const CustomTooltip = ({ active, payload, label }: any) => {
    if (active && payload && payload.length) {
      return (
        <div className="rounded-2xl border border-slate-200 bg-white/95 p-3 shadow-xl backdrop-blur-md dark:border-slate-700 dark:bg-slate-900/95">
          <p className="mb-2 text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400">
            {label}
          </p>
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
                  {entry.value}
                </span>
              </div>
            ))}
          </div>
        </div>
      );
    }
    return null;
  };

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
    <div className="space-y-3 p-3 pb-24 pt-2">
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
        {user?.role === 'admin' && (
          <button
            onClick={() => setMainTab('salarii')}
            className={`flex-1 rounded-xl py-2 text-sm font-bold transition-all ${
              mainTab === 'salarii'
                ? 'bg-white text-indigo-600 shadow-sm dark:bg-slate-700 dark:text-white'
                : 'text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200'
            }`}
          >
            Salarii
          </button>
        )}
      </div>

      {mainTab === 'salarii' && user?.role === 'admin' ? (
        <ErrorBoundary>
          <SalariiSubtab globalFilters={filters} currentMonth={currentMonth} />
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
              <div className="text-xs font-bold text-slate-600 dark:text-slate-400">Plecati</div>
            </div>
            <div className="text-2xl font-black text-rose-600 dark:text-rose-400">{overview?.left_this_month_count ?? '-'}</div>
            <div className="mt-1 text-[10px] text-slate-500">fata de luna trecuta</div>
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

      <div className="glass rounded-3xl p-4">
        <div className="mb-4">
          <h3 className="text-sm font-bold">Miscare de personal</h3>
          <p className="mt-1 text-[11px] text-slate-500">Evolutia lunara a efectivului activ si a achizitiei</p>
        </div>
        
        <div className="h-64 w-full">
          {movement && movement.history.length > 0 ? (
            <ResponsiveContainer width="100%" height="100%" minWidth={0}>
              <ComposedChart data={movement.history} margin={{ top: 10, right: 0, left: -20, bottom: 0 }}>
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
                />
                <Tooltip content={<CustomTooltip />} />
                <Legend 
                  wrapperStyle={{ fontSize: '11px', paddingTop: '10px' }} 
                  iconType="circle"
                  iconSize={8}
                />
                <Bar dataKey="new" name="Noi" stackId="a" fill="#10b981" barSize={12} radius={[0, 0, 4, 4]} />
                <Bar dataKey="reactivated" name="Reactivati" stackId="a" fill="#f59e0b" radius={[4, 4, 0, 0]} />
                <Line type="monotone" dataKey="active" name="Total Activi" stroke="#6366f1" strokeWidth={3} dot={{ r: 3, strokeWidth: 2 }} />
                <Line type="monotone" dataKey="net_growth" name="Net Growth" stroke="#8b5cf6" strokeWidth={2} strokeDasharray="5 5" dot={{ r: 2 }} />
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

        <div className="grid grid-cols-3 gap-3">
          <div className="rounded-2xl bg-emerald-50/50 p-3 dark:bg-emerald-900/10">
            <div className="mb-2 flex items-center gap-2">
              <Store size={16} className="text-emerald-500" />
              <div className="text-xs font-bold text-slate-600 dark:text-slate-400">Cu Agent</div>
            </div>
            <div className="text-2xl font-black text-emerald-600 dark:text-emerald-400">
              {coverage ? coverage.active_stores_count : '-'}
            </div>
          </div>
          <div className="rounded-2xl bg-amber-50/50 p-3 dark:bg-amber-900/10">
            <div className="mb-2 flex items-center gap-2">
              <Store size={16} className="text-amber-500" />
              <div className="text-xs font-bold text-slate-600 dark:text-slate-400">Fara Agent</div>
            </div>
            <div className="text-2xl font-black text-amber-600 dark:text-amber-400">
              {coverage ? coverage.uncovered_stores_count : '-'}
            </div>
          </div>
          <div className="rounded-2xl bg-slate-50/80 p-3 dark:bg-slate-800/40">
            <div className="mb-2 flex items-center gap-2">
              <Store size={16} className="text-slate-500" />
              <div className="text-xs font-bold text-slate-600 dark:text-slate-400">Inactive</div>
            </div>
            <div className="text-2xl font-black">
              {coverage ? coverage.closed_stores_count : '-'}
            </div>
            <div className="mt-1 text-[10px] text-slate-500">&gt; 3 luni fara activitate</div>
          </div>
        </div>

        {coverage && coverage.items.length > 0 && coverage.uncovered_stores_count > 0 && (
          <div className="mt-3 max-h-48 overflow-y-auto space-y-1">
            <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-1">Magazine fara agent (descoperite)</div>
            {coverage.items
              .filter((item: StoreCoverageItem) => item.status === 'uncovered')
              .slice(0, 10)
              .map((item: StoreCoverageItem) => (
                <div key={item.site_code} className="flex items-center justify-between rounded-xl bg-amber-50/50 px-3 py-2 dark:bg-amber-900/10">
                  <div>
                    <span className="text-xs font-bold text-slate-700 dark:text-slate-200">{item.locatie || item.site_code}</span>
                    <span className="ml-2 text-[10px] text-slate-400">{item.asm}</span>
                  </div>
                  <span className="text-[10px] font-bold text-amber-600">Fara agent</span>
                </div>
              ))}
          </div>
        )}

        {coverage && coverage.items.length > 0 && coverage.closed_stores_count > 0 && (
          <div className="mt-3 max-h-48 overflow-y-auto space-y-1">
            <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-1">
              Magazine inactive ({coverage.closed_stores_count}) — &gt; 3 luni fara activitate
            </div>
            {coverage.items
              .filter((item: StoreCoverageItem) => item.status === 'closed')
              .slice(0, 15)
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
          {loadingList && <RefreshCw size={14} className="animate-spin text-slate-400" />}
        </div>

        <div className="mb-4 flex gap-2 flex-wrap">
          {[
            { key: 'active' as const, label: 'Activi' },
            { key: 'movement' as const, label: 'Miscari' },
            { key: 'inactive' as const, label: 'Inactiv/Risc' },
            { key: 'all' as const, label: 'Toti' },
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
                onChange={(e) => { setCardFirma(e.target.value); setCardMagazin('Toate'); }}
                className="w-full appearance-none rounded-xl border border-slate-200 bg-slate-50 px-2 py-2 pr-6 text-xs outline-none dark:border-slate-700 dark:bg-slate-800"
              >
                <option value="Toate">Toate firmele</option>
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
                <option value="Toate">Toate</option>
                {Array.from(new Set(filterOptions?.magazine
                  .filter((m) => cardFirma === 'Toate' || m.firma === cardFirma)
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