import {
  ErpReconciliationPanel,
  ImportHistoryPanel,
  PromoActualsPanel,
  SalesUploadPanel,
} from "./imports/ImportPanels";
import type { ImportsModel } from "./types";

export function ImportsView({ model }: { model: ImportsModel }) {
  return (
    <div className="grid min-w-0 grid-cols-1 gap-3 xl:grid-cols-2">
      <SalesUploadPanel model={model} />
      <ErpReconciliationPanel model={model} />
      <PromoActualsPanel model={model} />
      <ImportHistoryPanel model={model} />
    </div>
  );
}
