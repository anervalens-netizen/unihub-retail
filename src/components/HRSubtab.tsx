import { useEffect, useState } from 'react';
import { RefreshCw, CheckCircle, XCircle, Clock, ChevronDown, ChevronUp } from 'lucide-react';
import {
  fetchLeaveRequests,
  createLeaveRequest,
  updateLeaveStatus,
  fetchAgentPerformance,
  type LeaveRequest,
  type PerformancePoint,
} from '../api/hr';
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts';

const STATUS_ICON = {
  pending: <Clock size={14} className="text-yellow-400" />,
  approved: <CheckCircle size={14} className="text-green-400" />,
  rejected: <XCircle size={14} className="text-red-400" />,
};

const STATUS_LABEL = { pending: 'În așteptare', approved: 'Aprobat', rejected: 'Respins' };
const LEAVE_LABELS: Record<string, string> = { odihna: 'Odihnă', medical: 'Medical', altul: 'Alt motiv' };

export function HRSubtab() {
  const [requests, setRequests] = useState<LeaveRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [filterStatus, setFilterStatus] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ agent_name: '', start_date: '', end_date: '', leave_type: 'odihna', notes: '' });
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);
  const [perfData, setPerfData] = useState<PerformancePoint[]>([]);
  const [perfLoading, setPerfLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const data = await fetchLeaveRequests(filterStatus ? { status: filterStatus } : undefined);
      setRequests(data);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [filterStatus]);

  const handleCreate = async () => {
    if (!form.agent_name || !form.start_date || !form.end_date) return;
    await createLeaveRequest({ ...form, notes: form.notes || undefined });
    setForm({ agent_name: '', start_date: '', end_date: '', leave_type: 'odihna', notes: '' });
    setShowForm(false);
    await load();
  };

  const handleStatus = async (id: number, status: 'approved' | 'rejected') => {
    await updateLeaveStatus(id, status);
    await load();
  };

  const handleSelectAgent = async (name: string) => {
    if (selectedAgent === name) {
      setSelectedAgent(null);
      return;
    }
    setSelectedAgent(name);
    setPerfLoading(true);
    try {
      const data = await fetchAgentPerformance(name);
      setPerfData(data);
    } finally {
      setPerfLoading(false);
    }
  };

  const formatMonth = (m: string) => {
    const [y, mo] = m.split('-');
    const labels = ['Ian', 'Feb', 'Mar', 'Apr', 'Mai', 'Iun', 'Iul', 'Aug', 'Sep', 'Oct', 'Noi', 'Dec'];
    return `${labels[parseInt(mo) - 1]} ${y.slice(2)}`;
  };

  return (
    <div className="p-4 space-y-6">
      {/* Secțiunea Concedii */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-white/80 uppercase tracking-wide">Cereri concediu</h3>
          <div className="flex gap-2">
            {['', 'pending', 'approved', 'rejected'].map((s) => (
              <button
                key={s}
                onClick={() => setFilterStatus(s)}
                className={`px-2.5 py-1 rounded-full text-xs font-medium transition-colors ${
                  filterStatus === s ? 'bg-indigo-600 text-white' : 'bg-white/10 text-white/50 hover:bg-white/20'
                }`}
              >
                {s === '' ? 'Toate' : STATUS_LABEL[s as keyof typeof STATUS_LABEL]}
              </button>
            ))}
            <button onClick={load} className="p-1.5 rounded bg-white/10 hover:bg-white/20">
              <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
            </button>
            <button
              onClick={() => setShowForm(!showForm)}
              className="px-3 py-1.5 rounded bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-medium"
            >
              + Cerere nouă
            </button>
          </div>
        </div>

        {showForm && (
          <div className="bg-white/5 border border-white/10 rounded-xl p-4 space-y-3">
            <div className="grid grid-cols-2 gap-2">
              <input
                className="col-span-2 bg-white/10 border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder-white/40 focus:outline-none focus:border-indigo-500"
                placeholder="Nume agent *"
                value={form.agent_name}
                onChange={(e) => setForm({ ...form, agent_name: e.target.value })}
              />
              <input type="date" className="bg-white/10 border border-white/10 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500"
                value={form.start_date} onChange={(e) => setForm({ ...form, start_date: e.target.value })} />
              <input type="date" className="bg-white/10 border border-white/10 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500"
                value={form.end_date} onChange={(e) => setForm({ ...form, end_date: e.target.value })} />
              <select
                className="bg-white/10 border border-white/10 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500"
                value={form.leave_type}
                onChange={(e) => setForm({ ...form, leave_type: e.target.value })}
              >
                <option value="odihna">Odihnă</option>
                <option value="medical">Medical</option>
                <option value="altul">Alt motiv</option>
              </select>
              <input
                className="bg-white/10 border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder-white/40 focus:outline-none focus:border-indigo-500"
                placeholder="Note (opțional)"
                value={form.notes}
                onChange={(e) => setForm({ ...form, notes: e.target.value })}
              />
            </div>
            <div className="flex justify-end gap-2">
              <button onClick={() => setShowForm(false)} className="px-4 py-2 text-sm text-white/60 hover:text-white">Anulează</button>
              <button onClick={handleCreate} className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-sm rounded-lg font-medium">Salvează</button>
            </div>
          </div>
        )}

        <div className="space-y-2">
          {requests.length === 0 && !loading && (
            <div className="text-center text-white/40 py-6 text-sm">Nicio cerere</div>
          )}
          {requests.map((r) => (
            <div key={r.id} className="bg-white/5 border border-white/10 rounded-xl px-4 py-3">
              <div className="flex items-center gap-3">
                {STATUS_ICON[r.status]}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => handleSelectAgent(r.agent_name)}
                      className="text-sm font-medium text-white hover:text-indigo-400 transition-colors flex items-center gap-1"
                    >
                      {r.agent_name}
                      {selectedAgent === r.agent_name ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                    </button>
                    <span className="text-xs text-white/40">{LEAVE_LABELS[r.leave_type] ?? r.leave_type}</span>
                  </div>
                  <p className="text-xs text-white/50 mt-0.5">{r.start_date} → {r.end_date}{r.notes ? ` · ${r.notes}` : ''}</p>
                </div>
                {r.status === 'pending' && (
                  <div className="flex gap-1.5 shrink-0">
                    <button
                      onClick={() => handleStatus(r.id, 'approved')}
                      className="px-2.5 py-1 rounded text-xs bg-green-500/20 text-green-300 hover:bg-green-500/30 font-medium"
                    >
                      Aprobă
                    </button>
                    <button
                      onClick={() => handleStatus(r.id, 'rejected')}
                      className="px-2.5 py-1 rounded text-xs bg-red-500/20 text-red-300 hover:bg-red-500/30 font-medium"
                    >
                      Respinge
                    </button>
                  </div>
                )}
              </div>

              {/* Grafic performanță expandabil */}
              {selectedAgent === r.agent_name && (
                <div className="mt-3 pt-3 border-t border-white/10">
                  {perfLoading ? (
                    <div className="text-center text-white/40 text-xs py-4">Se încarcă...</div>
                  ) : perfData.length === 0 ? (
                    <div className="text-center text-white/40 text-xs py-4">Date indisponibile</div>
                  ) : (
                    <div className="h-40">
                      <ResponsiveContainer width="100%" height="100%">
                        <AreaChart data={perfData} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
                          <defs>
                            <linearGradient id="perfGrad" x1="0" y1="0" x2="0" y2="1">
                              <stop offset="5%" stopColor="#6366f1" stopOpacity={0.4} />
                              <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                            </linearGradient>
                          </defs>
                          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                          <XAxis dataKey="import_month" tickFormatter={formatMonth} tick={{ fill: 'rgba(255,255,255,0.4)', fontSize: 10 }} />
                          <YAxis tick={{ fill: 'rgba(255,255,255,0.4)', fontSize: 10 }} />
                          <Tooltip
                            contentStyle={{ background: '#1e1e2e', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8 }}
                            labelFormatter={formatMonth}
                            formatter={(v: number) => [`${v}%`, '% Target']}
                          />
                          <Area type="monotone" dataKey="target_pct" stroke="#6366f1" fill="url(#perfGrad)" strokeWidth={2} dot={false} />
                        </AreaChart>
                      </ResponsiveContainer>
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
