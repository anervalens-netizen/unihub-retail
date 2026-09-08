import { lazy, Suspense, useState } from 'react';
const NativeCalendar = lazy(() => import('./grile/NativeCalendar').then(m => ({ default: m.NativeCalendar })));

import { CurrentGrileSubtab } from './grile/CurrentGrileSubtab';

export function GrileSubtab({ initialMonth }: { initialMonth?: string }) {
  const [native, setNative] = useState(false);
  return <div className="mx-auto max-w-6xl space-y-4 p-3 pb-24 pt-2 lg:max-w-none lg:p-0">
    <nav aria-label="Versiune grile" className="flex gap-2"><button aria-pressed={!native} onClick={() => setNative(false)} className="rounded border px-4 py-2">Grile V1</button><button aria-pressed={native} onClick={() => setNative(true)} className="rounded border px-4 py-2">Program V2</button></nav>
    {native ? <Suspense fallback={<p>Se încarcă programul…</p>}><NativeCalendar initialMonth={initialMonth} /></Suspense> : <CurrentGrileSubtab initialMonth={initialMonth} />}
  </div>;
}
