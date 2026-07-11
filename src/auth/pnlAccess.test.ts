import { describe, expect, it } from 'vitest';

import { hasPnlCapability, pnlPermissionIsPending, shouldResetPnlSubtab } from './pnlAccess';

describe('P&L capability state', () => {
  it('shows P&L only for management plus backend capability', () => {
    expect(hasPnlCapability(true, true)).toBe(true);
    expect(hasPnlCapability(true, false)).toBe(false);
    expect(hasPnlCapability(false, true)).toBe(false);
  });

  it('keeps a saved P&L subtab while permissions are pending', () => {
    expect(shouldResetPnlSubtab(true, false, 'pnl')).toBe(false);
    expect(shouldResetPnlSubtab(false, false, 'pnl')).toBe(true);
    expect(shouldResetPnlSubtab(false, true, 'pnl')).toBe(false);
    expect(shouldResetPnlSubtab(false, false, 'asm')).toBe(false);
  });

  it('includes authentication bootstrap in effective permission pending', () => {
    expect(pnlPermissionIsPending(true, false)).toBe(true);
    expect(shouldResetPnlSubtab(pnlPermissionIsPending(true, false), false, 'pnl')).toBe(false);
    expect(pnlPermissionIsPending(false, true)).toBe(true);
    expect(shouldResetPnlSubtab(pnlPermissionIsPending(false, true), false, 'pnl')).toBe(false);
    expect(pnlPermissionIsPending(false, false)).toBe(false);
    expect(shouldResetPnlSubtab(pnlPermissionIsPending(false, false), false, 'pnl')).toBe(true);
    expect(shouldResetPnlSubtab(pnlPermissionIsPending(false, false), true, 'pnl')).toBe(false);
    expect(shouldResetPnlSubtab(pnlPermissionIsPending(false, false), false, 'asm')).toBe(false);
  });
});
