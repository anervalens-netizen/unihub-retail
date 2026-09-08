import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { getApiErrorMessage } from '../../api/client';
import { saveStoreHours, type CalendarData } from '../../api/grileCalendar';

export function StoreHoursEditor({ month, site, data, disabled, writable, onPendingChange }: {
  month: string; site: string; data: CalendarData; disabled: boolean; writable: boolean; onPendingChange: (value: boolean) => void;
}) {
  const current = data.store_hours?.find(row => row.site_code === site);
  const [opens, setOpens] = useState(current?.opens ?? '10:00');
  const [closes, setCloses] = useState(current?.closes ?? '22:00');
  const [pause, setPause] = useState(current?.break_minutes ?? 60);
  const cache = useQueryClient();
  const save = useMutation({
    mutationFn: () => saveStoreHours(month, site, { opens, closes, break_minutes: pause, expected_revision: current?.revision ?? 0 }),
    onMutate: () => onPendingChange(true),
    onSuccess: () => cache.invalidateQueries({ queryKey: ['native-calendar', month] }),
    onSettled: () => onPendingChange(false),
  });
  return <details className="mb-4 rounded border p-3"><summary>Program magazin · {current?.opens ?? '10:00'}–{current?.closes ?? '22:00'} · pauză {current?.break_minutes ?? 60} min</summary>
    <p className="my-2 text-sm">Se aplică tuturor zilelor lucrate din {month}, inclusiv suplimentarilor. Celelalte luni nu se modifică.</p>
    {writable && <form onSubmit={e => { e.preventDefault(); save.mutate(); }} className="flex flex-wrap items-end gap-3">
      <label>Deschidere <input aria-label="Deschidere" type="time" required value={opens} disabled={disabled || save.isPending || save.isError} onChange={e => setOpens(e.target.value)} /></label>
      <label>Închidere <input aria-label="Închidere" type="time" required value={closes} disabled={disabled || save.isPending || save.isError} onChange={e => setCloses(e.target.value)} /></label>
      <label>Pauză (minute) <input aria-label="Pauză (minute)" type="number" required min={0} max={720} value={pause} disabled={disabled || save.isPending || save.isError} onChange={e => setPause(Number(e.target.value))} className="w-20" /></label>
      <button className="rounded border px-3 py-2" disabled={disabled || save.isPending || save.isError}>Salvează programul magazinului</button>
    </form>}
    {save.isError && <p role="alert">{getApiErrorMessage(save.error, 'Programul nu a fost salvat.')} <button onClick={async () => { await cache.invalidateQueries({ queryKey: ['native-calendar', month] }); save.reset(); }}>Reîncarcă orarul</button></p>}
  </details>;
}
