import { useEffect, useState } from 'react';
import { AlertTriangle, CheckCircle2, HelpCircle, XCircle } from 'lucide-react';
import { statusApi, type ComponentState, type StatusComponent, type StatusDay, type StatusResponse } from '../adminApi';
import packageJson from '../../package.json';

const REFRESH_MS = 60_000;

// Status colors are reserved for state and always ship with an icon + label
export const STATE_META: Record<ComponentState, { label: string; bar: string; text: string; Icon: typeof CheckCircle2 }> = {
  operational: { label: 'Operational', bar: 'bg-success', text: 'text-success-text', Icon: CheckCircle2 },
  degraded: { label: 'Degraded', bar: 'bg-warning', text: 'text-warning-text', Icon: AlertTriangle },
  outage: { label: 'Outage', bar: 'bg-error', text: 'text-error-text', Icon: XCircle },
  no_data: { label: 'No data', bar: 'bg-border', text: 'text-text-muted', Icon: HelpCircle },
};

const BANNER: Record<StatusResponse['status'], { title: string; className: string }> = {
  operational: { title: 'All systems operational', className: 'bg-success-light border-success/30 text-success-text' },
  degraded: { title: 'Some systems are degraded', className: 'bg-warning-light border-warning/30 text-warning-text' },
  outage: { title: 'Some systems are down', className: 'bg-error-light border-error/30 text-error-text' },
};

function formatDay(date: string): string {
  return new Date(`${date}T00:00:00`).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}

function dayDetail(day: StatusDay): string {
  if (day.status === 'no_data') {
    return 'No data';
  }
  if (day.estimated) {
    return day.uptime !== null ? `~${day.uptime.toFixed(2)}% uptime (estimated)` : 'Up (estimated)';
  }
  return `${day.uptime?.toFixed(2)}% uptime`;
}

function UptimeBars({ component, visibleDays }: { component: StatusComponent; visibleDays: number }) {
  const [active, setActive] = useState<number | null>(null);
  const days = component.days.slice(-visibleDays);
  const hovered = active !== null ? days[active] : null;

  return (
    <div className="relative">
      <div
        className="flex items-end gap-[2px] h-9"
        onMouseLeave={() => setActive(null)}
        role="list"
        aria-label={`${component.name}, last ${visibleDays} days`}
      >
        {days.map((day, index) => {
          const meta = STATE_META[day.status];
          return (
            <button
              key={day.date}
              type="button"
              role="listitem"
              className="flex-1 h-full py-0 focus:outline-none group"
              onMouseEnter={() => setActive(index)}
              onFocus={() => setActive(index)}
              onBlur={() => setActive(null)}
              onClick={() => setActive(active === index ? null : index)}
              aria-label={`${formatDay(day.date)}: ${meta.label}. ${dayDetail(day)}`}
            >
              <span
                className={`block w-full h-full rounded-[2px] ${meta.bar} ${
                  active === index ? 'opacity-70' : 'group-hover:opacity-70'
                }`}
              />
            </button>
          );
        })}
      </div>
      {hovered && active !== null && (
        <div
          className="absolute z-10 top-11 w-64 -translate-x-1/2 rounded-lg border border-border bg-white px-3 py-2 shadow-lg text-sm pointer-events-none"
          style={{ left: `clamp(8rem, ${((active + 0.5) / days.length) * 100}%, calc(100% - 8rem))` }}
        >
          <p className="font-medium text-text-primary">{formatDay(hovered.date)}</p>
          <p className={`mt-1 flex items-center gap-1.5 ${STATE_META[hovered.status].text}`}>
            {(() => {
              const { Icon } = STATE_META[hovered.status];
              return <Icon size={14} aria-hidden />;
            })()}
            {STATE_META[hovered.status].label}
          </p>
          <p className="text-text-tertiary">{dayDetail(hovered)}</p>
          {hovered.note && <p className="mt-1 text-xs text-text-muted">{hovered.note}</p>}
        </div>
      )}
      <div className="mt-2 flex justify-between text-xs text-text-muted">
        <span>{visibleDays} days ago</span>
        <span>
          {component.uptime !== null
            ? `${component.uptime.toFixed(2)}% uptime`
            : 'No data yet'}
        </span>
        <span>Today</span>
      </div>
    </div>
  );
}

function ComponentRow({ component, visibleDays }: { component: StatusComponent; visibleDays: number }) {
  const meta = STATE_META[component.status];
  return (
    <div className="py-5 border-b border-border-light last:border-b-0">
      <div className="flex items-center justify-between mb-3 gap-3">
        <h3 className="font-medium text-text-primary">
          {component.name}
          {component.latency_ms !== null && (
            <span className="ml-2 text-xs font-normal text-text-muted">{component.latency_ms} ms</span>
          )}
        </h3>
        <span className={`flex items-center gap-1.5 text-sm ${meta.text}`}>
          <meta.Icon size={16} aria-hidden />
          {meta.label}
        </span>
      </div>
      <UptimeBars component={component} visibleDays={visibleDays} />
    </div>
  );
}

function useVisibleDays(total: number): number {
  const query = '(min-width: 640px)';
  const [wide, setWide] = useState(() => typeof window === 'undefined' || window.matchMedia?.(query).matches !== false);
  useEffect(() => {
    const media = window.matchMedia?.(query);
    if (!media) return;
    const update = () => setWide(media.matches);
    media.addEventListener('change', update);
    return () => media.removeEventListener('change', update);
  }, []);
  return wide ? total : Math.min(total, 30);
}

export default function StatusPage() {
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const visibleDays = useVisibleDays(status?.days ?? 90);

  useEffect(() => {
    document.title = 'Status · Wololo Converter';
    let cancelled = false;
    const load = () =>
      statusApi
        .get()
        .then((data) => {
          if (!cancelled) {
            setStatus(data);
            setError(null);
          }
        })
        .catch(() => {
          if (!cancelled) setError('Could not reach the Wololo API.');
        });
    load();
    const timer = window.setInterval(load, REFRESH_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  return (
    <div className="min-h-screen bg-white">
      <header className="py-6 px-4 border-b border-border-light">
        <div className="max-w-3xl mx-auto flex items-center justify-between">
          <a href="/" className="flex items-center gap-3 text-text-primary">
            <img src="/wololo-left.png" alt="" className="w-10 h-10 object-contain" />
            <span className="text-xl font-semibold tracking-tight">Wololo Converter</span>
          </a>
          <span className="text-sm text-text-muted">Status</span>
        </div>
      </header>

      <main className="px-4 py-8">
        <div className="max-w-3xl mx-auto space-y-8">
          {error && !status && (
            <div className="rounded-lg border border-error/30 bg-error-light px-5 py-4 text-error-text flex items-center gap-2">
              <XCircle size={20} aria-hidden />
              {error}
            </div>
          )}
          {!status && !error && <p className="text-text-muted">Loading status…</p>}

          {status && (
            <>
              <div className={`rounded-lg border px-5 py-4 flex items-center gap-3 ${BANNER[status.status].className}`}>
                {(() => {
                  const { Icon } = STATE_META[status.status];
                  return <Icon size={22} aria-hidden />;
                })()}
                <div>
                  <p className="font-semibold">{BANNER[status.status].title}</p>
                  <p className="text-xs opacity-80">
                    Updated {new Date(status.generated_at).toLocaleTimeString()}
                    {error ? ' · could not refresh' : ''}
                  </p>
                </div>
              </div>

              <section>
                <div className="card !py-0">
                  {status.components.map((component) => (
                    <ComponentRow key={component.id} component={component} visibleDays={visibleDays} />
                  ))}
                </div>
              </section>

              <ul className="flex flex-wrap gap-x-5 gap-y-2 text-xs text-text-tertiary" aria-label="Legend">
                {(Object.keys(STATE_META) as ComponentState[]).map((state) => (
                  <li key={state} className="flex items-center gap-1.5">
                    <span className={`inline-block w-3 h-3 rounded-[2px] ${STATE_META[state].bar}`} aria-hidden />
                    {STATE_META[state].label}
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      </main>

      <footer className="py-6 px-4 text-center text-xs text-text-muted border-t border-border-light">
        <a href="/" className="hover:text-accent">
          Wololo Converter • v{packageJson.version}
        </a>
      </footer>
    </div>
  );
}
