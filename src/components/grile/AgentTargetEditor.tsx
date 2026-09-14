import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { saveAgentTarget, type readEarnings } from '../../api/grileCalendar';
import { getApiErrorMessage } from '../../api/client';

type Agent = Awaited<ReturnType<typeof readEarnings>>['agents'][number];
const money = (value: string | number | null | undefined) => value == null ? 'Indisponibil' : `${Number(value).toLocaleString('ro-RO', { maximumFractionDigits: 0 })} lei`;

export function AgentTargetEditor({ agent, writable }: { agent: Agent; writable: boolean }) {
  const setting = agent.target_setting;
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState<'automatic' | 'manual'>(setting?.mode ?? 'automatic');
  const [amount, setAmount] = useState(String(setting?.manual_target ?? agent.home_target ?? ''));
  const cache = useQueryClient();
  const valid = mode === 'automatic' || (/^\d+(?:[.,]\d{1,2})?$/.test(amount) && Number(amount.replace(',', '.')) > 0 && Number(amount.replace(',', '.')) <= 1000000);
  const save = useMutation({
    mutationFn: () => saveAgentTarget(setting!.month, agent.agent_code, {
      mode, manual_target: mode === 'manual' ? Number(amount.replace(',', '.')) : null,
      expected_revision: setting!.revision,
    }),
    onSuccess: async () => {
      setOpen(false);
      // Hub, selected-agent details, evaluation and exports share the same source.
      await cache.invalidateQueries();
    },
  });
  const value = money(agent.performance?.target ?? agent.home_target);
  if (!setting || agent.home_site_code === 'TL' || !writable) return <span>{value}{setting?.mode === 'manual' && <small className="ml-1 font-normal">· manager</small>}</span>;
  return <div className="relative">
    <button type="button" aria-label={`Editează target ${agent.agent_code}`} aria-expanded={open} className="underline decoration-dotted underline-offset-4" onClick={() => setOpen(!open)}>{value} <span className="text-xs">▾</span></button>
    {setting.mode === 'manual' && <small className="ml-1 font-normal text-indigo-600">manager</small>}
    {open && <form aria-label={`Target agent ${agent.agent_code}`} className="absolute right-0 top-full z-30 mt-1 w-64 whitespace-normal rounded-lg border border-indigo-200 bg-white p-3 text-left text-sm font-normal shadow-lg dark:bg-slate-900" onSubmit={e => { e.preventDefault(); if (valid) save.mutate(); }}>
      <label className="native-label">Target agent
        <select aria-label="Mod calcul target" className="native-field" value={mode} disabled={save.isPending} onChange={e => setMode(e.target.value as typeof mode)}>
          <option value="automatic">Calcul automat</option><option value="manual">Introdus de manager</option>
        </select>
      </label>
      {mode === 'manual' && <label className="native-label mt-2">Target lunar · lei<input aria-label="Target lunar în lei" className="native-field" inputMode="decimal" value={amount} disabled={save.isPending} onChange={e => setAmount(e.target.value)} /></label>}
      <p className="my-2 text-xs text-slate-500">Calcul automat: {money(setting.automatic_target)}. Setarea se aplică lunii {setting.month}.</p>
      <div className="flex gap-2"><button className="native-primary" disabled={!valid || save.isPending}>{save.isPending ? 'Se salvează…' : 'Salvează'}</button><button type="button" disabled={save.isPending} onClick={() => setOpen(false)}>Închide</button></div>
      {save.isError && <p role="alert" className="mt-2 text-xs text-red-700">{getApiErrorMessage(save.error, 'Salvarea a eșuat.')} <button type="button" onClick={() => void cache.invalidateQueries({ queryKey: ['native-earnings', setting.month] })}>Reîncarcă</button></p>}
    </form>}
  </div>;
}
