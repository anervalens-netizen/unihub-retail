import { beforeEach, describe, expect, it, vi } from "vitest";

const count = vi.hoisted(() => vi.fn());

vi.mock("@sentry/react", () => ({ metrics: { count } }));

import { reportFrontendBootstrapFailure } from "./frontendMetrics";

describe("frontend bootstrap metric", () => {
  beforeEach(() => count.mockReset());

  it("emits only the finite reason and no user or business labels", () => {
    reportFrontendBootstrapFailure("unavailable");
    expect(count).toHaveBeenCalledWith("frontend_bootstrap_failure", 1, {
      attributes: { reason: "unavailable" },
    });
  });
});
