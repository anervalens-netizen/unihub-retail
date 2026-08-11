import { describe, expect, it } from "vitest";

import { ApiError } from "./client";
import { GeneratedApiError } from "./generated/client";
import { isExportOperationNotFound, uncertainExportOperationId } from "./exports";

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

describe("isExportOperationNotFound", () => {
  const getOperationId =
    "get_export_operation_api_exports_operations__operation_id__get" as const;

  it("recognizes only the owner-bound operation 404", () => {
    expect(
      isExportOperationNotFound(
        new GeneratedApiError(
          getOperationId,
          new ApiError(404, "not found", { detail: "not found" }),
        ),
      ),
    ).toBe(true);
    expect(
      isExportOperationNotFound(
        new GeneratedApiError(
          getOperationId,
          new ApiError(503, "unavailable", { detail: "unavailable" }),
        ),
      ),
    ).toBe(false);
  });
});
