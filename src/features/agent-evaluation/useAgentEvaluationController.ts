import { useCallback, useEffect, useMemo, useState } from 'react';

import {
  fetchAgentEvaluation,
  fetchAgentEvaluationV2,
  type AgentEvaluationResponse,
  type AgentEvaluationV2Response,
} from '../../api/agents';
import { shiftMonth } from '../../lib/dates';
import {
  getSortValue,
  getV2SortValue,
  type SortKey,
  type V2SortKey,
} from './AgentEvaluationTables';

const EMPTY_RESPONSE: AgentEvaluationResponse = { months: [], firmas: [], asms: [], stores: [], rows: [] };
const EMPTY_V2_RESPONSE: AgentEvaluationV2Response = { months: [], firmas: [], asms: [], stores: [], rows: [] };

function latestClosedMonth(currentMonth: string, months: readonly string[]): string {
  const available = months.filter((month) => /^\d{4}-\d{2}$/.test(month) && month < currentMonth).sort();
  return available.at(-1) ?? (shiftMonth(currentMonth, -1) !== currentMonth ? shiftMonth(currentMonth, -1) : '');
}

function compareValues(left: string | number, right: string | number) {
  return typeof left === 'number' && typeof right === 'number'
    ? left - right
    : String(left).localeCompare(String(right), 'ro');
}

export function useAgentEvaluationController(currentMonth: string, months: string[]) {
  const [data, setData] = useState<AgentEvaluationResponse>(EMPTY_RESPONSE);
  const [v2Data, setV2Data] = useState<AgentEvaluationV2Response>(EMPTY_V2_RESPONSE);
  const [mode, setMode] = useState<'current' | 'new'>('current');
  const [selectedMonths, setSelectedMonths] = useState<string[]>(() => {
    const initial = latestClosedMonth(currentMonth, months); return initial ? [initial] : [];
  });
  const [firma, setFirma] = useState('');
  const [asm, setAsm] = useState('');
  const [selectedStores, setSelectedStores] = useState<string[]>([]);
  const [sortKey, setSortKey] = useState<SortKey>('total_points');
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('desc');
  const [v2SortKey, setV2SortKey] = useState<V2SortKey>('total_score');
  const [v2SortDirection, setV2SortDirection] = useState<'asc' | 'desc'>('desc');
  const [loading, setLoading] = useState(false);
  const [mobileFiltersOpen, setMobileFiltersOpen] = useState(false);
  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = {
        months: selectedMonths.length ? selectedMonths.join(',') : undefined,
        asm: asm || undefined,
        site_code: selectedStores.length ? selectedStores : undefined,
      };
      if (mode === 'new') setV2Data(await fetchAgentEvaluationV2(params));
      else setData(await fetchAgentEvaluation(params));
    } finally { setLoading(false); }
  }, [asm, mode, selectedMonths, selectedStores]);
  useEffect(() => { void load(); }, [load]);
  const toggleMonth = (value: string) => setSelectedMonths((current) => current.includes(value) ? current.filter((item) => item !== value) : [...current, value].sort());
  const toggleStore = (value: string) => setSelectedStores((current) => current.includes(value) ? current.filter((item) => item !== value) : [...current, value].sort());
  const rows = useMemo(() => {
    const filtered = firma ? data.rows.filter((row) => row.firma.toLowerCase() === firma.toLowerCase()) : data.rows;
    return [...filtered].sort((left, right) => {
      const result = compareValues(getSortValue(left, sortKey), getSortValue(right, sortKey));
      return sortDirection === 'asc' ? result : -result;
    });
  }, [data.rows, firma, sortDirection, sortKey]);
  const v2Rows = useMemo(() => {
    const filtered = firma ? v2Data.rows.filter((row) => row.firma.toLowerCase() === firma.toLowerCase()) : v2Data.rows;
    return [...filtered].sort((left, right) => {
      const result = compareValues(getV2SortValue(left, v2SortKey), getV2SortValue(right, v2SortKey));
      return v2SortDirection === 'asc' ? result : -result;
    });
  }, [firma, v2Data.rows, v2SortDirection, v2SortKey]);
  const handleSort = (key: SortKey) => {
    if (key === sortKey) { setSortDirection((value) => value === 'asc' ? 'desc' : 'asc'); return; }
    setSortKey(key); setSortDirection(key === 'agent' || key === 'month' ? 'asc' : 'desc');
  };
  const handleV2Sort = (key: V2SortKey) => {
    if (key === v2SortKey) { setV2SortDirection((value) => value === 'asc' ? 'desc' : 'asc'); return; }
    setV2SortKey(key); setV2SortDirection(key === 'agent' || key === 'eligibility_status' ? 'asc' : 'desc');
  };
  const summary = useMemo(() => ({
    agents: new Set(rows.map((row) => row.agent)).size,
    avgPoints: rows.length ? rows.reduce((sum, row) => sum + row.total_points, 0) / rows.length : 0,
    totalSales: rows.reduce((sum, row) => sum + row.total_sales, 0),
    premiumRows: rows.filter((row) => row.premium_glass_points >= 2).length,
  }), [rows]);
  const optionData = mode === 'new' ? v2Data : data;
  const resetManager = (value: string) => { setAsm(value); setSelectedStores([]); };
  return {
    mode, setMode, selectedMonths, setSelectedMonths, firma, setFirma, asm,
    resetManager, selectedStores, setSelectedStores, sortKey, sortDirection,
    v2SortKey, v2SortDirection, loading, mobileFiltersOpen, setMobileFiltersOpen,
    load, toggleMonth, toggleStore, rows, v2Rows, handleSort, handleV2Sort,
    summary, optionData,
  };
}

export type AgentEvaluationController = ReturnType<typeof useAgentEvaluationController>;

