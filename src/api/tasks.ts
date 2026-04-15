import { client } from './client';

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
  const { data } = await client.get('/api/tasks', { params });
  return data;
}

export async function createTask(body: TaskCreate): Promise<Task> {
  const { data } = await client.post('/api/tasks', body);
  return data;
}

export async function updateTask(id: number, body: TaskUpdate): Promise<Task> {
  const { data } = await client.patch(`/api/tasks/${id}`, body);
  return data;
}

export async function deleteTask(id: number): Promise<void> {
  await client.delete(`/api/tasks/${id}`);
}

export async function fetchMyTasks(status?: string): Promise<Task[]> {
  const { data } = await client.get('/api/tasks/my', { params: status ? { status } : undefined });
  return data;
}

export async function fetchMyPendingCount(): Promise<number> {
  const { data } = await client.get('/api/tasks/my/count');
  return data.count as number;
}

export async function updateMyTask(id: number, body: TaskUpdate): Promise<Task> {
  const { data } = await client.patch(`/api/tasks/my/${id}`, body);
  return data;
}
