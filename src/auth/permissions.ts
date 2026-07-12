const SALARY_ACCESS_GROUPS = new Set([
  'authentik admins',
  'unihub-admin',
  'unihub-hr',
  'unihub-manager',
]);
const ADMIN_ACCESS_GROUPS = new Set(['authentik admins', 'unihub-admin']);
const MANAGEMENT_ACCESS_GROUPS = new Set([
  'authentik admins',
  'unihub-admin',
  'unihub-hr',
  'unihub-manager',
]);
const BUSINESS_WRITE_GROUPS = new Set([
  'authentik admins',
  'unihub-admin',
  'unihub-manager',
]);

function stringGroups(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value.filter((group): group is string => typeof group === 'string');
  }
  if (typeof value === 'string') return [value];
  return [];
}

export function oidcGroups(
  profile: unknown,
): string[] {
  if (profile && typeof profile === 'object') {
    const groups = stringGroups((profile as Record<string, unknown>).groups);
    if (groups.length > 0) return groups;
  }

  return [];
}

export function canAccessSalaries(
  profile: unknown,
): boolean {
  return oidcGroups(profile).some((group) =>
    SALARY_ACCESS_GROUPS.has(group.trim().toLocaleLowerCase('en-US')),
  );
}

export function canAdministerImports(
  profile: unknown,
): boolean {
  return oidcGroups(profile).some((group) =>
    ADMIN_ACCESS_GROUPS.has(group.trim().toLocaleLowerCase('en-US')),
  );
}

export function canAccessManagement(
  profile: unknown,
): boolean {
  return oidcGroups(profile).some((group) =>
    MANAGEMENT_ACCESS_GROUPS.has(group.trim().toLocaleLowerCase('en-US')),
  );
}

export function canWriteBusinessData(
  profile: unknown,
): boolean {
  return oidcGroups(profile).some((group) =>
    BUSINESS_WRITE_GROUPS.has(group.trim().toLocaleLowerCase('en-US')),
  );
}

export const canExportReports = canAccessManagement;
