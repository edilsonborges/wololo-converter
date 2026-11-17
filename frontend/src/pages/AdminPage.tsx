import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight, LogOut, RefreshCw, Search, X } from 'lucide-react';
import {
  adminApi,
  formatBytes,
  formatDateTime,
  formatDuration,
  UnauthorizedError,
  type AdminInsights,
  type AdminJob,
  type AdminSummary,
  type AdminSystem,
  type HistoryBucket,
  type HistoryRange,
  type PeriodSummary,
  type SystemSample,
} from '../adminApi';
import { bucketRange, HistoryHistogram, PLATFORM_COLORS, PLATFORM_NAMES, PlatformDonut } from './adminCharts';
import packageJson from '../../package.json';

const REFRESH_MS = 15_000;
const PAGE_SIZES = [25, 50, 100, 200];
const STATUSES = ['', 'completed', 'failed', 'cancelled', 'queued', 'downloading', 'converting'];
const RANGES: { value: HistoryRange; label: string }[] = [
  { value: '24h', label: '24 h' },
  { value: '7d', label: '7 days' },
  { value: '30d', label: '30 days' },
  { value: '90d', label: '90 days' },
  { value: 'all', label: 'All' },
];

const STATUS_STYLE: Record<string, string> = {
  completed: 'bg-success-light text-success-text',
  failed: 'bg-error-light text-error-text',
  cancelled: 'bg-surface-tertiary text-text-tertiary',
};

// Several requests can fail at once (and effects run twice in dev); navigate once
let redirecting = false;
function goToLogin() {
  if (redirecting) return;
  redirecting = true;
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

function Panel({ title, children, actions }: { title: string; children: ReactNode; actions?: ReactNode }) {
  return (
    <div className="rounded-lg border border-border bg-white px-4 py-3">
      <div className="flex items-center justify-between gap-2 mb-2">
        <h3 className="text-sm font-medium text-text-secondary">{title}</h3>
        {actions}
      </div>
      {children}
    </div>
  );
}

function PeriodTiles({ title, period }: { title: string; period: PeriodSummary }) {
  return (
    <div>
      <h3 className="text-sm font-medium text-text-secondary mb-2">{title}</h3>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        <Tile
          label="Downloads"
          value={period.total}
          hint={`${period.completed} ok · ${period.failed} failed${period.interrupted ? ` · ${period.interrupted} cut by restarts` : ''}`}
        />
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
    <Panel
      title={title}
      actions={
        <span className="text-sm tabular-nums text-text-primary">
          {point ? `${pick(point).toFixed(1)}% · ${formatDateTime(point.at)}` : latest !== null ? `${latest.toFixed(1)}% now` : '—'}
        </span>
      }
    >
      {samples.length === 0 ? (
        <p className="py-8 text-center text-sm text-text-muted">No samples yet (one is taken every minute).</p>
      ) : (
        <svg
          ref={ref}
          viewBox={`0 0 ${width} ${height}`}
          preserveAspectRatio="none"
          className="w-full h-28 cursor-crosshair"
          onMouseMove={onMove}
          onMouseLeave={() => setHover(null)}
          role="img"
          aria-label={`${title}, latest ${latest?.toFixed(1)}%`}
        >
          {[0, 50, 100].map((v) => (
            <line key={v} x1={pad.left} x2={width - pad.right} y1={y(v)} y2={y(v)} stroke="#F0F0F0" strokeWidth={1} vectorEffect="non-scaling-stroke" />
          ))}
          <path d={path} fill="none" stroke="#2a78d6" strokeWidth={2} vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
          {point && hover !== null && (
            <>
              <line x1={x(hover)} x2={x(hover)} y1={pad.top} y2={height - pad.bottom} stroke="#9A9A9A" strokeWidth={1} vectorEffect="non-scaling-stroke" />
              <circle cx={x(hover)} cy={y(pick(point))} r={4} fill="#2a78d6" stroke="#FFFFFF" strokeWidth={2} vectorEffect="non-scaling-stroke" />
            </>
          )}
        </svg>
      )}
      <div className="flex justify-between text-xs text-text-muted mt-1">
        <span>{samples.length ? formatDateTime(samples[0].at) : ''}</span>
        <span>0–100%</span>
      </div>
    </Panel>
  );
}

function pageWindow(page: number, pages: number): (number | '…')[] {
  const wanted = new Set([0, pages - 1, page - 1, page, page + 1]);
  const list = [...wanted].filter((p) => p >= 0 && p < pages).sort((a, b) => a - b);
  const out: (number | '…')[] = [];
  list.forEach((p, i) => {
    if (i && p - list[i - 1] > 1) out.push('…');
    out.push(p);
  });
  return out;
}

function Pagination({
  page,
  pageSize,
  total,
  onPage,
  onPageSize,
}: {
  page: number;
  pageSize: number;
  total: number;
  onPage: (page: number) => void;
  onPageSize: (size: number) => void;
}) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  const first = total === 0 ? 0 : page * pageSize + 1;
  const last = Math.min(total, (page + 1) * pageSize);
  const navButton = 'h-8 min-w-8 px-2 rounded-md text-sm tabular-nums disabled:opacity-40 disabled:cursor-not-allowed hover:bg-surface-tertiary';

  return (
    <nav className="flex flex-wrap items-center justify-between gap-3 text-sm text-text-tertiary" aria-label="Pages">
      <div className="flex items-center gap-2">
        <span className="tabular-nums">
          {first}–{last} of {total}
        </span>
        <label className="flex items-center gap-1">
          <span className="sr-only sm:not-sr-only">Rows</span>
          <select
            className="rounded-md border border-border bg-white px-2 py-1 text-text-primary"
            value={pageSize}
            onChange={(e) => onPageSize(Number(e.target.value))}
            aria-label="Rows per page"
          >
            {PAGE_SIZES.map((size) => (
              <option key={size} value={size}>{size}</option>
            ))}
          </select>
        </label>
      </div>
      <div className="flex items-center gap-1">
        <button type="button" className={navButton} disabled={page === 0} onClick={() => onPage(0)} aria-label="First page">
          <ChevronsLeft size={16} />
        </button>
        <button type="button" className={navButton} disabled={page === 0} onClick={() => onPage(page - 1)} aria-label="Previous page">
          <ChevronLeft size={16} />
        </button>
        {pageWindow(page, pages).map((p, i) =>
          p === '…' ? (
            <span key={`gap-${i}`} className="px-1 text-text-muted">…</span>
          ) : (
            <button
              key={p}
              type="button"
              className={`${navButton} ${p === page ? 'bg-text-primary text-white hover:bg-text-primary' : 'text-text-secondary'}`}
              onClick={() => onPage(p)}
              aria-current={p === page ? 'page' : undefined}
            >
              {p + 1}
            </button>
          ),
        )}
        <button type="button" className={navButton} disabled={page + 1 >= pages} onClick={() => onPage(page + 1)} aria-label="Next page">
          <ChevronRight size={16} />
        </button>
        <button type="button" className={navButton} disabled={page + 1 >= pages} onClick={() => onPage(pages - 1)} aria-label="Last page">
          <ChevronsRight size={16} />
        </button>
      </div>
    </nav>
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
            <th className="py-2 px-3 font-medium text-right" title="Length of the video or audio">Length</th>
            <th className="py-2 px-3 font-medium text-right">Size</th>
            <th className="py-2 px-3 font-medium text-right" title="Time the server spent downloading and converting">Download time</th>
            <th className="py-2 px-3 font-medium text-right" title="Time waiting in the queue before starting">Waited</th>
            <th className="py-2 px-3 font-medium">IP</th>
            <th className="py-2 px-3 font-medium">Via</th>
          </tr>
        </thead>
        <tbody>
          {jobs.map((job) => (
            <tr key={job.id} className="border-b border-border-light align-top hover:bg-surface-secondary">
              <td className="py-2 px-3 whitespace-nowrap text-text-secondary tabular-nums">{formatDateTime(job.created_at)}</td>
              <td className="py-2 px-3">
                <span
                  className={`inline-block rounded px-1.5 py-0.5 text-xs ${STATUS_STYLE[job.status] ?? 'bg-info-light text-info-text'}`}
                  title={job.error_message ?? undefined}
                >
                  {job.status}
                </span>
                {job.request_count > 1 && (
                  <span
                    className="ml-1 inline-block rounded px-1.5 py-0.5 text-xs bg-warning-light text-warning-text tabular-nums"
                    title={`${job.request_count} requests shared this download`}
                  >
                    ×{job.request_count}
                  </span>
                )}
                {job.reused_from && (
                  <span
                    className="ml-1 inline-block rounded px-1.5 py-0.5 text-xs bg-surface-tertiary text-text-secondary"
                    title="Served from the cache, without downloading again"
                  >
                    cache
                  </span>
                )}
              </td>
              <td className="py-2 px-3 max-w-xs">
                <a
                  href={job.url}
                  target="_blank"
                  rel="noreferrer noopener"
                  className="text-text-primary hover:text-accent hover:underline break-words line-clamp-2"
                  title={job.title || job.url}
                >
                  {job.title || job.url}
                </a>
                <p className="text-xs text-text-muted line-clamp-2 flex items-center gap-1">
                  <span
                    className="inline-block w-2 h-2 rounded-[2px] shrink-0"
                    style={{ background: PLATFORM_COLORS[job.platform] ?? '#6250d6' }}
                    aria-hidden
                  />
                  {PLATFORM_NAMES[job.platform] ?? job.platform}
                  {job.error_message ? ` · ${job.error_message}` : ''}
                </p>
              </td>
              <td className="py-2 px-3 text-text-secondary">{job.quality ?? '—'}</td>
              <td className="py-2 px-3 text-right tabular-nums text-text-secondary">{formatDuration(job.duration)}</td>
              <td
                className="py-2 px-3 text-right tabular-nums text-text-secondary"
                title={job.estimated_size ? `Estimated before downloading: ${formatBytes(job.estimated_size)}` : undefined}
              >
                {job.file_size ? formatBytes(job.file_size) : job.estimated_size ? `~${formatBytes(job.estimated_size)}` : '—'}
              </td>
              <td className="py-2 px-3 text-right tabular-nums text-text-secondary">{formatDuration(job.elapsed_seconds)}</td>
              <td className="py-2 px-3 text-right tabular-nums text-text-secondary">{formatDuration(job.queued_seconds)}</td>
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

interface Filters {
  status: string;
  platform: string;
  q: string;
  range: HistoryRange;
  bucket: HistoryBucket | null;
}

export default function AdminPage() {
  const [summary, setSummary] = useState<AdminSummary | null>(null);
  const [system, setSystem] = useState<AdminSystem | null>(null);
  const [insights, setInsights] = useState<AdminInsights | null>(null);
  const [jobs, setJobs] = useState<{ total: number; items: AdminJob[] } | null>(null);
  const [filters, setFilters] = useState<Filters>({ status: '', platform: '', q: '', range: '7d', bucket: null });
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(50);
  const [error, setError] = useState<string | null>(null);
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);

  const update = (change: Partial<Filters>) => {
    setPage(0);
    setFilters((f) => ({ ...f, ...change }));
  };

  const load = useCallback(async () => {
    const history = {
      status: filters.status,
      platform: filters.platform,
      q: filters.q,
      range: filters.range,
      since: filters.bucket?.start,
      until: filters.bucket?.end,
    };
    try {
      const [s, sys, ins, j] = await Promise.all([
        adminApi.summary(),
        adminApi.system(24),
        adminApi.insights(history),
        adminApi.jobs({ ...history, limit: pageSize, offset: page * pageSize }),
      ]);
      setSummary(s);
      setSystem(sys);
      setInsights(ins);
      setJobs(j);
      setError(null);
      setUpdatedAt(new Date());
    } catch (e) {
      if (e instanceof UnauthorizedError) return goToLogin();
      setError(e instanceof Error ? e.message : 'Could not load data');
    }
  }, [filters, page, pageSize]);

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
      setFilters((f) => {
        if (f.q === query) return f;
        setPage(0);
        return { ...f, q: query };
      });
    }, 300);
    return () => window.clearTimeout(timer);
  }, [query]);

  const logout = async () => {
    await adminApi.logout().catch(() => undefined);
    goToLogin();
  };

  const now = system?.now;
  const activeChips = [
    filters.q && { label: `“${filters.q}”`, clear: () => setQuery('') },
    filters.status && { label: filters.status, clear: () => update({ status: '' }) },
    filters.platform && { label: PLATFORM_NAMES[filters.platform] ?? filters.platform, clear: () => update({ platform: '' }) },
    filters.bucket && insights && {
      label: bucketRange(filters.bucket, insights.bucket_seconds),
      clear: () => update({ bucket: null }),
    },
  ].filter(Boolean) as { label: string; clear: () => void }[];

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

          {/* Downloads: search, histogram, platforms and the list (like Kibana Discover) */}
          <section className="space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="text-lg font-semibold text-text-primary">Downloads</h2>
              <div className="inline-flex rounded-lg border border-border bg-white p-0.5" role="group" aria-label="Time range">
                {RANGES.map((r) => (
                  <button
                    key={r.value}
                    type="button"
                    className={`px-3 py-1 text-sm rounded-md ${
                      filters.range === r.value ? 'bg-text-primary text-white' : 'text-text-secondary hover:bg-surface-tertiary'
                    }`}
                    onClick={() => update({ range: r.value, bucket: null })}
                    aria-pressed={filters.range === r.value}
                  >
                    {r.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="flex flex-wrap gap-2">
              <label className="relative flex-1 min-w-[16rem]">
                <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" aria-hidden />
                <input
                  className="input-field !py-2 !pl-9"
                  placeholder="Search title, link, IP, key or browser"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  aria-label="Search downloads"
                  type="search"
                />
              </label>
              <select
                className="input-field !py-2 !w-auto"
                value={filters.status}
                onChange={(e) => update({ status: e.target.value })}
                aria-label="Status"
              >
                {STATUSES.map((s) => <option key={s} value={s}>{s || 'Any status'}</option>)}
              </select>
              <select
                className="input-field !py-2 !w-auto"
                value={filters.platform}
                onChange={(e) => update({ platform: e.target.value })}
                aria-label="Platform"
              >
                <option value="">Any platform</option>
                {Object.entries(PLATFORM_NAMES).map(([key, name]) => <option key={key} value={key}>{name}</option>)}
              </select>
            </div>

            {activeChips.length > 0 && (
              <div className="flex flex-wrap items-center gap-2 text-sm">
                {activeChips.map((chip) => (
                  <button
                    key={chip.label}
                    type="button"
                    onClick={chip.clear}
                    className="flex items-center gap-1 rounded-full border border-border bg-white px-3 py-1 text-text-secondary hover:border-border-dark"
                  >
                    {chip.label}
                    <X size={14} aria-label="Remove filter" />
                  </button>
                ))}
              </div>
            )}

            <div className="grid gap-3 lg:grid-cols-3">
              <div className="lg:col-span-2">
                <Panel
                  title={insights ? `${insights.total} downloads over time` : 'Downloads over time'}
                  actions={filters.bucket && (
                    <button type="button" className="text-xs text-accent hover:underline" onClick={() => update({ bucket: null })}>
                      Show the whole range
                    </button>
                  )}
                >
                  {insights ? (
                    <HistoryHistogram
                      buckets={insights.buckets}
                      bucketSeconds={insights.bucket_seconds}
                      selected={filters.bucket?.start ?? null}
                      onSelect={(bucket) => update({ bucket })}
                    />
                  ) : (
                    <p className="py-16 text-center text-sm text-text-muted">Loading…</p>
                  )}
                </Panel>
              </div>
              <Panel title="By platform">
                {insights ? (
                  <PlatformDonut slices={insights.platforms} selected={filters.platform} onSelect={(platform) => update({ platform })} />
                ) : (
                  <p className="py-16 text-center text-sm text-text-muted">Loading…</p>
                )}
              </Panel>
            </div>

            <div className="rounded-lg border border-border bg-white px-4 py-2">
              {jobs ? <JobsTable jobs={jobs.items} /> : <p className="py-8 text-center text-sm text-text-muted">Loading…</p>}
            </div>
            {jobs && (
              <Pagination
                page={page}
                pageSize={pageSize}
                total={jobs.total}
                onPage={setPage}
                onPageSize={(size) => {
                  setPage(0);
                  setPageSize(size);
                }}
              />
            )}
          </section>

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
              <Panel title="Top IPs, last 7 days">
                {summary.top_ips_7d.length === 0 ? (
                  <p className="text-sm text-text-muted">No IPs recorded yet (recorded from v0.12.0 on).</p>
                ) : (
                  <table className="w-full text-sm">
                    <tbody>
                      {summary.top_ips_7d.map((row) => (
                        <tr key={row.ip} className="border-b border-border-light last:border-0">
                          <td className="py-1.5">
                            <button
                              type="button"
                              className="tabular-nums hover:text-accent hover:underline"
                              onClick={() => {
                                setQuery(row.ip);
                                window.scrollTo({ top: 0, behavior: 'smooth' });
                              }}
                            >
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
              </Panel>
            </section>
          )}
        </div>
      </main>

      <footer className="py-6 px-4 text-center text-xs text-text-muted">
        <a href="/status" className="hover:text-accent">status</a> • v{packageJson.version}
      </footer>
    </div>
  );
}
