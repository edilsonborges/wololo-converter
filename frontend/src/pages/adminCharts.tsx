/**
 * Charts for the admin view, in plain SVG.
 *
 * Platform colors follow the entity (YouTube is always slot 1), never its
 * rank, so filtering never repaints a platform. Status colors are reserved
 * for job state and always come with a text label.
 */
import { useRef, useState } from 'react';
import type { HistoryBucket } from '../adminApi';

// Categorical slots in validated order (blue, orange, aqua, yellow, magenta,
// green, violet); each platform owns one slot.
export const PLATFORM_COLORS: Record<string, string> = {
  youtube: '#2a78d6',
  instagram: '#eb6834',
  tiktok: '#1baf7a',
  twitter: '#eda100',
  threads: '#e87ba4',
  facebook: '#008300',
};
const OTHER_COLOR = '#6250d6';

export const PLATFORM_NAMES: Record<string, string> = {
  youtube: 'YouTube',
  instagram: 'Instagram',
  tiktok: 'TikTok',
  twitter: 'Twitter/X',
  threads: 'Threads',
  facebook: 'Facebook',
};

export const STATUS_SERIES = [
  { key: 'completed', label: 'Completed', color: '#10B981' },
  { key: 'failed', label: 'Failed', color: '#EF4444' },
  { key: 'cancelled', label: 'Cancelled or cut by a restart', color: '#B5B5B5' },
  { key: 'other', label: 'In progress', color: '#2563EB' },
] as const;

type StatusKey = (typeof STATUS_SERIES)[number]['key'];

function platformColor(platform: string): string {
  return PLATFORM_COLORS[platform] ?? OTHER_COLOR;
}

function platformName(platform: string): string {
  return PLATFORM_NAMES[platform] ?? platform;
}

// ------------------------------------------------------------------ donut

interface Slice {
  platform: string;
  count: number;
}

function arcPath(cx: number, cy: number, outer: number, inner: number, start: number, end: number): string {
  // A full circle can't be drawn as one arc; split it
  if (end - start >= Math.PI * 2 - 1e-6) end = start + Math.PI * 2 - 1e-4;
  const large = end - start > Math.PI ? 1 : 0;
  const p = (r: number, a: number) => `${cx + r * Math.sin(a)},${cy - r * Math.cos(a)}`;
  return [
    `M${p(outer, start)}`,
    `A${outer},${outer} 0 ${large} 1 ${p(outer, end)}`,
    `L${p(inner, end)}`,
    `A${inner},${inner} 0 ${large} 0 ${p(inner, start)}`,
    'Z',
  ].join(' ');
}

export function PlatformDonut({
  slices,
  selected,
  onSelect,
}: {
  slices: Slice[];
  selected: string;
  onSelect: (platform: string) => void;
}) {
  const [hover, setHover] = useState<string | null>(null);
  const total = slices.reduce((sum, s) => sum + s.count, 0);
  const size = 180;
  const center = size / 2;
  const focus = hover ? slices.find((s) => s.platform === hover) : null;

  let angle = 0;
  const arcs = slices.map((slice) => {
    const start = angle;
    angle += total ? (slice.count / total) * Math.PI * 2 : 0;
    return { ...slice, start, end: angle };
  });

  if (total === 0) {
    return <p className="py-12 text-center text-sm text-text-muted">No downloads in this range.</p>;
  }

  return (
    <div className="flex flex-col sm:flex-row lg:flex-col xl:flex-row items-center gap-4">
      <svg viewBox={`0 0 ${size} ${size}`} className="w-40 h-40 shrink-0" role="img" aria-label="Downloads by platform">
        {arcs.map((arc) => (
          <path
            key={arc.platform}
            d={arcPath(center, center, 86, 54, arc.start, arc.end)}
            fill={platformColor(arc.platform)}
            stroke="#FFFFFF"
            strokeWidth={2}
            opacity={(hover && hover !== arc.platform) || (selected && selected !== arc.platform) ? 0.35 : 1}
            className="cursor-pointer transition-opacity"
            onMouseEnter={() => setHover(arc.platform)}
            onMouseLeave={() => setHover(null)}
            onClick={() => onSelect(selected === arc.platform ? '' : arc.platform)}
          >
            <title>{`${platformName(arc.platform)}: ${arc.count} (${((arc.count / total) * 100).toFixed(1)}%)`}</title>
          </path>
        ))}
        <text x={center} y={center - 4} textAnchor="middle" className="fill-text-primary" fontSize="22" fontWeight="600">
          {focus ? focus.count : total}
        </text>
        <text x={center} y={center + 16} textAnchor="middle" className="fill-text-tertiary" fontSize="11">
          {focus ? platformName(focus.platform) : 'downloads'}
        </text>
      </svg>
      <ul className="w-full space-y-1 text-sm" aria-label="Platforms">
        {slices.map((slice) => (
          <li key={slice.platform}>
            <button
              type="button"
              className={`w-full flex items-center gap-2 rounded px-2 py-1 text-left hover:bg-surface-tertiary ${
                selected === slice.platform ? 'bg-surface-tertiary' : ''
              }`}
              onMouseEnter={() => setHover(slice.platform)}
              onMouseLeave={() => setHover(null)}
              onClick={() => onSelect(selected === slice.platform ? '' : slice.platform)}
              aria-pressed={selected === slice.platform}
            >
              <span className="w-3 h-3 rounded-[3px] shrink-0" style={{ background: platformColor(slice.platform) }} aria-hidden />
              <span className="flex-1 text-text-primary">{platformName(slice.platform)}</span>
              <span className="tabular-nums text-text-secondary">{slice.count}</span>
              <span className="tabular-nums text-text-muted w-12 text-right">{((slice.count / total) * 100).toFixed(0)}%</span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

// ------------------------------------------------------------------ histogram

function bucketLabel(bucket: HistoryBucket, bucketSeconds: number, withDate = true): string {
  const start = new Date(bucket.start);
  if (bucketSeconds >= 86400) {
    return start.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
  }
  const time = start.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
  return withDate ? `${start.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })} ${time}` : time;
}

function bucketRange(bucket: HistoryBucket, bucketSeconds: number): string {
  if (bucketSeconds >= 86400) {
    return new Date(bucket.start).toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' });
  }
  const end = new Date(bucket.end).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
  return `${bucketLabel(bucket, bucketSeconds)} – ${end}`;
}

function niceMax(value: number): number {
  if (value <= 4) return Math.max(1, value);
  const magnitude = 10 ** Math.floor(Math.log10(value));
  const step = [1, 2, 2.5, 5, 10].find((m) => m * magnitude >= value / 4)! * magnitude;
  return Math.ceil(value / step) * step;
}

/**
 * Downloads over time, stacked by status (like Kibana Discover's histogram).
 * Clicking a bar narrows the list below to that time slot.
 */
export function HistoryHistogram({
  buckets,
  bucketSeconds,
  selected,
  onSelect,
}: {
  buckets: HistoryBucket[];
  bucketSeconds: number;
  selected: string | null;
  onSelect: (bucket: HistoryBucket | null) => void;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const wrapper = useRef<HTMLDivElement>(null);
  const width = 720;
  const height = 180;
  const pad = { top: 10, right: 8, bottom: 22, left: 34 };
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;

  const totals = buckets.map((b) => STATUS_SERIES.reduce((sum, s) => sum + b[s.key as StatusKey], 0));
  const max = niceMax(Math.max(0, ...totals));
  const slot = plotW / Math.max(1, buckets.length);
  const barW = Math.max(1, Math.min(28, slot - 2));
  const y = (v: number) => pad.top + plotH - (v / max) * plotH;
  const ticks = [0, max / 2, max];
  const labelEvery = Math.max(1, Math.ceil(buckets.length / 8));
  const hovered = hover !== null ? buckets[hover] : null;

  return (
    <div ref={wrapper} className="relative">
      <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-text-tertiary mb-2" aria-label="Legend">
        {STATUS_SERIES.map((s) => (
          <li key={s.key} className="flex items-center gap-1.5">
            <span className="w-3 h-3 rounded-[3px]" style={{ background: s.color }} aria-hidden />
            {s.label}
          </li>
        ))}
      </ul>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="w-full h-48"
        preserveAspectRatio="none"
        role="img"
        aria-label={`Downloads over time, ${buckets.length} bars`}
        onMouseLeave={() => setHover(null)}
      >
        {ticks.map((t) => (
          <g key={t}>
            <line x1={pad.left} x2={width - pad.right} y1={y(t)} y2={y(t)} stroke="#F0F0F0" vectorEffect="non-scaling-stroke" />
            <text x={pad.left - 6} y={y(t) + 4} textAnchor="end" fontSize="11" className="fill-text-muted">
              {Number.isInteger(t) ? t : t.toFixed(1)}
            </text>
          </g>
        ))}
        {buckets.map((bucket, i) => {
          const x = pad.left + i * slot + (slot - barW) / 2;
          let base = 0;
          const isSelected = selected === bucket.start;
          // Only a clicked bar dims the others; hover just shades its column
          const dim = selected !== null && !isSelected;
          const segments = STATUS_SERIES.filter((s) => bucket[s.key as StatusKey] > 0);
          return (
            <g key={bucket.start} opacity={dim ? 0.45 : 1}>
              {/* Hit target: the whole column, bigger than the bar */}
              <rect
                x={pad.left + i * slot}
                y={pad.top}
                width={slot}
                height={plotH}
                fill={hover === i ? '#F5F5F5' : 'transparent'}
                className="cursor-pointer"
                onMouseEnter={() => setHover(i)}
                onClick={() => onSelect(isSelected ? null : bucket)}
              />
              {segments.map((s, index) => {
                const value = bucket[s.key as StatusKey];
                const top = y(base + value);
                const h = y(base) - top;
                base += value;
                const isTop = index === segments.length - 1;
                // 2px surface gap between stacked segments
                const gap = index > 0 ? 2 : 0;
                return (
                  <rect
                    key={s.key}
                    x={x}
                    y={top}
                    width={barW}
                    height={Math.max(0, h - gap)}
                    rx={isTop ? Math.min(4, barW / 2) : 0}
                    fill={s.color}
                    pointerEvents="none"
                  />
                );
              })}
            </g>
          );
        })}
        {buckets.map((bucket, i) =>
          i % labelEvery === 0 ? (
            <text
              key={`label-${bucket.start}`}
              x={pad.left + i * slot + slot / 2}
              y={height - 6}
              textAnchor="middle"
              fontSize="11"
              className="fill-text-muted"
            >
              {bucketLabel(bucket, bucketSeconds, false)}
            </text>
          ) : null,
        )}
      </svg>
      {hovered && hover !== null && (
        <div
          className="absolute z-10 top-6 w-52 rounded-lg border border-border bg-white px-3 py-2 shadow-lg text-sm pointer-events-none"
          style={{
            left: `clamp(0px, calc(${((pad.left + hover * slot + slot / 2) / width) * 100}% - 6.5rem), calc(100% - 13rem))`,
          }}
        >
          <p className="font-medium text-text-primary">{bucketRange(hovered, bucketSeconds)}</p>
          <ul className="mt-1 space-y-0.5">
            {STATUS_SERIES.map((s) => (
              <li key={s.key} className="flex items-center gap-2 text-text-secondary">
                <span className="w-2.5 h-2.5 rounded-[2px]" style={{ background: s.color }} aria-hidden />
                <span className="flex-1">{s.label}</span>
                <span className="tabular-nums">{hovered[s.key as StatusKey]}</span>
              </li>
            ))}
          </ul>
          <p className="mt-1 text-xs text-text-muted">Click to list only this slot</p>
        </div>
      )}
    </div>
  );
}

export { bucketRange };
