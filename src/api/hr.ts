import { client } from './client';

export interface LeaveRequest {
  id: number;
  agent_name: string;
  start_date: string;
  end_date: string;
  leave_type: string;
  notes: string | null;
  status: 'pending' | 'approved' | 'rejected';
  created_at: string;
}

export interface PerformancePoint {
  import_month: string;
  total_value: number;
  transaction_count: number;
  active_days: number;
  target_pct: number;
}

export async function fetchLeaveRequests(params?: { status?: string; agent_name?: string }): Promise<LeaveRequest[]> {
  const { data } = await client.get('/api/hr/leave-requests', { params });
  return data;
}

export async function createLeaveRequest(body: {
  agent_name: string;
  start_date: string;
  end_date: string;
  leave_type: string;
  notes?: string;
}): Promise<LeaveRequest> {
  const { data } = await client.post('/api/hr/leave-requests', body);
  return data;
}

export async function updateLeaveStatus(id: number, status: 'approved' | 'rejected'): Promise<LeaveRequest> {
  const { data } = await client.patch(`/api/hr/leave-requests/${id}`, { status });
  return data;
}

export async function fetchAgentPerformance(agentName: string): Promise<PerformancePoint[]> {
  const { data } = await client.get(`/api/hr/performance/${encodeURIComponent(agentName)}`);
  return data;
}

export interface AsmPerformance {
  asm: string;
  regional: string;
  total_sales: number;
  total_target: number;
  target_pct: number | null;
  forecast_sales: number;
  forecast_target_pct: number | null;
  is_forecast: boolean;
  active_stores: number;
  active_agents: number;
  pct_bon2acc: number;
  pct_focus: number;
  total_visits: number;
  avg_completion: number | null;
  avg_duration: number | null;
  distinct_stores_visited: number;
  checklist_score: number | null;
  approved_pct: number | null;
}

export interface AsmHistoryPoint {
  month: string;
  total_sales: number;
  total_target: number;
  target_pct: number | null;
  forecast_sales: number;
  forecast_target_pct: number | null;
  is_forecast: boolean;
  active_stores: number;
  total_visits: number;
  avg_completion: number | null;
  avg_duration: number | null;
}

export async function fetchAsmPerformance(month: string, regional?: string): Promise<AsmPerformance[]> {
  const { data } = await client.get('/api/hr/asm-performance', { params: { month, regional } });
  return data;
}

export async function fetchAsmHistory(asmName: string, months = 6): Promise<AsmHistoryPoint[]> {
  const { data } = await client.get(`/api/hr/asm-performance/${encodeURIComponent(asmName)}/history`, { params: { months } });
  return data;
}

export interface AssignableUser {
  full_name: string;
  role: 'asm' | 'tl';
  username: string;
}

export async function fetchAssignableUsers(): Promise<AssignableUser[]> {
  const { data } = await client.get('/api/hr/users');
  return data;
}
