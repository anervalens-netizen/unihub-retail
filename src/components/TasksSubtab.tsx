import { useEffect, useState } from 'react';
import { Plus, Trash2, RefreshCw } from 'lucide-react';
import { fetchTasks, createTask, updateTask, deleteTask, type Task } from '../api/tasks';

const STATUS_LABELS: Record<string, string> = {
  deschis: 'Deschis',
  in_lucru: 'În lucru',
  inchis: 'Închis',
};

const STATUS_COLORS: Record<string, string> = {
  deschis: 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300',
  in_lucru: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
  inchis: 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300',
};

const STATUS_NEXT: Record<string, string> = {
  deschis: 'in_lucru',
  in_lucru: 'inchis',
  inchis: 'deschis',
};

export function TasksSubtab() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<string>('');
  const [showForm, setShowForm] = useState(false);
  const [newTitle, setNewTitle] = useState('');
  const [newAssignee, setNewAssignee] = useState('');
  const [newSiteCode, setNewSiteCode] = useState('');
  const [newDeadline, setNewDeadline] = useState('');

  const load = async () => {
    setLoading(true);
    try {
      const data = await fetchTasks(filter ? { status: filter } : undefined);
      setTasks(data);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [filter]);

  const handleCreate = async () => {
    if (!newTitle.trim()) return;
    await createTask({
      title: newTitle.trim(),
      assignee: newAssignee || null,
      site_code: newSiteCode || null,
      deadline: newDeadline || null,
    });
    setNewTitle(''); setNewAssignee(''); setNewSiteCode(''); setNewDeadline('');
    setShowForm(false);
    await load();
  };

  const handleStatusCycle = async (task: Task) => {
    await updateTask(task.id, { status: STATUS_NEXT[task.status] });
    await load();
  };

  const handleDelete = async (id: number) => {
    await deleteTask(id);
    await load();
  };

  const inputCls = 'rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:placeholder-slate-500';

  return (
    <div className="p-4 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex gap-1.5">
          {['', 'deschis', 'in_lucru', 'inchis'].map((s) => (
            <button
              key={s}
              onClick={() => setFilter(s)}
              className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
                filter === s
                  ? 'bg-indigo-600 text-white'
                  : 'bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-400 dark:hover:bg-slate-700'
              }`}
            >
              {s === '' ? 'Toate' : STATUS_LABELS[s]}
            </button>
          ))}
        </div>
        <div className="flex gap-2">
          <button onClick={load} className="p-1.5 rounded-xl bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-500">
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          </button>
          <button
            onClick={() => setShowForm(!showForm)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-medium"
          >
            <Plus size={14} /> Task nou
          </button>
        </div>
      </div>

      {/* Form creare */}
      {showForm && (
        <div className="glass rounded-2xl p-4 space-y-3">
          <input className={`w-full ${inputCls}`} placeholder="Titlu task *" value={newTitle} onChange={(e) => setNewTitle(e.target.value)} />
          <div className="grid grid-cols-3 gap-2">
            <input className={inputCls} placeholder="Responsabil" value={newAssignee} onChange={(e) => setNewAssignee(e.target.value)} />
            <input className={inputCls} placeholder="Cod magazin" value={newSiteCode} onChange={(e) => setNewSiteCode(e.target.value)} />
            <input type="date" className={inputCls} value={newDeadline} onChange={(e) => setNewDeadline(e.target.value)} />
          </div>
          <div className="flex justify-end gap-2">
            <button onClick={() => setShowForm(false)} className="px-4 py-2 text-sm text-slate-500 hover:text-slate-700 dark:hover:text-slate-300">Anulează</button>
            <button onClick={handleCreate} className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-sm rounded-xl font-medium">Creează</button>
          </div>
        </div>
      )}

      {/* Lista */}
      <div className="space-y-2">
        {tasks.length === 0 && !loading && (
          <div className="text-center text-slate-400 py-8 text-sm">Niciun task{filter ? ` cu status "${STATUS_LABELS[filter]}"` : ''}</div>
        )}
        {tasks.map((task) => (
          <div key={task.id} className="glass rounded-2xl px-4 py-3 flex items-center gap-3">
            <button
              onClick={() => handleStatusCycle(task)}
              className={`shrink-0 px-2.5 py-1 rounded-full text-xs font-medium cursor-pointer transition-colors ${STATUS_COLORS[task.status]}`}
            >
              {STATUS_LABELS[task.status]}
            </button>
            <div className="flex-1 min-w-0">
              <p className={`text-sm font-medium ${task.status === 'inchis' ? 'line-through text-slate-400' : 'text-slate-800 dark:text-slate-200'}`}>
                {task.title}
              </p>
              <p className="text-xs text-slate-400 mt-0.5">
                {[task.assignee, task.site_code, task.deadline].filter(Boolean).join(' · ') || 'Fără detalii'}
              </p>
            </div>
            <button
              onClick={() => handleDelete(task.id)}
              className="shrink-0 p-1.5 rounded-lg text-slate-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
            >
              <Trash2 size={14} />
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
