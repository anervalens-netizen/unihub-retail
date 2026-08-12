import type { TargetScenarioViewProps } from './TargetScenarioView';
import {
  TargetAllocationHeader,
  TargetDesktopTable,
  TargetLocationFilter,
  TargetMobileRows,
} from './TargetStoreAllocationViews';

export function TargetStoreAllocation({ model }: { model: TargetScenarioViewProps }) {
  if (!model.scenario) return null;
  return <div className="glass overflow-hidden rounded-2xl">
    <TargetAllocationHeader model={model} />
    <TargetLocationFilter model={model} />
    <TargetMobileRows model={model} />
    <TargetDesktopTable model={model} />
  </div>;
}
