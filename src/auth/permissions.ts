import { parseClaims } from '@unihub/auth-client';

const SALARY_ACCESS_GROUPS = new Set([
  'authentik admins',
  'unihub-admin',
  'unihub-hr',
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
  accessToken?: string,
): string[] {
  if (profile && typeof profile === 'object') {
    const groups = stringGroups((profile as Record<string, unknown>).groups);
    if (groups.length > 0) return groups;
  }

  if (accessToken) {
    try {
      return stringGroups(parseClaims(accessToken).groups);
    } catch {
      return [];
    }
  }

  return [];
}

export function canAccessSalaries(
  profile: unknown,
  accessToken?: string,
): boolean {
  return oidcGroups(profile, accessToken).some((group) =>
    SALARY_ACCESS_GROUPS.has(group.trim().toLocaleLowerCase('en-US')),
  );
}
