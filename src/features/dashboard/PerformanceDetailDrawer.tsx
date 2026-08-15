import type { PerformanceDetailLevel, PerformanceDetailResponse } from '../../api/generated/runtime-types';
import { LoadingCard } from '../../components/common/DataDisplay';
import { SideDrawer } from '../../components/common/SideDrawer';
import { PerformanceDetailContent } from './PerformanceDetailSections';
import { usePerformanceDetailModel } from './usePerformanceDetailModel';

export type PerformanceSelection = {
  level: PerformanceDetailLevel;
  key: string;
  site_code?: string;
};

interface PerformanceDetailDrawerProps {
  open: boolean;
  selection: PerformanceSelection | null;
  detail: PerformanceDetailResponse | null;
  loading: boolean;
  error: string;
  canViewSalaries: boolean;
  onClose: () => void;
}

export function PerformanceDetailDrawer(props: PerformanceDetailDrawerProps) {
  const model = usePerformanceDetailModel(props);
  return <SideDrawer
    open={props.open}
    onClose={props.onClose}
    title={props.detail ? `Performanta · ${props.detail.title}` : 'Performanta'}
    widthClassName="w-full max-w-5xl"
  >
    <div className="space-y-4 p-4">
      {props.loading && <LoadingCard label="Incarc detaliile de performanta..." />}
      {props.error && <div className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-xs font-semibold text-rose-700 dark:border-rose-900 dark:bg-rose-950/30 dark:text-rose-300">{props.error}</div>}
      {props.detail && <PerformanceDetailContent detail={props.detail} model={model} canViewSalaries={props.canViewSalaries} />}
    </div>
  </SideDrawer>;
}
