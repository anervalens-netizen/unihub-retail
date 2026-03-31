import React, { useState } from 'react';
import { motion } from 'motion/react';
import { AlertCircle, LockKeyhole, User } from 'lucide-react';
import { getCurrentUser, login } from '../api/auth';
import type { AuthUser } from '../api/types';

interface PinScreenProps {
  onAuthenticated: (user: AuthUser) => void | Promise<void>;
}

export function PinScreen({ onAuthenticated }: PinScreenProps) {
  const [username, setUsername] = useState('admin');
  const [password, setPassword] = useState('9999');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setLoading(true);
    setError('');
    try {
      await login(username, password);
      const user = await getCurrentUser();
      await onAuthenticated(user);
    } catch {
      setError('Autentificare esuata. Verifica utilizatorul si parola/PIN-ul.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center px-4 py-8">
      <motion.form
        initial={{ opacity: 0, y: 24 }}
        animate={{ opacity: 1, y: 0 }}
        onSubmit={handleSubmit}
        className="glass w-full max-w-md rounded-[2rem] p-8 shadow-2xl"
      >
        <div className="mx-auto mb-5 flex h-16 w-16 items-center justify-center rounded-2xl bg-indigo-500 text-white shadow-lg">
          <LockKeyhole size={26} />
        </div>
        <h1 className="text-center text-2xl font-bold">UniHub</h1>
        <p className="mb-8 text-center text-sm text-slate-500 dark:text-slate-400">
          Login pe backend real prin JWT
        </p>

        <label className="mb-3 block">
          <span className="mb-1 block text-[11px] font-bold uppercase tracking-wide text-slate-500">
            Username
          </span>
          <div className="flex items-center gap-2 rounded-2xl border border-slate-200 bg-white/70 px-3 py-3 dark:border-slate-700 dark:bg-slate-800/60">
            <User size={16} className="text-slate-400" />
            <input
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              className="w-full bg-transparent text-sm outline-none"
            />
          </div>
        </label>

        <label className="mb-3 block">
          <span className="mb-1 block text-[11px] font-bold uppercase tracking-wide text-slate-500">
            PIN / Parola
          </span>
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            className="w-full rounded-2xl border border-slate-200 bg-white/70 px-3 py-3 text-sm outline-none dark:border-slate-700 dark:bg-slate-800/60"
          />
        </label>

        {error && (
          <div className="mb-4 flex items-center gap-2 rounded-2xl bg-rose-50 px-3 py-2 text-xs font-medium text-rose-700 dark:bg-rose-950/40 dark:text-rose-300">
            <AlertCircle size={14} />
            {error}
          </div>
        )}

        <button
          type="submit"
          disabled={loading}
          className="w-full rounded-2xl bg-indigo-600 px-4 py-3 text-sm font-bold text-white shadow-lg shadow-indigo-500/30 transition hover:bg-indigo-700 disabled:opacity-60"
        >
          {loading ? 'Se autentifica...' : 'Intra in aplicatie'}
        </button>

        <p className="mt-4 text-center text-[11px] text-slate-500">
          Pentru local, contul default este disponibil dupa bootstrap sau reset explicit.
        </p>
      </motion.form>
    </div>
  );
}
