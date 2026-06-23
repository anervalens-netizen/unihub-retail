export async function loadCampaignsScreen() {
  const module = await import('./components/Campaigns');
  return { default: module.Campaigns };
}

export async function loadDashboardScreen() {
  const module = await import('./components/Dashboard');
  return { default: module.Dashboard };
}

export async function loadAgentsScreen() {
  const module = await import('./components/Agents');
  return { default: module.Agents };
}

export async function loadSettingsScreen() {
  const module = await import('./components/Settings');
  return { default: module.Settings };
}

export async function loadManagementScreen() {
  const module = await import('./components/Management');
  return { default: module.Management };
}
