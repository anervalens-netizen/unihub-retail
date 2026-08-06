import { generatedGet } from './generated/client';
import type {
  AsmHistoryPoint,
  AsmPerformance,
  AsmSalaryBreakdown,
  ManagerOverview,
} from './generated/runtime-types';

export async function fetchAsmPerformance(month: string, regional?: string): Promise<AsmPerformance[]> {
  return await generatedGet('get_asm_perf_api_hr_asm_performance_get', { params: { month, regional } }) as AsmPerformance[];
}

export async function fetchAsmHistory(asmName: string, months = 6): Promise<AsmHistoryPoint[]> {
  return await generatedGet('get_asm_perf_history_api_hr_asm_performance__asm_name__history_get', {
    pathParams: { asm_name: asmName },
    params: { months },
  }) as AsmHistoryPoint[];
}

export async function fetchManagerOverview(month: string, signal?: AbortSignal): Promise<ManagerOverview[]> {
  return await generatedGet('get_manager_overview_api_hr_manager_overview_get', { params: { month }, signal }) as ManagerOverview[];
}

export async function fetchAsmSalary(asm: string, month: string): Promise<AsmSalaryBreakdown> {
  return await generatedGet('get_asm_salary_api_hr_asm_salary__asm_name__get', {
    pathParams: { asm_name: asm },
    params: { month },
  }) as AsmSalaryBreakdown;
}

export type { AsmHistoryPoint, AsmPerformance, AsmSalaryBreakdown, ManagerOverview };
