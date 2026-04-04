import { useEffect, useMemo, useState } from 'react';
import {
  ChevronDown,
  Database,
  FileSpreadsheet,
  Pencil,
  Plus,
  Shield,
  Trash2,
  Upload,
  Users,
  X,
} from 'lucide-react';
import {
  createAdminUser,
  deleteAdminUser,
  getAdminUsers,
  updateAdminUser,
  updateTlAssignments,
} from '../api/admin';
import { getImportHistory, uploadSalesFile } from '../api/imports';
import { getStores } from '../api/stores';
import type {
  AdminUser,
  AdminUserCreate,
  AuthUser,
  ImportHistoryEntry,
  StoreOption,
} from '../api/types';
import { cn } from '../lib/utils';
import { getCachedView, setCachedView } from '../lib/viewCache';
import { getRoleAccessLabel, type Role } from '../lib/roles';

interface SettingsProps {
  user: AuthUser | null;
  onImportCompleted: (month: string) => void;
}

const SETTINGS_CACHE_TTL_MS = 5 * 60 * 1000;

const ROLE_OPTIONS = [
  { id: 'tl', label: 'TL' },
  { id: 'asm', label: 'ASM' },
  { id: 'management', label: 'Management' },
  { id: 'admin', label: 'Admin' },
] as const;

export function Settings({
  user,
  onImportCompleted,
}: SettingsProps) {
  const [history, setHistory] = useState<ImportHistoryEntry[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [message, setMessage] = useState('');
  const [messageType, setMessageType] = useState<'success' | 'error'>('success');
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [stores, setStores] = useState<StoreOption[]>([]);
  const [newUser, setNewUser] = useState<AdminUserCreate>({
    username: '',
    full_name: '',
    password: '9999',
    role: 'tl',
    is_active: true,
  });
  const [editingUserId, setEditingUserId] = useState<number | null>(null);
  const [createPanelOpen, setCreatePanelOpen] = useState(false);
  const [selectedTlId, setSelectedTlId] = useState<number | null>(null);
  const [selectedSiteCodes, setSelectedSiteCodes] = useState<string[]>([]);

  useEffect(() => {
    if (user?.role !== 'admin') {
      return;
    }

    const cacheKey = `settings:admin:${user.id}`;
    const cached = getCachedView<{
      history: ImportHistoryEntry[];
      users: AdminUser[];
      stores: StoreOption[];
    }>(cacheKey, SETTINGS_CACHE_TTL_MS);
    if (cached.value) {
      setHistory(cached.value.history);
      setUsers(cached.value.users);
      setStores(cached.value.stores);
      if (cached.isFresh) {
        return;
      }
    }

    Promise.all([getImportHistory(), getAdminUsers(), getStores()])
      .then(([historyData, userData, storeData]) => {
        setHistory(historyData);
        setUsers(userData);
        setStores(storeData);
        setCachedView(cacheKey, {
          history: historyData,
          users: userData,
          stores: storeData,
        });
      })
      .catch(() => {
        setHistory([]);
        setUsers([]);
        setStores([]);
        setMessage('Nu am putut încărca datele de administrare.');
        setMessageType('error');
      });
  }, [user?.id, user?.role]);

  const tlUsers = useMemo(() => users.filter((entry) => entry.role === 'tl'), [users]);
  const selectedTl = tlUsers.find((entry) => entry.id === selectedTlId) ?? null;

  useEffect(() => {
    if (!selectedTl && tlUsers[0]) {
      setSelectedTlId(tlUsers[0].id);
      setSelectedSiteCodes(tlUsers[0].assigned_site_codes);
      return;
    }
    if (selectedTl) {
      setSelectedSiteCodes(selectedTl.assigned_site_codes);
    }
  }, [selectedTlId, tlUsers, selectedTl]);

  const handleUpload = async () => {
    if (!file) return;
    try {
      setUploading(true);
      setMessage('');
      setMessageType('success');
      const response = await uploadSalesFile(file);
      setHistory((previous) => [
        {
          id: response.snapshot_id,
          import_month: response.import_month,
          filename: response.filename,
          upload_date: new Date().toISOString().slice(0, 10),
          is_month_final: response.is_month_final,
          rows_in_file: response.rows_in_file,
          rows_imported: response.rows_imported,
          status: 'completed',
          error_message: null,
          imported_by: user?.id ?? null,
          created_at: new Date().toISOString(),
        },
        ...previous,
      ]);
      onImportCompleted(response.import_month);
      const parts = [
        `Import ${response.import_month}: ${response.rows_imported} rânduri importate`,
      ];
      if (response.rows_filtered > 0) {
        parts.push(`${response.rows_filtered} rânduri non-ASM filtrate`);
      }
      if (response.is_month_final) {
        parts.push('Luna a fost marcată ca FINALĂ');
      } else {
        parts.push('Import intermediar (lună în curs)');
      }
      setMessage(parts.join(' · '));
      setFile(null);
    } catch {
      setMessage('Importul a eșuat. Verifică fișierul și încearcă din nou.');
      setMessageType('error');
    } finally {
      setUploading(false);
    }
  };

  const handleCreateOrUpdateUser = async () => {
    if (!newUser.username.trim()) return;
    try {
      setMessage('');
      setMessageType('success');
      if (editingUserId !== null) {
        const updated = await updateAdminUser(editingUserId, {
          full_name: newUser.full_name,
          role: newUser.role,
          is_active: newUser.is_active,
          ...(newUser.password ? { password: newUser.password } : {}),
        });
        setUsers((previous) =>
          previous.map((entry) => (entry.id === updated.id ? updated : entry))
        );
        setMessage(`Utilizatorul ${updated.username} a fost actualizat.`);
        setEditingUserId(null);
        resetForm();
      } else {
        const created = await createAdminUser(newUser);
        setUsers((previous) =>
          [...previous, created].sort((a, b) => a.username.localeCompare(b.username))
        );
        setMessage(`Utilizatorul ${created.username} a fost creat.`);
        resetForm();
        setCreatePanelOpen(false);
      }
    } catch (err) {
      console.error(err);
      setMessage('Nu am putut salva utilizatorul.');
      setMessageType('error');
    }
  };

  const handleDeleteUser = async (id: number, username: string) => {
    try {
      setMessage('');
      setMessageType('success');
      await deleteAdminUser(id);
      setUsers((previous) => previous.filter((entry) => entry.id !== id));
      setMessage(`Utilizatorul ${username} a fost șters.`);
    } catch (err) {
      console.error(err);
      setMessage('Nu am putut șterge utilizatorul.');
      setMessageType('error');
    }
  };

  const handleEditUser = (entry: AdminUser) => {
    setCreatePanelOpen(false);
    setEditingUserId(entry.id);
    setNewUser({
      username: entry.username,
      full_name: entry.full_name ?? '',
      password: '',
      role: entry.role,
      is_active: entry.is_active,
    });
  };

  const handleCancelEdit = () => {
    setEditingUserId(null);
    resetForm();
  };

  const handleCancelCreate = () => {
    setCreatePanelOpen(false);
    resetForm();
  };

  const resetForm = () => {
    setNewUser({ username: '', full_name: '', password: '9999', role: 'tl', is_active: true });
  };

  const handleSaveAssignments = async () => {
    if (!selectedTlId) return;
    try {
      setMessage('');
      setMessageType('success');
      const updated = await updateTlAssignments(selectedTlId, selectedSiteCodes);
      setUsers((previous) =>
        previous.map((entry) => (entry.id === updated.id ? updated : entry))
      );
      setMessage(`Alocările TL pentru ${updated.username} au fost salvate.`);
    } catch {
      setMessage('Nu am putut salva alocările TL.');
      setMessageType('error');
    }
  };

  return (
    <div className="space-y-3 p-3 pb-24 pt-2">
      <div>
        <h1 className="text-xl font-bold tracking-tight">Setări</h1>
        <p className="text-xs text-slate-500 dark:text-slate-400">
          {user?.role === 'admin' ? 'Administrare aplicație' : 'Tema și contul tău'}
        </p>
      </div>

      <div className="glass rounded-3xl p-4">
        <div className="mb-3 flex items-center gap-2">
          <Database size={16} className="text-indigo-500" />
          <h3 className="text-sm font-bold">Status cont</h3>
        </div>
        <div className="rounded-2xl bg-slate-50 p-3 text-xs dark:bg-slate-800/60">
          <div className="font-semibold">Utilizator: {user?.full_name ?? user?.username}</div>
          <div className="mt-1 text-slate-500">Rol: {user?.role}</div>
        </div>
      </div>

      {user?.role === 'admin' && (
        <>
          <div className="glass rounded-3xl p-4">
            <div className="mb-3 flex items-center gap-2">
              <Upload size={16} className="text-indigo-500" />
              <h3 className="text-sm font-bold">Import fișier vânzări</h3>
            </div>
            <label
              htmlFor="upload-sales-file"
              className={cn(
                'mb-3 flex cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed px-4 py-6 text-center transition-all',
                file
                  ? 'border-emerald-400 bg-emerald-50 dark:border-emerald-600 dark:bg-emerald-950/20'
                  : 'border-slate-300 bg-slate-50 hover:border-indigo-400 hover:bg-indigo-50/50 dark:border-slate-600 dark:bg-slate-800/60 dark:hover:border-indigo-500'
              )}
            >
              {file ? (
                <>
                  <FileSpreadsheet size={20} className="mb-1 text-emerald-500" />
                  <span className="text-xs font-semibold text-emerald-700 dark:text-emerald-300">
                    {file.name}
                  </span>
                  <span className="mt-0.5 text-[11px] text-slate-400">
                    {(file.size / 1024).toFixed(1)} KB · Click pentru a schimba
                  </span>
                </>
              ) : (
                <>
                  <Upload size={20} className="mb-1 text-slate-400" />
                  <span className="text-xs font-semibold text-slate-600 dark:text-slate-300">
                    Click sau drag & drop pentru a încărca
                  </span>
                  <span className="mt-0.5 text-[11px] text-slate-400">
                    .xlsx, .xls
                  </span>
                </>
              )}
              <input
                id="upload-sales-file"
                type="file"
                accept=".xlsx,.xls"
                onChange={(event) => setFile(event.target.files?.[0] ?? null)}
                className="hidden"
              />
            </label>
            <button
              onClick={() => void handleUpload()}
              disabled={!file || uploading}
              className="w-full rounded-2xl bg-indigo-600 px-4 py-3 text-xs font-bold text-white shadow-lg shadow-indigo-500/30 disabled:opacity-60"
            >
              {uploading ? 'Se încarcă...' : 'Importă fișier'}
            </button>
            {message && (
              <div className={`mt-3 rounded-2xl px-3 py-2 text-xs font-semibold ${
                messageType === 'error'
                  ? 'bg-rose-50 text-rose-700 dark:bg-rose-950/30 dark:text-rose-300'
                  : 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-300'
              }`}>
                {message}
              </div>
            )}
          </div>

          <div className="glass rounded-3xl p-4">
            <div className="mb-3 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Users size={16} className="text-indigo-500" />
                <h3 className="text-sm font-bold">Utilizatori</h3>
              </div>
              <button
                onClick={() => {
                  if (createPanelOpen) {
                    handleCancelCreate();
                  } else {
                    setCreatePanelOpen(true);
                    setEditingUserId(null);
                    resetForm();
                  }
                }}
                className="flex items-center gap-1.5 rounded-2xl bg-indigo-600 px-3 py-1.5 text-xs font-bold text-white shadow-sm transition-all hover:bg-indigo-700"
              >
                <Plus size={12} />
                {createPanelOpen ? 'Anulează' : 'Crează user'}
              </button>
            </div>

            {createPanelOpen && (
              <div className="mb-4 rounded-2xl border border-indigo-200 bg-indigo-50/50 p-3 dark:border-indigo-800 dark:bg-indigo-950/20">
                <div className="mb-2.5 text-xs font-bold text-indigo-600 dark:text-indigo-400">
                  Creare utilizator nou
                </div>
                <div className="mb-3 flex gap-1.5 rounded-2xl bg-slate-100 p-1 dark:bg-slate-800">
                  {ROLE_OPTIONS.map((opt) => (
                    <button
                      key={opt.id}
                      onClick={() => setNewUser({ ...newUser, role: opt.id })}
                      className={cn(
                        'flex-1 rounded-xl px-2 py-1.5 text-center text-[10px] font-bold transition-all',
                        newUser.role === opt.id
                          ? 'bg-white text-indigo-600 shadow-sm dark:bg-slate-700 dark:text-indigo-400'
                          : 'text-slate-400 hover:text-slate-600 dark:hover:text-slate-300'
                      )}
                    >
                      {opt.label}
                    </button>
                  ))}
                </div>
                <div className="mb-2 rounded-xl bg-emerald-100 px-2.5 py-1.5 text-[10px] text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300">
                  Va avea acces la: {getRoleAccessLabel(newUser.role as Role)}
                </div>
                <div className="mb-3 grid grid-cols-2 gap-2">
                  <input
                    value={newUser.username}
                    onChange={(event) => setNewUser({ ...newUser, username: event.target.value })}
                    placeholder="username"
                    className="rounded-2xl border border-slate-200 bg-white px-3 py-2 text-xs outline-none dark:border-slate-700 dark:bg-slate-800"
                  />
                  <input
                    value={newUser.full_name}
                    onChange={(event) => setNewUser({ ...newUser, full_name: event.target.value })}
                    placeholder="nume complet"
                    className="rounded-2xl border border-slate-200 bg-white px-3 py-2 text-xs outline-none dark:border-slate-700 dark:bg-slate-800"
                  />
                  <input
                    value={newUser.password}
                    onChange={(event) => setNewUser({ ...newUser, password: event.target.value })}
                    placeholder="parolă"
                    className="rounded-2xl border border-slate-200 bg-white px-3 py-2 text-xs outline-none dark:border-slate-700 dark:bg-slate-800"
                  />
                  <div className="flex items-center gap-2">
                    <select
                      value={newUser.role}
                      onChange={(event) =>
                        setNewUser({
                          ...newUser,
                          role: event.target.value as Role,
                        })
                      }
                      className="flex-1 rounded-2xl border border-slate-200 bg-white px-2 py-2 text-xs outline-none dark:border-slate-700 dark:bg-slate-800"
                    >
                      {ROLE_OPTIONS.map((opt) => (
                        <option key={opt.id} value={opt.id}>{opt.label}</option>
                      ))}
                    </select>
                    <label className="flex items-center gap-1 text-[10px] text-slate-500">
                      <input
                        type="checkbox"
                        checked={newUser.is_active}
                        onChange={(event) => setNewUser({ ...newUser, is_active: event.target.checked })}
                        className="accent-indigo-600"
                      />
                      activ
                    </label>
                  </div>
                </div>
                <button
                  onClick={() => void handleCreateOrUpdateUser()}
                  className="w-full rounded-2xl bg-indigo-600 px-4 py-2.5 text-xs font-bold text-white shadow-sm hover:bg-indigo-700"
                >
                  {editingUserId !== null ? 'Salvează modificări' : 'Crează utilizator'}
                </button>
              </div>
            )}

            <div className="space-y-2">
              {users.map((entry) => (
                <div key={entry.id}>
                  <div
                    className={cn(
                      'flex items-center justify-between rounded-2xl bg-slate-50 p-3 text-xs dark:bg-slate-800/60',
                      editingUserId === entry.id && 'ring-2 ring-indigo-400'
                    )}
                  >
                    <div className="min-w-0 flex-1">
                      <div className="font-semibold">{entry.username}</div>
                      <div className="mt-0.5 text-slate-500">
                        {entry.full_name ?? 'Fără nume'} · {entry.role} ·{' '}
                        {entry.is_active ? 'activ' : 'inactiv'}
                      </div>
                      {entry.role === 'tl' && (
                        <div className="mt-0.5 text-slate-400">
                          {entry.assignment_count} magazine alocate
                        </div>
                      )}
                    </div>
                    <div className="flex items-center gap-1 ml-2">
                      <button
                        onClick={() =>
                          editingUserId === entry.id
                            ? handleCancelEdit()
                            : handleEditUser(entry)
                        }
                        className={cn(
                          'flex h-7 w-7 items-center justify-center rounded-xl transition-all',
                          editingUserId === entry.id
                            ? 'bg-indigo-100 text-indigo-600 dark:bg-indigo-900/30 dark:text-indigo-400'
                            : 'bg-slate-100 text-slate-500 hover:bg-indigo-100 hover:text-indigo-600 dark:bg-slate-700 dark:text-slate-400 dark:hover:bg-indigo-900/30 dark:hover:text-indigo-400'
                        )}
                        title={editingUserId === entry.id ? 'Anulează' : 'Editează'}
                      >
                        {editingUserId === entry.id ? <ChevronDown size={12} className="rotate-180" /> : <Pencil size={12} />}
                      </button>
                      <button
                        onClick={() => {
                          if (window.confirm(`Ștergi utilizatorul "${entry.username}"?`)) {
                            void handleDeleteUser(entry.id, entry.username);
                          }
                        }}
                        className="flex h-7 w-7 items-center justify-center rounded-xl bg-slate-100 text-slate-500 hover:bg-red-100 hover:text-red-500 dark:bg-slate-700 dark:text-slate-400 dark:hover:bg-red-950/30 dark:hover:text-red-400"
                        title="Șterge"
                      >
                        <Trash2 size={12} />
                      </button>
                    </div>
                  </div>

                  {editingUserId === entry.id && (
                    <div className="mt-1 rounded-2xl border border-indigo-200 bg-indigo-50/50 p-3 dark:border-indigo-800 dark:bg-indigo-950/20">
                      <div className="mb-2 text-xs font-bold text-indigo-600 dark:text-indigo-400">
                        Editează: {entry.username}
                      </div>
                        <div className="mb-3 flex gap-1.5 rounded-2xl bg-slate-100 p-1 dark:bg-slate-800">
                          {ROLE_OPTIONS.map((opt) => (
                            <button
                              key={opt.id}
                              onClick={() => setNewUser({ ...newUser, role: opt.id })}
                              className={cn(
                                'flex-1 rounded-xl px-2 py-1.5 text-center text-[10px] font-bold transition-all',
                                newUser.role === opt.id
                                  ? 'bg-white text-indigo-600 shadow-sm dark:bg-slate-700 dark:text-indigo-400'
                                  : 'text-slate-400 hover:text-slate-600 dark:hover:text-slate-300'
                              )}
                            >
                              {opt.label}
                            </button>
                          ))}
                        </div>
                        <div className="mb-2 rounded-xl bg-emerald-100 px-2.5 py-1.5 text-[10px] text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300">
                          Va avea acces la: {getRoleAccessLabel(newUser.role as Role)}
                        </div>
                        <div className="mb-3 grid grid-cols-2 gap-2">
                          <input
                            value={newUser.username}
                            disabled
                            className="col-span-2 rounded-2xl border border-slate-200 bg-slate-100 px-3 py-2 text-xs outline-none dark:border-slate-700 dark:bg-slate-800"
                          />
                          <input
                            value={newUser.full_name}
                            onChange={(event) => setNewUser({ ...newUser, full_name: event.target.value })}
                            placeholder="nume complet"
                            className="rounded-2xl border border-slate-200 bg-white px-3 py-2 text-xs outline-none dark:border-slate-700 dark:bg-slate-800"
                          />
                          <input
                            value={newUser.password}
                            onChange={(event) => setNewUser({ ...newUser, password: event.target.value })}
                            placeholder="lasă necompletat pt. a păstra parola"
                            className="rounded-2xl border border-slate-200 bg-white px-3 py-2 text-xs outline-none dark:border-slate-700 dark:bg-slate-800"
                          />
                          <div className="col-span-2 flex items-center gap-2">
                            <label className="flex items-center gap-1.5 text-xs text-slate-500">
                              <input
                                type="checkbox"
                                checked={newUser.is_active}
                                onChange={(event) => setNewUser({ ...newUser, is_active: event.target.checked })}
                                className="accent-indigo-600"
                              />
                              cont activ
                            </label>
                          </div>
                        </div>
                      <button
                        onClick={() => void handleCreateOrUpdateUser()}
                        className="w-full rounded-2xl bg-indigo-600 px-4 py-2.5 text-xs font-bold text-white shadow-sm hover:bg-indigo-700"
                      >
                        Salvează modificări
                      </button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>

          <div className="glass rounded-3xl p-4">
            <div className="mb-3 flex items-center gap-2">
              <Shield size={16} className="text-indigo-500" />
              <h3 className="text-sm font-bold">Alocări TL</h3>
            </div>
            <select
              value={selectedTlId ?? ''}
              onChange={(event) => setSelectedTlId(Number(event.target.value))}
              className="mb-3 w-full rounded-2xl border border-slate-200 bg-slate-50 px-3 py-3 text-xs outline-none dark:border-slate-700 dark:bg-slate-800"
            >
              {tlUsers.map((entry) => (
                <option key={entry.id} value={entry.id}>
                  {entry.username}
                </option>
              ))}
            </select>
            <div className="max-h-64 space-y-2 overflow-y-auto rounded-2xl bg-slate-50 p-3 dark:bg-slate-800/60">
              {stores.map((store) => {
                const checked = selectedSiteCodes.includes(store.site_code);
                return (
                  <label key={store.site_code} className="flex items-center gap-2 text-xs">
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={(event) => {
                        setSelectedSiteCodes((previous) =>
                          event.target.checked
                            ? [...previous, store.site_code].sort()
                            : previous.filter((item) => item !== store.site_code)
                        );
                      }}
                    />
                    <span>
                      {store.locatie} ({store.site_code})
                    </span>
                  </label>
                );
              })}
            </div>
            <button
              onClick={() => void handleSaveAssignments()}
              className="mt-3 w-full rounded-2xl bg-indigo-600 px-4 py-3 text-xs font-bold text-white shadow-lg shadow-indigo-500/30"
            >
              Salvează alocările TL
            </button>
          </div>

          <div className="glass rounded-3xl p-4">
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-sm font-bold">Istoric importuri</h3>
              <span className="text-[11px] text-slate-500">{history.length} snapshot-uri</span>
            </div>
            <div className="max-h-40 space-y-2 overflow-y-auto">
              {history.slice(0, 8).map((entry) => (
                <div
                  key={entry.id}
                  className="rounded-2xl bg-slate-50 p-3 text-xs dark:bg-slate-800/60"
                >
                  <div className="font-semibold">
                    {entry.import_month} · {entry.filename}
                  </div>
                  <div className="mt-1 text-slate-500">
                    {entry.rows_imported ?? 0} rânduri · {entry.status} ·{' '}
                    {entry.is_month_final ? '✓ Final' : 'Intermediar'} ·{' '}
                    {entry.created_at.slice(0, 16).replace('T', ' ')}
                  </div>
                </div>
              ))}
              {history.length === 0 && (
                <div className="text-sm font-semibold text-slate-500">Nu există istoric încă.</div>
              )}
            </div>
          </div>
        </>
      )}

      {message && user?.role !== 'admin' && (
        <div className="mt-3 rounded-2xl bg-emerald-50 px-3 py-2 text-xs font-semibold text-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-300">
          {message}
        </div>
      )}
    </div>
  );
}
