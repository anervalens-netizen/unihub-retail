import axios from 'axios';

const api = axios.create({ baseURL: '/api/hr' });

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('unihub_token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

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
  const { data } = await api.get('/leave-requests', { params });
  return data;
}

export async function createLeaveRequest(body: {
  agent_name: string;
  start_date: string;
  end_date: string;
  leave_type: string;
  notes?: string;
}): Promise<LeaveRequest> {
  const { data } = await api.post('/leave-requests', body);
  return data;
}

export async function updateLeaveStatus(id: number, status: 'approved' | 'rejected'): Promise<LeaveRequest> {
  const { data } = await api.patch(`/leave-requests/${id}`, { status });
  return data;
}

export async function fetchAgentPerformance(agentName: string): Promise<PerformancePoint[]> {
  const { data } = await api.get(`/performance/${encodeURIComponent(agentName)}`);
  return data;
}
