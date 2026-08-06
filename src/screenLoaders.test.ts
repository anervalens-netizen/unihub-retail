import { describe, expect, it, vi } from "vitest";

const screens = vi.hoisted(() => ({
  Campaigns: () => null,
  Dashboard: () => null,
  Agents: () => null,
  Settings: () => null,
  Management: () => null,
}));

vi.mock("./features/campaigns/CampaignsPage", () => ({
  Campaigns: screens.Campaigns,
}));
vi.mock("./features/dashboard/DashboardPage", () => ({
  Dashboard: screens.Dashboard,
}));
vi.mock("./features/agents/AgentsPage", () => ({ Agents: screens.Agents }));
vi.mock("./features/settings/SettingsPage", () => ({
  Settings: screens.Settings,
}));
vi.mock("./components/Management", () => ({ Management: screens.Management }));

import {
  loadAgentsScreen,
  loadCampaignsScreen,
  loadDashboardScreen,
  loadManagementScreen,
  loadSettingsScreen,
} from "./screenLoaders";

describe("lazy screen loaders", () => {
  it.each([
    ["Campaigns", loadCampaignsScreen, screens.Campaigns],
    ["Dashboard", loadDashboardScreen, screens.Dashboard],
    ["Agents", loadAgentsScreen, screens.Agents],
    ["Settings", loadSettingsScreen, screens.Settings],
    ["Management", loadManagementScreen, screens.Management],
  ] as const)(
    "maps %s named export to React.lazy default",
    async (_name, loader, component) => {
      await expect(loader()).resolves.toEqual({ default: component });
    },
  );
});
