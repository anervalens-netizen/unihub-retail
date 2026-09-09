import { lazy, Suspense, useState } from 'react';
const NativeCalendar = lazy(() => import('./grile/NativeCalendar').then(m => ({ default: m.NativeCalendar })));

import { SegmentedTabs } from './common/SegmentedTabs';
import { CurrentGrileSubtab } from './grile/CurrentGrileSubtab';

export function GrileSubtab({ initialMonth }: { initialMonth?: string }) {
  const [native, setNative] = useState(false);
  return <div className="mx-auto max-w-6xl space-y-4 p-3 pb-24 pt-2 lg:max-w-none lg:p-0">
    <SegmentedTabs ariaLabel="Versiune grile" options={[{ value: 'v1', label: 'Grile V1' }, { value: 'v2', label: 'Program V2' }]} value={native ? 'v2' : 'v1'} onChange={value => setNative(value === 'v2')} />
    {native ? <Suspense fallback={<p>Se încarcă programul…</p>}><NativeCalendar initialMonth={initialMonth} /></Suspense> : <CurrentGrileSubtab initialMonth={initialMonth} />}
  </div>;
}
