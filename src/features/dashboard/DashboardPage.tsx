import { DashboardSurface } from './DashboardSurface';
import type { DashboardProps } from './dashboardTypes';
import { useDashboardController, type DashboardContextProps } from './useDashboardController';

export type { DashboardProps, DashboardSection, DashboardViewProps } from './dashboardTypes';

export function Dashboard(props: DashboardProps & DashboardContextProps) {
  return <DashboardSurface {...useDashboardController(props)} />;
}
