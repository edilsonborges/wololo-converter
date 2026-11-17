/** Client for the status page (public) and the admin view (signed-in). */

export type ComponentState = 'operational' | 'degraded' | 'outage' | 'no_data';

export interface StatusDay {
  date: string;
  status: ComponentState;
  uptime: number | null;
  completed?: number;
  failed?: number;
  note?: string;
  estimated?: boolean;
}

export interface StatusComponent {
  id: string;
  name: string;
  group: 'Service' | 'Downloads';
  status: ComponentState;
  uptime: number | null;
  latency_ms: number | null;
  days: StatusDay[];
}

export interface StatusResponse {
  status: Exclude<ComponentState, 'no_data'>;
  generated_at: string;
  days: number;
  components: StatusComponent[];
}

export interface AdminJob {
  id: string;
  created_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  elapsed_seconds: number | null;
  queued_seconds: number | null;
  status: string;
  platform: string;
  quality: string | null;
  url: string;
  title: string | null;
  filename: string | null;
  file_size: number | null;
  duration: number | null;
  error_message: string | null;
  client_ip: string | null;
  client_name: string | null;
  source: string | null;
  user_agent: string | null;
}

export interface PeriodSummary {
  total: number;
  completed: number;
  failed: number;
  cancelled: number;
  interrupted: number;
  success_rate: number | null;
  bytes: number;
  unique_ips: number;
}

export interface AdminSummary {
  last_24h: PeriodSummary;
  last_7d: PeriodSummary;
  last_30d: PeriodSummary;
  platforms_7d: { platform: string; count: number }[];
  top_ips_7d: { ip: string; count: number; last_seen: string | null }[];
}

export interface SystemNow {
  cpu_percent: number;
  cpu_count: number | null;
  load_average: number[] | null;
  memory_percent: number;
  memory_used_bytes: number;
  memory_total_bytes: number;
  disk_percent: number;
  disk_used_bytes: number;
  disk_total_bytes: number;
  temp_dir_bytes: number;
  process_memory_bytes: number;
  process_started_at: string;
  active_downloads: number;
  queued_downloads: number;
  max_concurrent_downloads: number;
}

export interface SystemSample {
  at: string;
  cpu: number;
  memory: number;
  disk: number;
  active: number;
  queued: number;
}

export interface AdminSystem {
  now: SystemNow;
  samples: SystemSample[];
}

export type HistoryRange = '24h' | '7d' | '30d' | '90d' | 'all';

export interface HistoryBucket {
  start: string;
  end: string;
  completed: number;
  failed: number;
  cancelled: number;
  other: number;
}

export interface AdminInsights {
  range: HistoryRange;
  bucket_seconds: number;
  total: number;
  buckets: HistoryBucket[];
  platforms: { platform: string; count: number }[];
}

export interface HistoryFilters {
  status?: string;
  platform?: string;
  q?: string;
  range?: HistoryRange;
  since?: string;
  until?: string;
}

export class UnauthorizedError extends Error {}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    credentials: 'same-origin',
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
  });
  if (response.status === 401) {
    const body = await response.json().catch(() => ({}));
    throw new UnauthorizedError(body.detail || 'Not signed in');
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

function toQuery(params: object): string {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== '') query.set(key, String(value));
  });
  return query.toString();
}

export const statusApi = {
  get: () => request<StatusResponse>('/api/status'),
};

export const adminApi = {
  login: (password: string) =>
    request<{ ok: boolean }>('/api/admin/login', { method: 'POST', body: JSON.stringify({ password }) }),
  logout: () => request<{ ok: boolean }>('/api/admin/logout', { method: 'POST' }),
  me: () => request<{ ok: boolean }>('/api/admin/me'),
  summary: () => request<AdminSummary>('/api/admin/summary'),
  system: (hours = 24) => request<AdminSystem>(`/api/admin/system?hours=${hours}`),
  jobs: (params: HistoryFilters & { limit?: number; offset?: number }) =>
    request<{ total: number; items: AdminJob[] }>(`/api/admin/jobs?${toQuery(params)}`),
  insights: (params: HistoryFilters) =>
    request<AdminInsights>(
      `/api/admin/insights?${toQuery({ ...params, since: undefined, until: undefined, tz_offset: new Date().getTimezoneOffset() })}`,
    ),
};

export function formatBytes(bytes: number | null | undefined): string {
  if (bytes == null) return '—';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(value >= 10 || unit === 0 ? 0 : 1)} ${units[unit]}`;
}

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null) return '—';
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ${seconds % 60}s`;
  return `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
}

export function formatDateTime(iso: string | null): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleString(undefined, {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit',
  });
}
