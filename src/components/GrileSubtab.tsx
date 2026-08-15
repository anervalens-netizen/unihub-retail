import { useState } from 'react';

import { CurrentGrileSubtab } from './grile/CurrentGrileSubtab';
import { PilotV2Panel } from './grile/PilotV2Panel';
import { SegmentedTabs } from './common/SegmentedTabs';

export function GrileSubtab({ initialMonth }: { initialMonth?: string }) {
  const [view, setView] = useState<'current' | 'pilot-v2'>('current');
  return <div className="mx-auto max-w-6xl space-y-4 p-3 pb-24 pt-2 lg:max-w-none lg:p-0">
    <SegmentedTabs
      ariaLabel="Versiune grilă"
      value={view}
      onChange={setView}
      options={[
        { value: 'current', label: 'Grila actuală' },
        { value: 'pilot-v2', label: 'V2 · pilot' },
      ]}
    />
    <div hidden={view !== 'current'}><CurrentGrileSubtab initialMonth={initialMonth} /></div>
    <div hidden={view !== 'pilot-v2'}><PilotV2Panel enabled={view === 'pilot-v2'} /></div>
  </div>;
}
