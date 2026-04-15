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
  pending: <Clock size={14} className="text-amber-500" />,
  approved: <CheckCircle size={14} className="text-green-500" />,
  rejected: <XCircle size={14} className="text-red-500" />,
};
const STATUS_LABEL = { pending: 'În așteptare', approved: 'Aprobat', rejected: 'Respins' };
const LEAVE_LABELS: Record<string, string> = { odihna: 'Odihnă', medical: 'Medical', altul: 'Alt motiv' };

const inputCls = 'rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:placeholder-slate-500';

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
      setRequests(await fetchLeaveRequests(filterStatus ? { status: filterStatus } : undefined));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [filterStatus]);

  const handleCreate = async () => {
    if (!form.agent_name || !form.start_date || !form.end_date) return;
    try {
      await createLeaveRequest({ ...form, notes: form.notes || undefined });
      setForm({ agent_name: '', start_date: '', end_date: '', leave_type: 'odihna', notes: '' });
      setShowForm(false);
      await load();
    } catch (err) {
      console.error('Failed to create leave request', err);
    }
  };

  const handleStatus = async (id: number, status: 'approved' | 'rejected') => {
    try {
      await updateLeaveStatus(id, status);
      await load();
    } catch (err) {
      console.error('Failed to update leave request status', err);
    }
  };

  const handleSelectAgent = async (name: string) => {
    if (selectedAgent === name) { setSelectedAgent(null); return; }
    setSelectedAgent(name);
    setPerfLoading(true);
    try { setPerfData(await fetchAgentPerformance(name)); }
    finally { setPerfLoading(false); }
  };

  const formatMonth = (m: string) => {
    const [y, mo] = m.split('-');
    const labels = ['Ian', 'Feb', 'Mar', 'Apr', 'Mai', 'Iun', 'Iul', 'Aug', 'Sep', 'Oct', 'Noi', 'Dec'];
    return `${labels[parseInt(mo) - 1]} ${y.slice(2)}`;
  };

  return (
    <div className="p-4 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500">Cereri concediu</h3>
        <div className="flex gap-1.5 flex-wrap">
          {['', 'pending', 'approved', 'rejected'].map((s) => (
            <button
              key={s}
              onClick={() => setFilterStatus(s)}
              className={`px-2.5 py-1 rounded-full text-xs font-medium transition-colors ${
                filterStatus === s
                  ? 'bg-indigo-600 text-white'
                  : 'bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-400 dark:hover:bg-slate-700'
              }`}
            >
              {s === '' ? 'Toate' : STATUS_LABEL[s as keyof typeof STATUS_LABEL]}
            </button>
          ))}
          <button onClick={load} className="p-1.5 rounded-xl bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-500">
            <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
          </button>
          <button
            onClick={() => setShowForm(!showForm)}
            className="px-3 py-1.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-medium"
          >
            + Cerere nouă
          </button>
        </div>
      </div>

      {/* Form */}
      {showForm && (
        <div className="glass rounded-2xl p-4 space-y-3">
          <div className="grid grid-cols-2 gap-2">
            <input className={`col-span-2 ${inputCls}`} placeholder="Nume agent *" value={form.agent_name} onChange={(e) => setForm({ ...form, agent_name: e.target.value })} />
            <input type="date" className={inputCls} value={form.start_date} onChange={(e) => setForm({ ...form, start_date: e.target.value })} />
            <input type="date" className={inputCls} value={form.end_date} onChange={(e) => setForm({ ...form, end_date: e.target.value })} />
            <select className={inputCls} value={form.leave_type} onChange={(e) => setForm({ ...form, leave_type: e.target.value })}>
              <option value="odihna">Odihnă</option>
              <option value="medical">Medical</option>
              <option value="altul">Alt motiv</option>
            </select>
            <input className={inputCls} placeholder="Note (opțional)" value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
          </div>
          <div className="flex justify-end gap-2">
            <button onClick={() => setShowForm(false)} className="px-4 py-2 text-sm text-slate-500 hover:text-slate-700 dark:hover:text-slate-300">Anulează</button>
            <button onClick={handleCreate} className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-sm rounded-xl font-medium">Salvează</button>
          </div>
        </div>
      )}

      {/* Lista cereri */}
      <div className="space-y-2">
        {requests.length === 0 && !loading && (
          <div className="text-center text-slate-400 py-6 text-sm">Nicio cerere</div>
        )}
        {requests.map((r) => (
          <div key={r.id} className="glass rounded-2xl px-4 py-3">
            <div className="flex items-center gap-3">
              {STATUS_ICON[r.status]}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => handleSelectAgent(r.agent_name)}
                    className="text-sm font-medium text-slate-800 dark:text-slate-200 hover:text-indigo-600 dark:hover:text-indigo-400 transition-colors flex items-center gap-1"
                  >
                    {r.agent_name}
                    {selectedAgent === r.agent_name ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                  </button>
                  <span className="text-xs text-slate-400">{LEAVE_LABELS[r.leave_type] ?? r.leave_type}</span>
                </div>
                <p className="text-xs text-slate-400 mt-0.5">{r.start_date} → {r.end_date}{r.notes ? ` · ${r.notes}` : ''}</p>
              </div>
              {r.status === 'pending' && (
                <div className="flex gap-1.5 shrink-0">
                  <button onClick={() => handleStatus(r.id, 'approved')} className="px-2.5 py-1 rounded-lg text-xs bg-green-100 text-green-700 hover:bg-green-200 dark:bg-green-900/40 dark:text-green-300 font-medium">Aprobă</button>
                  <button onClick={() => handleStatus(r.id, 'rejected')} className="px-2.5 py-1 rounded-lg text-xs bg-red-100 text-red-700 hover:bg-red-200 dark:bg-red-900/40 dark:text-red-300 font-medium">Respinge</button>
                </div>
              )}
            </div>

            {selectedAgent === r.agent_name && (
              <div className="mt-3 pt-3 border-t border-slate-200 dark:border-slate-700">
                {perfLoading ? (
                  <div className="text-center text-slate-400 text-xs py-4">Se încarcă...</div>
                ) : perfData.length === 0 ? (
                  <div className="text-center text-slate-400 text-xs py-4">Date indisponibile</div>
                ) : (
                  <div className="h-40">
                    <ResponsiveContainer width="100%" height="100%">
                      <AreaChart data={perfData} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
                        <defs>
                          <linearGradient id="perfGrad" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor="#6366f1" stopOpacity={0.3} />
                            <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                          </linearGradient>
                        </defs>
                        <CartesianGrid strokeDasharray="3 3" stroke="rgba(100,116,139,0.15)" />
                        <XAxis dataKey="import_month" tickFormatter={formatMonth} tick={{ fill: '#94a3b8', fontSize: 10 }} />
                        <YAxis tick={{ fill: '#94a3b8', fontSize: 10 }} />
                        <Tooltip
                          contentStyle={{ background: 'var(--glass-bg)', border: '1px solid var(--glass-border)', borderRadius: 8, fontSize: 12 }}
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
  );
}
