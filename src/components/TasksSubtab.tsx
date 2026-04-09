import { useEffect, useState } from 'react';
import { Plus, Trash2, RefreshCw, ChevronDown } from 'lucide-react';
import {
  fetchTasks, createTask, updateTask, deleteTask,
  fetchMyTasks, updateMyTask,
  type Task,
} from '../api/tasks';
import { fetchAssignableUsers, type AssignableUser } from '../api/hr';

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

const ROLE_LABEL: Record<string, string> = { asm: 'ASM', tl: 'TL' };

interface Props {
  userRole?: string;
  userFullName?: string;
}

export function TasksSubtab({ userRole, userFullName }: Props) {
  const isManager = userRole === 'admin' || userRole === 'management';
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<string>('');
  const [showForm, setShowForm] = useState(false);
  const [users, setUsers] = useState<AssignableUser[]>([]);

  // Form state
  const [newTitle, setNewTitle] = useState('');
  const [newAssignee, setNewAssignee] = useState('');
  const [newSiteCode, setNewSiteCode] = useState('');
  const [newDeadline, setNewDeadline] = useState('');
  const [userDropdownOpen, setUserDropdownOpen] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const params = filter ? { status: filter } : undefined;
      const data = isManager
        ? await fetchTasks(params)
        : await fetchMyTasks(filter || undefined);
      setTasks(data);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [filter, isManager]);
  useEffect(() => {
    if (isManager) {
      fetchAssignableUsers().then(setUsers).catch(() => {});
    }
  }, [isManager]);

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
    const nextStatus = STATUS_NEXT[task.status];
    if (isManager) {
      await updateTask(task.id, { status: nextStatus });
    } else {
      await updateMyTask(task.id, { status: nextStatus });
    }
    await load();
  };

  const handleDelete = async (id: number) => {
    await deleteTask(id);
    await load();
  };

  const inputCls = 'rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:placeholder-slate-500';

  const deadlineColor = (deadline: string | null) => {
    if (!deadline) return '';
    const d = new Date(deadline);
    const now = new Date();
    const diff = (d.getTime() - now.getTime()) / (1000 * 60 * 60 * 24);
    if (diff < 0) return 'text-red-600 dark:text-red-400 font-semibold';
    if (diff <= 2) return 'text-amber-600 dark:text-amber-400 font-semibold';
    return '';
  };

  return (
    <div className="p-4 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex gap-1.5 flex-wrap">
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
          {isManager && (
            <button
              onClick={() => setShowForm(!showForm)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-medium"
            >
              <Plus size={14} /> Task nou
            </button>
          )}
        </div>
      </div>

      {/* Banner pentru non-manageri */}
      {!isManager && (
        <div className="rounded-2xl bg-indigo-50 dark:bg-indigo-900/20 border border-indigo-200 dark:border-indigo-800 px-4 py-2.5">
          <p className="text-xs text-indigo-700 dark:text-indigo-300 font-medium">
            Taskuri asignate ție{userFullName ? ` — ${userFullName}` : ''}
          </p>
        </div>
      )}

      {/* Form creare (doar manageri) */}
      {showForm && isManager && (
        <div className="glass rounded-2xl p-4 space-y-3">
          <input
            className={`w-full ${inputCls}`}
            placeholder="Titlu task *"
            value={newTitle}
            onChange={(e) => setNewTitle(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleCreate()}
          />
          <div className="grid grid-cols-3 gap-2">
            {/* Dropdown assignee */}
            <div className="relative">
              <button
                type="button"
                onClick={() => setUserDropdownOpen(!userDropdownOpen)}
                className={`w-full flex items-center justify-between ${inputCls} cursor-pointer`}
              >
                <span className={newAssignee ? 'text-slate-700 dark:text-slate-300' : 'text-slate-400 dark:text-slate-500'}>
                  {newAssignee || 'Responsabil'}
                </span>
                <ChevronDown size={14} className="text-slate-400 shrink-0" />
              </button>
              {userDropdownOpen && (
                <div className="absolute top-full left-0 right-0 mt-1 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 shadow-lg z-20 max-h-48 overflow-y-auto">
                  <button
                    onClick={() => { setNewAssignee(''); setUserDropdownOpen(false); }}
                    className="w-full px-3 py-2 text-left text-xs text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-700"
                  >
                    Fără responsabil
                  </button>
                  {['asm', 'tl'].map((role) => {
                    const group = users.filter((u) => u.role === role);
                    if (!group.length) return null;
                    return (
                      <div key={role}>
                        <div className="px-3 py-1 text-[10px] font-bold uppercase tracking-wider text-slate-400 bg-slate-50 dark:bg-slate-900">
                          {ROLE_LABEL[role]}
                        </div>
                        {group.map((u) => (
                          <button
                            key={u.username}
                            onClick={() => { setNewAssignee(u.full_name); setUserDropdownOpen(false); }}
                            className="w-full px-3 py-2 text-left text-sm text-slate-700 dark:text-slate-300 hover:bg-indigo-50 dark:hover:bg-indigo-900/30"
                          >
                            {u.full_name}
                          </button>
                        ))}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
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
          <div className="text-center text-slate-400 py-8 text-sm">
            {isManager
              ? `Niciun task${filter ? ` cu status "${STATUS_LABELS[filter]}"` : ''}`
              : 'Nu ai taskuri asignate momentan'}
          </div>
        )}
        {tasks.map((task) => (
          <div key={task.id} className="glass rounded-2xl px-4 py-3 flex items-center gap-3">
            <button
              onClick={() => handleStatusCycle(task)}
              title="Click pentru a avansa statusul"
              className={`shrink-0 px-2.5 py-1 rounded-full text-xs font-medium cursor-pointer transition-colors ${STATUS_COLORS[task.status]}`}
            >
              {STATUS_LABELS[task.status]}
            </button>
            <div className="flex-1 min-w-0">
              <p className={`text-sm font-medium ${task.status === 'inchis' ? 'line-through text-slate-400' : 'text-slate-800 dark:text-slate-200'}`}>
                {task.title}
              </p>
              <div className="flex flex-wrap gap-x-3 mt-0.5">
                {task.assignee && (
                  <span className="text-xs text-slate-400">{task.assignee}</span>
                )}
                {task.site_code && (
                  <span className="text-xs text-slate-400">{task.site_code}</span>
                )}
                {task.deadline && (
                  <span className={`text-xs ${deadlineColor(task.deadline) || 'text-slate-400'}`}>
                    {task.deadline}
                  </span>
                )}
              </div>
            </div>
            {isManager && (
              <button
                onClick={() => handleDelete(task.id)}
                className="shrink-0 p-1.5 rounded-lg text-slate-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
              >
                <Trash2 size={14} />
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
