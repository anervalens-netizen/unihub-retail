export function hasPnlCapability(
  hasManagementAccess: boolean,
  canView: boolean | undefined,
): boolean {
  return hasManagementAccess && canView === true;
}

export function pnlPermissionIsPending(
  isAuthLoading: boolean,
  isCapabilityPending: boolean,
): boolean {
  return isAuthLoading || isCapabilityPending;
}

export function shouldResetPnlSubtab(
  isPermissionPending: boolean,
  hasPnlAccess: boolean,
  activeSubtab: string,
): boolean {
  return !isPermissionPending && !hasPnlAccess && activeSubtab === 'pnl';
}
