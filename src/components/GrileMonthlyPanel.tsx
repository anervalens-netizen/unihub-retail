import { GrileMonthlyPanelView } from './grile/GrileMonthlyPanelView';
import { useGrileMonthlyPanel } from './grile/useGrileMonthlyPanel';

export function GrileMonthlyPanel({ month }: { month: string }) {
  return <GrileMonthlyPanelView month={month} model={useGrileMonthlyPanel(month)} />;
}
