import { describe, expect, it } from 'vitest';
import {
  getAgentSortValue,
  getStoreDailyAverage,
  getStoreSortValue,
  getRegionalSortValue,
  getAsmSortValue,
  sumChartValues,
  formatCompactDonutValue,
  describeFilterScope,
  getBon2AccTone,
  getFocusTone,
} from './DashboardWidgets';
import type { AgentStat, RegionalStat, AsmStat, StoreStat } from '../../api/types';
import type { AppFilters } from '../MainLayout';
import { ALL_FIRMS, ALL_SCOPE, ALL_STORES } from '../../lib/filterValues';

function makeAgent(overrides: Partial<AgentStat> = {}): AgentStat {
  return {
    import_month: '2026-05',
    agent: 'Test Agent',
    site_code: 'STORE01',
    locatie: 'Test Store',
    firma: 'MobiCell',
    regional: 'RM1',
    asm: 'ASM1',
    acc_qty_realizat: 100,
    nr_bonuri: 50,
    nr_bon2acc: 30,
    proc_bon2acc: 60,
    total_vanzari: 10000,
    zile_lucrate: 22,
    medie_zilnica: 454.5,
    acc_focus_qty: 20,
    prc_focus_acc_qty: 20,
    target: 15000,
    proc_realizare_target: 66.67,
    promo_qty: 5,
    incentive_qty: 3,
    ...overrides,
  };
}

function makeStore(overrides: Partial<StoreStat> = {}): StoreStat {
  return {
    import_month: '2026-05',
    site_code: 'STORE01',
    locatie: 'Test Store',
    firma: 'MobiCell',
    regional: 'RM1',
    asm: 'ASM1',
    total_vanzari: 50000,
    qty_total: 200,
    nr_bonuri: 150,
    nr_agenti: 3,
    zile_active: 22,
    target: 60000,
    proc_realizare_target: 83.33,
    forecast_target_pct: 95,
    promo_qty: 10,
    incentive_qty: 5,
    ...overrides,
  };
}

function makeRegional(overrides: Partial<RegionalStat> = {}): RegionalStat {
  return {
    regional: 'RM1',
    total_vanzari: 200000,
    qty_total: 800,
    nr_bonuri: 500,
    nr_agenti: 10,
    zile_active: 22,
    target: 250000,
    proc_realizare_target: 80,
    forecast_target_pct: 90,
    promo_qty: 30,
    incentive_qty: 15,
    medie_zilnica: 9090.9,
    proc_bon2acc: 62,
    prc_focus_acc_qty: 25,
    ...overrides,
  };
}

function makeAsm(overrides: Partial<AsmStat> = {}): AsmStat {
  return {
    asm: 'ASM1',
    regional: 'RM1',
    total_vanzari: 100000,
    qty_total: 400,
    nr_bonuri: 250,
    nr_agenti: 5,
    zile_active: 22,
    target: 120000,
    proc_realizare_target: 83.33,
    promo_qty: 12,
    incentive_qty: 7,
    medie_zilnica: 4545.5,
    proc_bon2acc: 60,
    prc_focus_acc_qty: 30,
    ...overrides,
  };
}

function makeFilters(overrides: Partial<AppFilters> = {}): AppFilters {
  return {
    firma: ALL_FIRMS,
    rm: ALL_SCOPE,
    asm: ALL_SCOPE,
    magazin: ALL_STORES,
    agent: ALL_SCOPE,
    ...overrides,
  };
}

describe('getAgentSortValue', () => {
  it('returns numeric value for valid key', () => {
    expect(getAgentSortValue(makeAgent({ total_vanzari: 12345 }), 'total_vanzari')).toBe(12345);
  });

  it('returns NEGATIVE_INFINITY for null value', () => {
    expect(getAgentSortValue(makeAgent({ proc_bon2acc: null }), 'proc_bon2acc')).toBe(Number.NEGATIVE_INFINITY);
  });

  it('returns NEGATIVE_INFINITY for undefined value', () => {
    const agent = makeAgent();
    (agent as any).total_vanzari = undefined;
    expect(getAgentSortValue(agent, 'total_vanzari')).toBe(Number.NEGATIVE_INFINITY);
  });

  it('handles string-number coercion from agent name (returns NEGATIVE_INFINITY)', () => {
    expect(getAgentSortValue(makeAgent({ agent: 'Ion' }), 'agent' as any)).toBe(Number.NEGATIVE_INFINITY);
  });

  it('handles zero correctly', () => {
    expect(getAgentSortValue(makeAgent({ nr_bonuri: 0 }), 'nr_bonuri')).toBe(0);
  });
});

describe('getStoreDailyAverage', () => {
  it('computes daily average correctly', () => {
    expect(getStoreDailyAverage(makeStore({ total_vanzari: 22000, zile_active: 22 }))).toBe(1000);
  });

  it('returns 0 when zile_active is 0', () => {
    expect(getStoreDailyAverage(makeStore({ zile_active: 0 }))).toBe(0);
  });

  it('returns 0 when zile_active is falsy (null-like)', () => {
    expect(getStoreDailyAverage(makeStore({ zile_active: 0 }))).toBe(0);
  });
});

describe('getStoreSortValue', () => {
  it('returns numeric field value', () => {
    expect(getStoreSortValue(makeStore({ target: 75000 }), 'target')).toBe(75000);
  });

  it('delegates to getStoreDailyAverage for medie_zilnica key', () => {
    const store = makeStore({ total_vanzari: 44000, zile_active: 22 });
    expect(getStoreSortValue(store, 'medie_zilnica')).toBe(2000);
  });

  it('returns NEGATIVE_INFINITY for null', () => {
    expect(getStoreSortValue(makeStore({ proc_realizare_target: null }), 'proc_realizare_target')).toBe(Number.NEGATIVE_INFINITY);
  });
});

describe('getRegionalSortValue', () => {
  it('returns numeric value', () => {
    expect(getRegionalSortValue(makeRegional({ total_vanzari: 300000 }), 'total_vanzari')).toBe(300000);
  });

  it('returns NEGATIVE_INFINITY for null', () => {
    expect(getRegionalSortValue(makeRegional({ proc_bon2acc: null }), 'proc_bon2acc')).toBe(Number.NEGATIVE_INFINITY);
  });
});

describe('getAsmSortValue', () => {
  it('returns numeric value', () => {
    expect(getAsmSortValue(makeAsm({ nr_bonuri: 300 }), 'nr_bonuri')).toBe(300);
  });

  it('returns NEGATIVE_INFINITY for null', () => {
    expect(getAsmSortValue(makeAsm({ medie_zilnica: null }), 'medie_zilnica')).toBe(Number.NEGATIVE_INFINITY);
  });
});

describe('sumChartValues', () => {
  it('sums numeric values by key', () => {
    const rows = [
      { category: 'A', value: 100 },
      { category: 'B', value: 200 },
      { category: 'C', value: 300 },
    ];
    expect(sumChartValues(rows, 'value')).toBe(600);
  });

  it('treats missing keys as 0', () => {
    const rows = [{ a: 1 }, { b: 2 }];
    expect(sumChartValues(rows, 'a')).toBe(1);
  });

  it('returns 0 for empty array', () => {
    expect(sumChartValues([], 'value')).toBe(0);
  });

  it('coerces string numbers', () => {
    const rows = [{ value: '100' }, { value: '200' }];
    expect(sumChartValues(rows, 'value')).toBe(300);
  });
});

describe('formatCompactDonutValue', () => {
  it('formats small values without compact notation', () => {
    const result = formatCompactDonutValue(999);
    expect(result).toBe('999');
  });

  it('formats thousands with compact notation', () => {
    const result = formatCompactDonutValue(1500);
    expect(result.length).toBeLessThan(5);
  });

  it('formats millions with 1 decimal', () => {
    const result = formatCompactDonutValue(1_500_000);
    expect(result).toMatch(/1[.,]5/);
  });

  it('handles zero', () => {
    expect(formatCompactDonutValue(0)).toBe('0');
  });
});

describe('describeFilterScope', () => {
  it('returns default description when no filters applied', () => {
    expect(describeFilterScope(makeFilters())).toBe('Toata selectia activa');
  });

  it('describes single agent', () => {
    const desc = describeFilterScope(makeFilters({ agent: 'Ion Ionescu' }));
    expect(desc).toBe('Agent Ion Ionescu');
  });

  it('describes multiple agents comma-separated', () => {
    const desc = describeFilterScope(makeFilters({ agent: 'Agent1,Agent2,Agent3' }));
    expect(desc).toBe('3 agenti selectati');
  });

  it('describes single store', () => {
    const desc = describeFilterScope(makeFilters({ magazin: 'CRELECTROP' }));
    expect(desc).toBe('Magazin CRELECTROP');
  });

  it('describes multiple stores', () => {
    const desc = describeFilterScope(makeFilters({ magazin: 'STORE1,STORE2' }));
    expect(desc).toBe('2 magazine selectate');
  });

  it('describes regional when set', () => {
    const desc = describeFilterScope(makeFilters({ rm: 'Elena Popescu' }));
    expect(desc).toBe('Regional Elena Popescu');
  });

  it('describes firma when set', () => {
    const desc = describeFilterScope(makeFilters({ firma: 'MobiCell' }));
    expect(desc).toBe('Firma MobiCell');
  });

  it('prioritizes agent over store over regional over firma', () => {
    const desc = describeFilterScope(makeFilters({
      firma: 'MobiCell',
      rm: 'Elena',
      magazin: 'STORE1',
      agent: 'Agent1',
    }));
    expect(desc).toBe('Agent Agent1');
  });
});

describe('getBon2AccTone', () => {
  it('returns "Foarte bun" for value >= 31', () => {
    expect(getBon2AccTone(31).label).toBe('Foarte bun');
    expect(getBon2AccTone(35).label).toBe('Foarte bun');
  });

  it('returns "Solid" for value >= 30 and < 31', () => {
    expect(getBon2AccTone(30).label).toBe('Solid');
    expect(getBon2AccTone(30.5).label).toBe('Solid');
  });

  it('returns "Atentie" for value >= 28 and < 30', () => {
    expect(getBon2AccTone(28).label).toBe('Atentie');
    expect(getBon2AccTone(29.9).label).toBe('Atentie');
  });

  it('returns "Critic" for value < 28', () => {
    expect(getBon2AccTone(27.9).label).toBe('Critic');
    expect(getBon2AccTone(0).label).toBe('Critic');
  });

  it('includes cardClass and badgeClass in every tier', () => {
    for (const val of [35, 30, 28, 20]) {
      const tone = getBon2AccTone(val);
      expect(tone.cardClass).toBeTruthy();
      expect(tone.badgeClass).toBeTruthy();
    }
  });
});

describe('getFocusTone', () => {
  it('returns "Foarte bun" for value >= 8', () => {
    expect(getFocusTone(8).label).toBe('Foarte bun');
    expect(getFocusTone(10).label).toBe('Foarte bun');
  });

  it('returns "In target" for value >= 7 and < 8', () => {
    expect(getFocusTone(7).label).toBe('In target');
    expect(getFocusTone(7.5).label).toBe('In target');
  });

  it('returns "Sub tinta" for value >= 6 and < 7', () => {
    expect(getFocusTone(6).label).toBe('Sub tinta');
    expect(getFocusTone(6.9).label).toBe('Sub tinta');
  });

  it('returns "Critic" for value < 6', () => {
    expect(getFocusTone(5.9).label).toBe('Critic');
    expect(getFocusTone(0).label).toBe('Critic');
  });
});
