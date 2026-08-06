import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  GeneratedApiError,
  generatedGet,
  generatedPatch,
  generatedPost,
  isGeneratedApiError,
} from "./client";

const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

describe("generated Retail client", () => {
  it("keeps request contracts type-checked", () => {
    if (import.meta.env.MODE === "typecheck-only") {
      // @ts-expect-error required query parameters cannot be omitted
      generatedGet("get_summary_api_dashboard_summary_get", {});
      generatedGet(
        "get_scenario_api_target_calculator_scenarios__scenario_id__get",
        {
          pathParams: {
            // @ts-expect-error path parameters use the generated numeric schema
            scenario_id: "42",
          },
        },
      );
      generatedPatch(
        "update_final_targets_api_target_calculator_scenarios__scenario_id__rows_patch",
        {
          expected_revision: 4,
          rows: [],
        },
        { pathParams: { scenario_id: 42 } },
      );
    }
    expect(true).toBe(true);
  });

  it("resolves path parameters and decodes nullable Decimal fields", async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          total_sales: "123.45",
          forecast_sales: null,
        }),
        { status: 200 },
      ),
    );

    const result = await generatedGet("get_summary_api_dashboard_summary_get", {
      params: { month: "2026-08" },
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/dashboard/summary?month=2026-08",
      expect.objectContaining({ method: "GET", credentials: "same-origin" }),
    );
    expect(result).toEqual({ total_sales: 123.45, forecast_sales: null });
  });

  it("keeps string option values when the schema also contains numeric value fields", async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          rows: [{ value: "42", label: "Mobiup" }],
        }),
        { status: 200 },
      ),
    );

    const result = await generatedGet(
      "get_filter_options_api_filters_options_get",
      {
        params: { month: "2026-08" },
      },
    );

    expect(result).toEqual({ rows: [{ value: "42", label: "Mobiup" }] });
  });

  it("rejects an invalid Decimal only at its generated response path", async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ total_sales: "not-a-decimal" }), {
        status: 200,
      }),
    );
    await expect(
      generatedGet("get_summary_api_dashboard_summary_get", {
        params: { month: "2026-08" },
      }),
    ).rejects.toThrow("Invalid Retail Decimal for total_sales");
  });

  it("rejects invalid generated date and date-time response paths", async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ last_sale_date: "2026-02-30" }), {
        status: 200,
      }),
    );
    await expect(
      generatedGet("get_summary_api_dashboard_summary_get", {
        params: { month: "2026-08" },
      }),
    ).rejects.toThrow("Invalid Retail date for last_sale_date");

    fetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify([
          {
            upload_date: "2026-08-05",
            created_at: "not-a-date-time",
            finished_at: null,
          },
        ]),
        { status: 200 },
      ),
    );
    await expect(
      generatedGet("get_import_history_api_import_history_get"),
    ).rejects.toThrow("Invalid Retail date-time for */created_at");
  });

  it("decodes nested Decimal fields from the operation path plan", async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          daily: [{ total_sales: "123.45" }],
          filter_value: { value: "42" },
        }),
        { status: 200 },
      ),
    );

    const result = await generatedGet(
      "get_dashboard_all_api_dashboard_all_get",
      {
        params: { month: "2026-08" },
      },
    );

    expect(result).toMatchObject({
      daily: [{ total_sales: 123.45 }],
      filter_value: { value: "42" },
    });
  });

  it("supports PATCH and Blob responses through the generated route map", async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ ok: true }), { status: 200 }),
    );
    await generatedPatch(
      "update_final_targets_api_target_calculator_scenarios__scenario_id__rows_patch",
      {
        expected_revision: 4,
        rows: [],
      },
      {
        pathParams: { scenario_id: 42 },
      },
    );
    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      "/api/target-calculator/scenarios/42/rows",
    );

    const blob = new Blob(["xlsx"], { type: "application/octet-stream" });
    fetchMock.mockResolvedValueOnce({
      status: 200,
      ok: true,
      headers: new Headers(),
      blob: vi.fn().mockResolvedValue(blob),
      text: vi.fn(),
    });
    const result = await generatedGet(
      "export_scenario_api_target_calculator_scenarios__scenario_id__export_get",
      {
        pathParams: { scenario_id: 42 },
      },
    );
    expect(result).toBe(blob);
  });

  it("forwards AbortSignal and uses the generated POST route", async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ results: [] }), { status: 200 }),
    );
    const controller = new AbortController();
    await generatedPost(
      "get_dashboard_all_batch_api_dashboard_all_batch_post",
      { queries: [] },
      {
        signal: controller.signal,
      },
    );
    expect(fetchMock.mock.calls[0]?.[1]).toEqual(
      expect.objectContaining({ signal: controller.signal }),
    );
  });

  it("wraps documented 409 and 422 responses with their operation identity", async () => {
    const targetOperation =
      "update_final_targets_api_target_calculator_scenarios__scenario_id__rows_patch" as const;
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: "Conflict de revizie" }), {
        status: 409,
      }),
    );
    const conflict = await generatedPatch(
      targetOperation,
      {
        expected_revision: 4,
        rows: [],
      },
      {
        pathParams: { scenario_id: 42 },
      },
    ).catch((error: unknown) => error);

    expect(conflict).toBeInstanceOf(GeneratedApiError);
    expect(isGeneratedApiError(conflict, targetOperation)).toBe(true);
    if (isGeneratedApiError(conflict, targetOperation)) {
      expect(conflict.expected).toBe(true);
      expect(conflict.typedBody).toEqual({ detail: "Conflict de revizie" });
    }

    const summaryOperation = "get_summary_api_dashboard_summary_get" as const;
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: [{ msg: "month invalid" }] }), {
        status: 422,
      }),
    );
    const validation = await generatedGet(summaryOperation, {
      params: { month: "bad" },
    }).catch((error: unknown) => error);

    expect(isGeneratedApiError(validation, summaryOperation)).toBe(true);
    if (isGeneratedApiError(validation, summaryOperation)) {
      expect(validation.expected).toBe(true);
      expect(validation.typedBody).toEqual({
        detail: [{ msg: "month invalid" }],
      });
    }
  });
});
