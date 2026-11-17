import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import { LogOut, RefreshCw } from 'lucide-react';
import {
  adminApi,
  formatBytes,
  formatDateTime,
  formatDuration,
  UnauthorizedError,
  type AdminJob,
  type AdminSummary,
  type AdminSystem,
  type PeriodSummary,
  type SystemSample,
} from '../adminApi';
import packageJson from '../../package.json';

const REFRESH_MS = 15_000;
const PAGE_SIZE = 50;
const STATUSES = ['', 'completed', 'failed', 'cancelled', 'queued', 'downloading', 'converting'];
const PLATFORMS = ['', 'youtube', 'instagram', 'tiktok', 'twitter', 'threads', 'facebook'];

const STATUS_STYLE: Record<string, string> = {
  completed: 'bg-success-light text-success-text',
  failed: 'bg-error-light text-error-text',
  cancelled: 'bg-surface-tertiary text-text-tertiary',
};

function goToLogin() {
  window.location.replace('/login');
}

function Tile({ label, value, hint }: { label: string; value: ReactNode; hint?: ReactNode }) {
  return (
    <div className="rounded-lg border border-border bg-white px-4 py-3">
      <p className="text-xs text-text-tertiary">{label}</p>
      <p className="mt-1 text-xl font-semibold text-text-primary tabular-nums">{value}</p>
      {hint && <p className="text-xs text-text-muted mt-0.5">{hint}</p>}
    </div>
  );
}

function PeriodTiles({ title, period }: { title: string; period: PeriodSummary }) {
  return (
    <div>
      <h3 className="text-sm font-medium text-text-secondary mb-2">{title}</h3>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        <Tile label="Downloads" value={period.total} hint={`${period.completed} ok · ${period.failed} failed${period.interrupted ? ` · ${period.interrupted} cut by restarts` : ''}`} />
        <Tile label="Success rate" value={period.success_rate !== null ? `${period.success_rate}%` : '—'} />
        <Tile label="Data delivered" value={formatBytes(period.bytes)} />
        <Tile label="Unique IPs" value={period.unique_ips} />
      </div>
    </div>
  );
}

/** One metric over time (0-100%). Single series: the title names it, no legend. */
function UsageChart({ title, samples, pick }: { title: string; samples: SystemSample[]; pick: (s: SystemSample) => number }) {
  const [hover, setHover] = useState<number | null>(null);
  const ref = useRef<SVGSVGElement>(null);
  const width = 600;
  const height = 120;
  const pad = { top: 8, right: 4, bottom: 4, left: 4 };
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;

  const x = (i: number) => pad.left + (samples.length <= 1 ? plotW : (i / (samples.length - 1)) * plotW);
  const y = (v: number) => pad.top + plotH - (Math.min(100, Math.max(0, v)) / 100) * plotH;
  const path = samples.map((s, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(pick(s)).toFixed(1)}`).join('');
  const latest = samples.length ? pick(samples[samples.length - 1]) : null;
  const point = hover !== null ? samples[hover] : null;

  const onMove = (event: React.MouseEvent<SVGSVGElement>) => {
    const box = ref.current?.getBoundingClientRect();
    if (!box || samples.length === 0) return;
    const ratio = (event.clientX - box.left) / box.width;
    setHover(Math.max(0, Math.min(samples.length - 1, Math.round(ratio * (samples.length - 1)))));
  };

  return (
    <div className="rounded-lg border border-border bg-white px-4 py-3">
      <div className="flex items-baseline justify-between">
        <h3 className="text-sm font-medium text-text-secondary">{title}</h3>
        <span className="text-sm tabular-nums text-text-primary">
          {point ? `${pick(point).toFixed(1)}% · ${formatDateTime(point.at)}` : latest !== null ? `${latest.toFixed(1)}% now` : '—'}
        </span>
      </div>
      {samples.length === 0 ? (
        <p className="py-8 text-center text-sm text-text-muted">No samples yet (one is taken every minute).</p>
      ) : (
        <svg
          ref={ref}
          viewBox={`0 0 ${width} ${height}`}
          preserveAspectRatio="none"
          className="mt-2 w-full h-28 cursor-crosshair"
          onMouseMove={onMove}
          onMouseLeave={() => setHover(null)}
          role="img"
          aria-label={`${title}, last ${samples.length} samples, latest ${latest?.toFixed(1)}%`}
        >
          {[0, 50, 100].map((v) => (
            <line key={v} x1={pad.left} x2={width - pad.right} y1={y(v)} y2={y(v)} stroke="#F0F0F0" strokeWidth={1} vectorEffect="non-scaling-stroke" />
          ))}
          <path d={path} fill="none" stroke="#2563EB" strokeWidth={2} vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
          {point && hover !== null && (
            <>
              <line x1={x(hover)} x2={x(hover)} y1={pad.top} y2={height - pad.bottom} stroke="#9A9A9A" strokeWidth={1} vectorEffect="non-scaling-stroke" />
              <circle cx={x(hover)} cy={y(pick(point))} r={4} fill="#2563EB" stroke="#FFFFFF" strokeWidth={2} vectorEffect="non-scaling-stroke" />
            </>
          )}
        </svg>
      )}
      <div className="flex justify-between text-xs text-text-muted mt-1">
        <span>{samples.length ? formatDateTime(samples[0].at) : ''}</span>
        <span>0–100%</span>
      </div>
    </div>
  );
}

function JobsTable({ jobs }: { jobs: AdminJob[] }) {
  if (jobs.length === 0) {
    return <p className="py-8 text-center text-sm text-text-muted">No downloads match.</p>;
  }
  return (
    <div className="overflow-x-auto -mx-4 sm:mx-0">
      <table className="min-w-full text-sm">
        <thead>
          <tr className="text-left text-xs text-text-tertiary border-b border-border">
            <th className="py-2 px-3 font-medium">When</th>
            <th className="py-2 px-3 font-medium">Status</th>
            <th className="py-2 px-3 font-medium">Video</th>
            <th className="py-2 px-3 font-medium">Quality</th>
            <th className="py-2 px-3 font-medium text-right">Size</th>
            <th className="py-2 px-3 font-medium text-right">Took</th>
            <th className="py-2 px-3 font-medium">IP</th>
            <th className="py-2 px-3 font-medium">Via</th>
          </tr>
        </thead>
        <tbody>
          {jobs.map((job) => (
            <tr key={job.id} className="border-b border-border-light align-top">
              <td className="py-2 px-3 whitespace-nowrap text-text-secondary tabular-nums">{formatDateTime(job.created_at)}</td>
              <td className="py-2 px-3">
                <span
                  className={`inline-block rounded px-1.5 py-0.5 text-xs ${STATUS_STYLE[job.status] ?? 'bg-info-light text-info-text'}`}
                  title={job.error_message ?? undefined}
                >
                  {job.status}
                </span>
              </td>
              <td className="py-2 px-3 max-w-xs">
                <a href={job.url} target="_blank" rel="noreferrer noopener" className="text-text-primary hover:text-accent hover:underline break-words line-clamp-2" title={job.title || job.url}>
                  {job.title || job.url}
                </a>
                <p className="text-xs text-text-muted line-clamp-2">
                  {job.platform}
                  {job.error_message ? ` · ${job.error_message}` : ''}
                </p>
              </td>
              <td className="py-2 px-3 text-text-secondary">{job.quality ?? '—'}</td>
              <td className="py-2 px-3 text-right tabular-nums text-text-secondary">{formatBytes(job.file_size)}</td>
              <td className="py-2 px-3 text-right tabular-nums text-text-secondary">{formatDuration(job.elapsed_seconds)}</td>
              <td className="py-2 px-3 whitespace-nowrap tabular-nums text-text-secondary">{job.client_ip ?? '—'}</td>
              <td className="py-2 px-3 text-text-secondary" title={job.user_agent ?? undefined}>
                {job.client_name ? `${job.source ?? ''} · ${job.client_name}` : job.source ?? '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function AdminPage() {
  const [summary, setSummary] = useState<AdminSummary | null>(null);
  const [system, setSystem] = useState<AdminSystem | null>(null);
  const [jobs, setJobs] = useState<{ total: number; items: AdminJob[] } | null>(null);
  const [filters, setFilters] = useState({ status: '', platform: '', q: '' });
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);

  const load = useCallback(async () => {
    try {
      const [s, sys, j] = await Promise.all([
        adminApi.summary(),
        adminApi.system(24),
        adminApi.jobs({ limit: PAGE_SIZE, offset: page * PAGE_SIZE, ...filters }),
      ]);
      setSummary(s);
      setSystem(sys);
      setJobs(j);
      setError(null);
      setUpdatedAt(new Date());
    } catch (e) {
      if (e instanceof UnauthorizedError) return goToLogin();
      setError(e instanceof Error ? e.message : 'Could not load data');
    }
  }, [filters, page]);

  useEffect(() => {
    document.title = 'Admin · Wololo Converter';
  }, []);

  useEffect(() => {
    load();
    const timer = window.setInterval(load, REFRESH_MS);
    return () => window.clearInterval(timer);
  }, [load]);

  // Search as you type, without a request per keystroke
  useEffect(() => {
    const timer = window.setTimeout(() => {
      setPage(0);
      setFilters((f) => (f.q === query ? f : { ...f, q: query }));
    }, 300);
    return () => window.clearTimeout(timer);
  }, [query]);

  const logout = async () => {
    await adminApi.logout().catch(() => undefined);
    goToLogin();
  };

  const now = system?.now;
  const pages = jobs ? Math.max(1, Math.ceil(jobs.total / PAGE_SIZE)) : 1;

  return (
    <div className="min-h-screen bg-surface-secondary">
      <header className="bg-white border-b border-border-light px-4 py-4">
        <div className="max-w-6xl mx-auto flex items-center justify-between gap-3">
          <a href="/" className="flex items-center gap-3 text-text-primary">
            <img src="/wololo-left.png" alt="" className="w-9 h-9 object-contain" />
            <span className="font-semibold">Wololo admin</span>
          </a>
          <div className="flex items-center gap-2 text-sm">
            <span className="hidden sm:inline text-text-muted">
              {updatedAt ? `Updated ${updatedAt.toLocaleTimeString()}` : 'Loading…'}
            </span>
            <button type="button" className="btn-ghost !px-2" onClick={load} aria-label="Refresh">
              <RefreshCw size={16} />
            </button>
            <button type="button" className="btn-ghost !px-3 flex items-center gap-1.5" onClick={logout}>
              <LogOut size={16} /> Sign out
            </button>
          </div>
        </div>
      </header>

      <main className="px-4 py-6">
        <div className="max-w-6xl mx-auto space-y-8">
          {error && (
            <p role="alert" className="rounded-lg border border-error/30 bg-error-light px-4 py-3 text-sm text-error-text">
              {error}
            </p>
          )}

          {now && (
            <section className="space-y-3">
              <h2 className="text-lg font-semibold text-text-primary">Server</h2>
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2">
                <Tile
                  label="CPU"
                  value={`${now.cpu_percent.toFixed(0)}%`}
                  hint={now.load_average ? `load ${now.load_average.join(' / ')} · ${now.cpu_count} cores` : `${now.cpu_count} cores`}
                />
                <Tile label="Memory" value={`${now.memory_percent.toFixed(0)}%`} hint={`${formatBytes(now.memory_used_bytes)} of ${formatBytes(now.memory_total_bytes)}`} />
                <Tile label="Disk" value={`${now.disk_percent.toFixed(0)}%`} hint={`${formatBytes(now.disk_used_bytes)} of ${formatBytes(now.disk_total_bytes)}`} />
                <Tile label="Downloads now" value={`${now.active_downloads} / ${now.max_concurrent_downloads}`} hint={`${now.queued_downloads} waiting`} />
                <Tile label="Temp files" value={formatBytes(now.temp_dir_bytes)} />
                <Tile label="Backend memory" value={formatBytes(now.process_memory_bytes)} hint={`up since ${formatDateTime(now.process_started_at)}`} />
              </div>
              <div className="grid gap-2 lg:grid-cols-3">
                <UsageChart title="CPU, last 24 h" samples={system.samples} pick={(s) => s.cpu} />
                <UsageChart title="Memory, last 24 h" samples={system.samples} pick={(s) => s.memory} />
                <UsageChart title="Disk, last 24 h" samples={system.samples} pick={(s) => s.disk} />
              </div>
            </section>
          )}

          {summary && (
            <section className="space-y-4">
              <h2 className="text-lg font-semibold text-text-primary">Usage</h2>
              <PeriodTiles title="Last 24 hours" period={summary.last_24h} />
              <PeriodTiles title="Last 7 days" period={summary.last_7d} />
              <PeriodTiles title="Last 30 days" period={summary.last_30d} />
              <div className="grid gap-4 md:grid-cols-2">
                <div className="rounded-lg border border-border bg-white px-4 py-3">
                  <h3 className="text-sm font-medium text-text-secondary mb-2">Top IPs, last 7 days</h3>
                  {summary.top_ips_7d.length === 0 ? (
                    <p className="text-sm text-text-muted">No IPs recorded yet (recorded from v0.12.0 on).</p>
                  ) : (
                    <table className="w-full text-sm">
                      <tbody>
                        {summary.top_ips_7d.map((row) => (
                          <tr key={row.ip} className="border-b border-border-light last:border-0">
                            <td className="py-1.5">
                              <button type="button" className="tabular-nums hover:text-accent hover:underline" onClick={() => setQuery(row.ip)}>
                                {row.ip}
                              </button>
                            </td>
                            <td className="py-1.5 text-right tabular-nums">{row.count}</td>
                            <td className="py-1.5 text-right text-text-muted">{formatDateTime(row.last_seen)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
                <div className="rounded-lg border border-border bg-white px-4 py-3">
                  <h3 className="text-sm font-medium text-text-secondary mb-2">Platforms, last 7 days</h3>
                  <table className="w-full text-sm">
                    <tbody>
                      {summary.platforms_7d.map((row) => (
                        <tr key={row.platform} className="border-b border-border-light last:border-0">
                          <td className="py-1.5">{row.platform}</td>
                          <td className="py-1.5 text-right tabular-nums">{row.count}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </section>
          )}

          <section className="space-y-3">
            <h2 className="text-lg font-semibold text-text-primary">Download history</h2>
            <div className="flex flex-wrap gap-2">
              <input
                className="input-field !py-2 max-w-xs"
                placeholder="Search title, link, IP or key"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                aria-label="Search downloads"
              />
              <select
                className="input-field !py-2 !w-auto"
                value={filters.status}
                onChange={(e) => {
                  setPage(0);
                  setFilters({ ...filters, status: e.target.value });
                }}
                aria-label="Status"
              >
                {STATUSES.map((s) => <option key={s} value={s}>{s || 'Any status'}</option>)}
              </select>
              <select
                className="input-field !py-2 !w-auto"
                value={filters.platform}
                onChange={(e) => {
                  setPage(0);
                  setFilters({ ...filters, platform: e.target.value });
                }}
                aria-label="Platform"
              >
                {PLATFORMS.map((p) => <option key={p} value={p}>{p || 'Any platform'}</option>)}
              </select>
            </div>
            <div className="rounded-lg border border-border bg-white px-4 py-2">
              {jobs ? <JobsTable jobs={jobs.items} /> : <p className="py-8 text-center text-sm text-text-muted">Loading…</p>}
            </div>
            {jobs && (
              <div className="flex items-center justify-between text-sm text-text-tertiary">
                <span>{jobs.total} downloads</span>
                <div className="flex items-center gap-2">
                  <button type="button" className="btn-ghost !px-3 !py-1" disabled={page === 0} onClick={() => setPage(page - 1)}>
                    Previous
                  </button>
                  <span className="tabular-nums">{page + 1} / {pages}</span>
                  <button type="button" className="btn-ghost !px-3 !py-1" disabled={page + 1 >= pages} onClick={() => setPage(page + 1)}>
                    Next
                  </button>
                </div>
              </div>
            )}
          </section>
        </div>
      </main>

      <footer className="py-6 px-4 text-center text-xs text-text-muted">
        <a href="/status" className="hover:text-accent hover:underline underline-offset-2">
          _status • v{packageJson.version}
        </a>
      </footer>
    </div>
  );
}
