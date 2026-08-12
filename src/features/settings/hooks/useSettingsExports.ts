import type { ExportsModel } from "../types";
import { useExportOperation } from "./useExportOperation";
import { useExportRequest, useExportSelection } from "./useExportSelection";

const INCENTIVE_PRODUCTS_DATASET = "incentive_products";

export function useSettingsExports(
  enabled: boolean,
  identityKey = "anonymous",
  authorized = enabled,
): ExportsModel {
  const selection = useExportSelection(enabled, identityKey, authorized);
  const request = useExportRequest(selection);
  const operation = useExportOperation(
    enabled,
    authorized,
    identityKey,
    request,
    selection.setPreview,
  );
  return {
    ...selection,
    ...operation,
    isIncentiveProductsExport:
      selection.exportMode === "table" &&
      selection.exportDataset === INCENTIVE_PRODUCTS_DATASET,
  };
}
