import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { saveEpay, type readEarnings } from '../../api/grileCalendar';
import { getApiErrorMessage } from '../../api/client';
type Compensation = NonNullable<Awaited<ReturnType<typeof readEarnings>>['agents'][number]['compensation']>;
const fields = [['epay_under_50', 'E-pay <50 lei'], ['epay_over_50', 'E-pay ≥50 lei']] as const;
export function CompensationEditor({ value, writable }: { value: Compensation; writable: boolean }) {
  const [values, setValues] = useState({ epay_under_50: String(value.epay_under_50 ?? 0), epay_over_50: String(value.epay_over_50 ?? 0) });
  const cache = useQueryClient();
  const valid = fields.every(([key]) => /^\d+$/.test(values[key]) && Number(values[key]) <= 15);
  const dirty = fields.some(([key]) => Number(values[key]) !== Number(value[key] ?? 0));
  const save = useMutation({ mutationFn: () => saveEpay(value.month, value.agent_code, {
    epay_under_50: Number(values.epay_under_50), epay_over_50: Number(values.epay_over_50),
    expected_revision: value.revision,
  }), onSuccess: async () => { await cache.invalidateQueries({ queryKey: ['native-earnings', value.month] }); } });
  return <form className="grile-epay grid grid-cols-2 gap-2 py-2" aria-label={`E-pay ${value.agent_code}`} onSubmit={e => { e.preventDefault(); if (valid && dirty) save.mutate(); }}>
    {fields.map(([key, label]) => <label className="native-label" key={key}>{label} · buc.
      <select aria-label={`${label} cantitate`} className="native-field" value={values[key]} disabled={!writable || save.isPending} onChange={e => setValues(v => ({ ...v, [key]: e.target.value }))}>
        {Array.from({ length: 16 }, (_, n) => <option key={n} value={n}>{n}</option>)}
      </select>
    </label>)}
    {writable && dirty && <button className="native-primary col-span-2" disabled={!valid || save.isPending}>{save.isPending ? 'Se salvează…' : 'Salvează E-pay'}</button>}
    {save.isError && <p role="alert" className="col-span-2 text-xs text-rose-700">{getApiErrorMessage(save.error, 'Salvarea a eșuat. Reîncarcă grila.')} <button type="button" onClick={() => void cache.invalidateQueries({ queryKey: ['native-earnings', value.month] })}>Reîncarcă</button></p>}
  </form>;
}
