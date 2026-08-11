// @vitest-environment jsdom

import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const dashboardMock = vi.hoisted(() => ({
  current: {} as Record<string, unknown>,
  refetchCurrent: vi.fn(),
  refetchHistory: vi.fn(),
}));

vi.mock("../../auth/AuthContext", () => ({
  useAuth: () => ({ user: { profile: { sub: "test", groups: [] } } }),
}));

vi.mock("./useDashboardData", () => ({
  useDashboardData: () => dashboardMock.current,
}));

vi.mock("./CurrentDashboard", () => ({
  CurrentDashboard: ({ agents, stores }: { agents: unknown[]; stores: unknown[] }) => (
    <div data-testid="current-dashboard">
      curent: {agents.length} agenți, {stores.length} magazine
    </div>
  ),
}));

vi.mock("./HistoryDashboard", () => ({
  HistoryDashboard: ({ error, loading }: { error: string | null; loading: boolean }) => (
    <div data-testid="history-dashboard">
      {loading ? "istoric în încărcare" : error || "istoric disponibil"}
    </div>
  ),
}));

import { Dashboard } from "./DashboardPage";

const baseData = () => ({
  summary: { is_month_final: false, days_in_month: 31 },
  agents: [],
  stores: [],
  dailySales: [],
  dailyLastYear: [],
  periodComparison: null,
  categoryMix: [],
  receiptBucketMix: [],
  focusSubcategoryMix: [],
  brandMix: [],
  regionals: [],
  currentHistory: [],
  currentHistoryLoading: false,
  yearHistory: [],
  yearHistoryLoading: false,
  history: [],
  historySummary: null,
  historyReceiptBucketMix: [],
  historyFocusSubcategoryMix: [],
  historyDailySales: [],
  historyCategoryMix: [],
  historyBrandMix: [],
  historyRegionals: [],
  historyStores: [],
  historyAgents: [],
  loading: false,
  error: null,
  historyLoading: false,
  historyError: null,
  refetchCurrentData: dashboardMock.refetchCurrent,
  refetchHistoryData: dashboardMock.refetchHistory,
});

const props = {
  currentMonth: "2026-08",
  months: ["2026-08", "2026-07"],
  filters: { firma: "all", rm: "all", magazin: [], agent: [] },
};

describe("Dashboard owner states", () => {
  beforeEach(() => {
    dashboardMock.current = baseData();
    dashboardMock.refetchCurrent.mockReset();
    dashboardMock.refetchHistory.mockReset();
  });

  it("renders the request-wide loading state", () => {
    dashboardMock.current = { ...baseData(), loading: true, summary: null };
    render(<Dashboard {...props} />);
    expect(screen.getByText("Se incarca luna in curs...")).toBeInTheDocument();
  });

  it("renders a recoverable error and invokes retry", () => {
    dashboardMock.current = {
      ...baseData(),
      error: "Dashboard indisponibil",
      summary: null,
    };
    render(<Dashboard {...props} />);
    expect(screen.getByText("Dashboard indisponibil")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Reincearca" }));
    expect(dashboardMock.refetchCurrent).toHaveBeenCalledOnce();
  });

  it("keeps an empty partial payload usable and switches to history", () => {
    const onSectionChange = vi.fn();
    render(<Dashboard {...props} onSectionChange={onSectionChange} />);

    expect(screen.getByTestId("current-dashboard")).toHaveTextContent(
      "curent: 0 agenți, 0 magazine",
    );
    fireEvent.click(screen.getByRole("tab", { name: "Istoric" }));
    expect(screen.getByTestId("history-dashboard")).toHaveTextContent(
      "istoric disponibil",
    );
    expect(onSectionChange).toHaveBeenLastCalledWith("history");
  });
});
