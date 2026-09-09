import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { saveCompensation, type readEarnings } from '../../api/grileCalendar';
type Compensation = NonNullable<Awaited<ReturnType<typeof readEarnings>>['agents'][number]['compensation']>;
import { getApiErrorMessage } from '../../api/client';

const fields = [
  ['vouchers', 'Tichete de masă (lei)'], ['sim_quantity', 'SIM · cantitate'],
  ['epay_under_50', 'E-pay sub 50 lei · cantitate'], ['epay_over_50', 'E-pay ≥ 50 lei · cantitate'],
  ['incentive', 'Incentive confirmat (lei)'], ['adjustment', 'Corecție (+/− lei)'],
] as const;
export function CompensationEditor({ value, writable }: { value: Compensation; writable: boolean }) {
  const [values, setValues] = useState<Record<string, string>>(Object.fromEntries(fields.map(([key]) => [key, value[key] == null ? '' : String(value[key])])));
  const cache = useQueryClient();
  const save = useMutation({ mutationFn: () => saveCompensation(value.month, value.agent_code, {
    salary_base: value.salary_base, vouchers: values.vouchers === '' ? null : Number(values.vouchers),
    sim_quantity: values.sim_quantity === '' ? null : Number(values.sim_quantity),
    epay_under_50: values.epay_under_50 === '' ? null : Number(values.epay_under_50),
    epay_over_50: values.epay_over_50 === '' ? null : Number(values.epay_over_50),
    incentive: values.incentive === '' ? null : Number(values.incentive), adjustment: values.adjustment === '' ? null : Number(values.adjustment), expected_revision: value.revision,
  }), onSuccess: async () => { await cache.invalidateQueries({ queryKey: ['native-earnings', value.month] }); } });
  if (!writable) return null;
  return <details className="mt-4 rounded-xl border border-slate-200 p-3 dark:border-slate-700"><summary className="cursor-pointer text-sm font-semibold">Completări de manager</summary><form className="mt-3 space-y-3" onSubmit={event => { event.preventDefault(); save.mutate(); }}>
    <p className="text-xs text-slate-500">Salariu de bază: București, Constanța și Cluj — 2.600 lei; restul orașelor — 2.400 lei. Se aplică magazinului de bază. SIM: 3 lei; E-pay: 5 / 12 lei pe bucată. Introdu explicit 0 pentru componentele fără valoare.</p>
    <div className="grid gap-3 sm:grid-cols-2">{fields.map(([key, label]) => <label className="native-label" key={key}>{label}<input type="number" min={key === 'adjustment' ? -1000000 : 0} max={key.includes('quantity') || key.includes('epay') ? 100000 : 1000000} step={key.includes('quantity') || key.includes('epay') ? 1 : '0.01'} className="native-field" value={values[key]} placeholder="De completat" disabled={save.isPending} onChange={event => setValues(old => ({ ...old, [key]: event.target.value }))} /></label>)}</div>
    <button type="button" className="native-secondary" onClick={() => setValues(old => Object.fromEntries(Object.entries(old).map(([key, v]) => [key, v || '0'])))}>Confirmă câmpurile goale ca zero</button>
    <button className="native-primary ml-2" disabled={save.isPending || save.isSuccess}>Salvează completările</button>
    {save.isError && <p role="alert">{getApiErrorMessage(save.error, 'Salvarea a eșuat. Reîncarcă grila înainte de a reîncerca.')} <button type="button" onClick={() => void cache.invalidateQueries({ queryKey: ['native-earnings', value.month] })}>Reîncarcă</button></p>}
  </form></details>;
}
