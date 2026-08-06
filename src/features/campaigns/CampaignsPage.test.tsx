// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  getActiveContests: vi.fn(),
  getCampaignSnapshot: vi.fn(),
  getFocusHistory: vi.fn(),
  getPremiumGlassAnalysis: vi.fn(),
  getPromotionsIncentives: vi.fn(),
}));

vi.mock("../../api/campaigns", () => ({
  getCampaignSnapshot: api.getCampaignSnapshot,
  getFocusHistory: api.getFocusHistory,
  getPromotionsIncentives: api.getPromotionsIncentives,
}));

vi.mock("../../api/contests", () => ({
  getActiveContests: api.getActiveContests,
}));

vi.mock("../../api/dashboard", () => ({
  getPremiumGlassAnalysis: api.getPremiumGlassAnalysis,
}));

vi.mock("../../components/IncentiveDesktopDashboard", () => ({
  IncentiveDesktopHeader: () => <div data-testid="campaign-header" />,
}));

vi.mock("./PromoSection", () => ({
  PromoSection: () => <div data-testid="promo-section" />,
}));

vi.mock("./IncentiveSection", () => ({
  IncentiveSection: () => <div data-testid="incentive-section" />,
}));

import { defaultAppFilters } from "../../lib/filterValues";
import { CampaignsPage } from "./CampaignsPage";

function wrapper(children: React.ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe("Campaigns request states", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getPromotionsIncentives.mockRejectedValue(new Error("offline"));
  });

  it("uses a same-month range and exposes a working retry", async () => {
    render(
      wrapper(
        <CampaignsPage
          currentMonth="2026-08"
          months={["2026-08", "2026-07"]}
          filters={defaultAppFilters()}
          preferredSection="promo"
          onSectionChange={vi.fn()}
        />,
      ),
    );

    expect(
      await screen.findByText(
        "Datele pentru campanii si focus nu au putut fi incarcate.",
      ),
    ).toBeInTheDocument();
    expect(api.getPromotionsIncentives).toHaveBeenCalledWith(
      expect.objectContaining({
        start_date: "2026-08-01",
        end_date: "2026-08-31",
        view: "promo",
      }),
      expect.any(AbortSignal),
    );

    fireEvent.click(screen.getByRole("button", { name: "Reincearca" }));
    await waitFor(() =>
      expect(api.getPromotionsIncentives).toHaveBeenCalledTimes(2),
    );
  });

  it("refetches the canonical projection when the campaign tab changes", async () => {
    api.getPromotionsIncentives.mockResolvedValue({
      promotions: [],
      selected_promotion_key: "",
    });
    render(
      wrapper(
        <CampaignsPage
          currentMonth="2026-08"
          months={["2026-08"]}
          filters={defaultAppFilters()}
          preferredSection="promo"
          onSectionChange={vi.fn()}
        />,
      ),
    );

    expect(await screen.findByTestId("promo-section")).toBeInTheDocument();
    expect(api.getPromotionsIncentives).toHaveBeenLastCalledWith(
      expect.objectContaining({
        start_date: "2026-08-01",
        end_date: "2026-08-31",
        view: "promo",
      }),
      expect.any(AbortSignal),
    );

    fireEvent.click(screen.getByRole("tab", { name: "Incentive" }));
    expect(await screen.findByTestId("incentive-section")).toBeInTheDocument();
    expect(api.getPromotionsIncentives).toHaveBeenLastCalledWith(
      expect.objectContaining({
        start_date: "2026-08-01",
        end_date: "2026-08-31",
        view: "incentive",
      }),
      expect.any(AbortSignal),
    );
  });
});
