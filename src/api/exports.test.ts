import { describe, expect, it } from "vitest";

import { ApiError } from "./client";
import { GeneratedApiError } from "./generated/client";
import { uncertainExportOperationId } from "./exports";

const operationId = "create_export_operation_api_exports_operations_post" as const;

describe("uncertainExportOperationId", () => {
  it("reads only the generated 503 body for the create operation", () => {
    const error = new GeneratedApiError(
      operationId,
      new ApiError(503, "temporar indisponibil", {
        detail: { operation_id: 42, status: "queued" },
      }),
    );

    expect(uncertainExportOperationId(error)).toBe(42);
  });

  it("rejects a different status or malformed generated detail", () => {
    expect(
      uncertainExportOperationId(
        new GeneratedApiError(
          operationId,
          new ApiError(409, "conflict", { detail: { operation_id: 42 } }),
        ),
      ),
    ).toBeNull();
    expect(
      uncertainExportOperationId(
        new GeneratedApiError(
          operationId,
          new ApiError(503, "temporar indisponibil", { detail: "retry" }),
        ),
      ),
    ).toBeNull();
  });
});
