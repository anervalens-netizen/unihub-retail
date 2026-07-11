import { describe, expect, it } from 'vitest';

import { hasPnlCapability, shouldResetPnlSubtab } from './pnlAccess';

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
});
