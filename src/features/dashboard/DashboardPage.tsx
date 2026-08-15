import { DashboardSurface } from './DashboardSurface';
import type { DashboardProps } from './dashboardTypes';
import { useDashboardController } from './useDashboardController';

export type { DashboardProps, DashboardSection, DashboardViewProps } from './dashboardTypes';

export function Dashboard(props: DashboardProps) {
  return <DashboardSurface {...useDashboardController(props)} />;
}
