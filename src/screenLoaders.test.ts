import { describe, expect, it, vi } from 'vitest';

const screens = vi.hoisted(() => ({
  Campaigns: () => null,
  Dashboard: () => null,
  Agents: () => null,
  Settings: () => null,
  Management: () => null,
}));

vi.mock('./components/Campaigns', () => ({ Campaigns: screens.Campaigns }));
vi.mock('./components/Dashboard', () => ({ Dashboard: screens.Dashboard }));
vi.mock('./components/Agents', () => ({ Agents: screens.Agents }));
vi.mock('./components/Settings', () => ({ Settings: screens.Settings }));
vi.mock('./components/Management', () => ({ Management: screens.Management }));

import {
  loadAgentsScreen,
  loadCampaignsScreen,
  loadDashboardScreen,
  loadManagementScreen,
  loadSettingsScreen,
} from './screenLoaders';

describe('lazy screen loaders', () => {
  it.each([
    ['Campaigns', loadCampaignsScreen, screens.Campaigns],
    ['Dashboard', loadDashboardScreen, screens.Dashboard],
    ['Agents', loadAgentsScreen, screens.Agents],
    ['Settings', loadSettingsScreen, screens.Settings],
    ['Management', loadManagementScreen, screens.Management],
  ] as const)('maps %s named export to React.lazy default', async (_name, loader, component) => {
    await expect(loader()).resolves.toEqual({ default: component });
  });
});
