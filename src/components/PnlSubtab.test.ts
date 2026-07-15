import { describe, expect, it } from "vitest";

import { defaultPnlRange, monthLabel, pnlStoreOptionValue } from "./PnlSubtab";

describe("defaultPnlRange", () => {
  it("selects the available year-to-date months from the current year", () => {
    expect(
      defaultPnlRange(
        ["2025-12", "2026-03", "2026-01", "2026-07"],
        new Date("2026-07-13T10:00:00Z"),
      ),
    ).toEqual({ start: "2026-01", end: "2026-07" });
  });

  it("falls back to the latest available year when the current year is absent", () => {
    expect(
      defaultPnlRange(
        ["2024-12", "2025-04", "2025-01"],
        new Date("2026-07-13T10:00:00Z"),
      ),
    ).toEqual({ start: "2025-01", end: "2025-04" });
  });

  it("returns an empty range when no months exist", () => {
    expect(defaultPnlRange([], new Date("2026-07-13T10:00:00Z"))).toEqual({
      start: "",
      end: "",
    });
  });
});

describe("monthLabel", () => {
  it("keeps the initial empty range render-safe", () => {
    expect(monthLabel("")).toBe("—");
    expect(monthLabel("invalid")).toBe("—");
  });

  it("formats valid months", () => {
    expect(monthLabel("2026-07")).not.toBe("—");
  });
});

describe("pnlStoreOptionValue", () => {
  it("keeps identical unmapped source codes distinct by company", () => {
    const base = { site_code: "LEGACY", location: "Legacy", regional: "Nealocat" };
    expect(
      pnlStoreOptionValue({
        ...base,
        company_name: "Mobicell",
        scope_company: "Mobicell",
      }),
    ).not.toBe(
      pnlStoreOptionValue({
        ...base,
        company_name: "Mobiup",
        scope_company: "Mobiup",
      }),
    );
  });

  it("uses a company-neutral value for canonical stores", () => {
    expect(
      pnlStoreOptionValue({
        company_name: "Mobicell",
        site_code: "CRFORADEA",
        location: "Carrefour Oradea",
        regional: "Vest",
        scope_company: null,
      }),
    ).toBe('[null,"CRFORADEA"]');
  });
});
