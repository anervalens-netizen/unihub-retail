import { generatedGet } from './generated/client';
import type { RetailOperationPaths, RetailOperationQueries } from './generated/contracts';
import type {
  AsmHistoryPoint,
  AsmPerformance,
  AsmSalaryBreakdown,
  ManagerOverview,
} from './generated/runtime-types';

export async function fetchAsmPerformance(month: string, regional?: string): Promise<AsmPerformance[]> {
  const params: RetailOperationQueries['get_asm_perf_api_hr_asm_performance_get'] = { month, regional };
  return generatedGet('get_asm_perf_api_hr_asm_performance_get', { params });
}

export async function fetchAsmHistory(asmName: string, months = 6): Promise<AsmHistoryPoint[]> {
  const pathParams: RetailOperationPaths['get_asm_perf_history_api_hr_asm_performance__asm_name__history_get'] = { asm_name: asmName };
  const params: RetailOperationQueries['get_asm_perf_history_api_hr_asm_performance__asm_name__history_get'] = { months };
  return await generatedGet('get_asm_perf_history_api_hr_asm_performance__asm_name__history_get', {
    pathParams,
    params,
  });
}

export async function fetchManagerOverview(month: string, signal?: AbortSignal): Promise<ManagerOverview[]> {
  const params: RetailOperationQueries['get_manager_overview_api_hr_manager_overview_get'] = { month };
  return generatedGet('get_manager_overview_api_hr_manager_overview_get', { params, signal });
}

export async function fetchAsmSalary(asm: string, month: string): Promise<AsmSalaryBreakdown> {
  const pathParams: RetailOperationPaths['get_asm_salary_api_hr_asm_salary__asm_name__get'] = { asm_name: asm };
  const params: RetailOperationQueries['get_asm_salary_api_hr_asm_salary__asm_name__get'] = { month };
  return await generatedGet('get_asm_salary_api_hr_asm_salary__asm_name__get', {
    pathParams,
    params,
  });
}

export type { AsmHistoryPoint, AsmPerformance, AsmSalaryBreakdown, ManagerOverview };
