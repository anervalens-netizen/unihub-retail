import { useEffect, useState } from 'react';
import { Plus, Trash2, RefreshCw } from 'lucide-react';
import { fetchTasks, createTask, updateTask, deleteTask, type Task } from '../api/tasks';

const STATUS_LABELS: Record<string, string> = {
  deschis: 'Deschis',
  in_lucru: 'În lucru',
  inchis: 'Închis',
};

const STATUS_COLORS: Record<string, string> = {
  deschis: 'bg-blue-500/20 text-blue-300',
  in_lucru: 'bg-yellow-500/20 text-yellow-300',
  inchis: 'bg-green-500/20 text-green-300',
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
    setNewTitle('');
    setNewAssignee('');
    setNewSiteCode('');
    setNewDeadline('');
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

  return (
    <div className="p-4 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex gap-2">
          {['', 'deschis', 'in_lucru', 'inchis'].map((s) => (
            <button
              key={s}
              onClick={() => setFilter(s)}
              className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
                filter === s ? 'bg-indigo-600 text-white' : 'bg-white/10 text-white/60 hover:bg-white/20'
              }`}
            >
              {s === '' ? 'Toate' : STATUS_LABELS[s]}
            </button>
          ))}
        </div>
        <div className="flex gap-2">
          <button onClick={load} className="p-1.5 rounded bg-white/10 hover:bg-white/20">
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          </button>
          <button
            onClick={() => setShowForm(!showForm)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-medium"
          >
            <Plus size={14} /> Task nou
          </button>
        </div>
      </div>

      {/* Form creare */}
      {showForm && (
        <div className="bg-white/5 border border-white/10 rounded-xl p-4 space-y-3">
          <input
            className="w-full bg-white/10 border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder-white/40 focus:outline-none focus:border-indigo-500"
            placeholder="Titlu task *"
            value={newTitle}
            onChange={(e) => setNewTitle(e.target.value)}
          />
          <div className="grid grid-cols-3 gap-2">
            <input
              className="bg-white/10 border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder-white/40 focus:outline-none focus:border-indigo-500"
              placeholder="Responsabil"
              value={newAssignee}
              onChange={(e) => setNewAssignee(e.target.value)}
            />
            <input
              className="bg-white/10 border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder-white/40 focus:outline-none focus:border-indigo-500"
              placeholder="Cod magazin"
              value={newSiteCode}
              onChange={(e) => setNewSiteCode(e.target.value)}
            />
            <input
              type="date"
              className="bg-white/10 border border-white/10 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500"
              value={newDeadline}
              onChange={(e) => setNewDeadline(e.target.value)}
            />
          </div>
          <div className="flex justify-end gap-2">
            <button
              onClick={() => setShowForm(false)}
              className="px-4 py-2 text-sm text-white/60 hover:text-white"
            >
              Anulează
            </button>
            <button
              onClick={handleCreate}
              className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-sm rounded-lg font-medium"
            >
              Creează
            </button>
          </div>
        </div>
      )}

      {/* Lista task-uri */}
      <div className="space-y-2">
        {tasks.length === 0 && !loading && (
          <div className="text-center text-white/40 py-8 text-sm">Niciun task{filter ? ` cu status "${STATUS_LABELS[filter]}"` : ''}</div>
        )}
        {tasks.map((task) => (
          <div key={task.id} className="bg-white/5 border border-white/10 rounded-xl px-4 py-3 flex items-center gap-3">
            <button
              onClick={() => handleStatusCycle(task)}
              className={`shrink-0 px-2.5 py-1 rounded-full text-xs font-medium cursor-pointer ${STATUS_COLORS[task.status]}`}
            >
              {STATUS_LABELS[task.status]}
            </button>
            <div className="flex-1 min-w-0">
              <p className={`text-sm font-medium ${task.status === 'inchis' ? 'line-through text-white/40' : 'text-white'}`}>
                {task.title}
              </p>
              <p className="text-xs text-white/40 mt-0.5">
                {[task.assignee, task.site_code, task.deadline].filter(Boolean).join(' · ') || 'Fără detalii'}
              </p>
            </div>
            <button
              onClick={() => handleDelete(task.id)}
              className="shrink-0 p-1.5 rounded text-white/30 hover:text-red-400 hover:bg-red-500/10 transition-colors"
            >
              <Trash2 size={14} />
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
