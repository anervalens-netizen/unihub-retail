export async function loadCampaignsScreen() {
  const module = await import('./features/campaigns/CampaignsPage');
  return { default: module.Campaigns };
}

export async function loadDashboardScreen() {
  const module = await import('./features/dashboard/DashboardPage');
  return { default: module.Dashboard };
}

export async function loadAgentsScreen() {
  const module = await import('./features/agents/AgentsPage');
  return { default: module.Agents };
}

export async function loadSettingsScreen() {
  const module = await import('./features/settings/SettingsPage');
  return { default: module.Settings };
}

export async function loadManagementScreen() {
  const module = await import('./components/Management');
  return { default: module.Management };
}
