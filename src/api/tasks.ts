import axios from 'axios';

const api = axios.create({ baseURL: '/api/tasks' });

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('unihub_token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

export interface Task {
  id: number;
  title: string;
  assignee: string | null;
  site_code: string | null;
  deadline: string | null;
  status: 'deschis' | 'in_lucru' | 'inchis';
  source: string;
  source_meta: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface TaskCreate {
  title: string;
  assignee?: string | null;
  site_code?: string | null;
  deadline?: string | null;
  status?: string;
  source?: string;
  source_meta?: Record<string, unknown> | null;
}

export interface TaskUpdate {
  title?: string;
  assignee?: string | null;
  site_code?: string | null;
  deadline?: string | null;
  status?: string;
}

export async function fetchTasks(params?: { status?: string; assignee?: string; site_code?: string }): Promise<Task[]> {
  const { data } = await api.get('', { params });
  return data;
}

export async function createTask(body: TaskCreate): Promise<Task> {
  const { data } = await api.post('', body);
  return data;
}

export async function updateTask(id: number, body: TaskUpdate): Promise<Task> {
  const { data } = await api.patch(`/${id}`, body);
  return data;
}

export async function deleteTask(id: number): Promise<void> {
  await api.delete(`/${id}`);
}

export async function fetchMyTasks(status?: string): Promise<Task[]> {
  const { data } = await api.get('/my', { params: status ? { status } : undefined });
  return data;
}

export async function fetchMyPendingCount(): Promise<number> {
  const { data } = await api.get('/my/count');
  return data.count as number;
}

export async function updateMyTask(id: number, body: TaskUpdate): Promise<Task> {
  const { data } = await api.patch(`/my/${id}`, body);
  return data;
}
