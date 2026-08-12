import { ExportWorkflow } from "./exports/controls";
import {
  ExportColumnsPanel,
  ExportFiltersPanel,
  ExportNavigation,
  ExportPreviewPanel,
  ExportSetupPanel,
} from "./exports/ExportPanels";
import type { ExportsModel } from "./types";

export function ExportsView({ model }: { model: ExportsModel }) {
  return (
    <div className="space-y-3">
      <ExportWorkflow step={model.exportStep} onChange={model.setExportStep} />
      <ExportSetupPanel model={model} />
      <div className="relative z-0 grid gap-3 lg:grid-cols-2">
        <ExportFiltersPanel model={model} />
        <ExportColumnsPanel model={model} />
      </div>
      <ExportPreviewPanel model={model} />
      <ExportNavigation model={model} />
    </div>
  );
}
