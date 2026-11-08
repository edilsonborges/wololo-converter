import { useEffect, useState, type FC } from 'react';
import { formatElapsed } from '../elapsed';
import { Icon } from './Icon';

interface ElapsedTimeProps {
  startedAt: number;
  /** When set, shows the final duration; otherwise ticks live every second. */
  endedAt?: number;
  label?: string;
}

export const ElapsedTime: FC<ElapsedTimeProps> = ({ startedAt, endedAt, label }) => {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (endedAt !== undefined) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [endedAt]);

  const elapsed = (endedAt ?? now) - startedAt;

  return (
    <span
      className="inline-flex items-center gap-1 text-xs text-text-muted tabular-nums"
      title={endedAt !== undefined ? 'Total processing time' : 'Elapsed time'}
      data-testid="elapsed-time"
    >
      <Icon name="clock" size="xs" />
      {label ? `${label} ` : ''}
      {formatElapsed(elapsed)}
    </span>
  );
};
