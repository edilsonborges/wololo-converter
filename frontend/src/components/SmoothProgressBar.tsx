import type { FC } from 'react';
import { useSmoothedProgress } from '../hooks/useSmoothedProgress';

interface SmoothProgressBarProps {
  progress: number;
  isActive: boolean;
  speed?: string;
  eta?: string;
  barClassName?: string;
  heightClass?: string;
  textSizeClass?: string;
  isComplete?: boolean;
  isFailed?: boolean;
}

export const SmoothProgressBar: FC<SmoothProgressBarProps> = ({
  progress,
  isActive,
  speed,
  eta,
  barClassName = 'bg-accent',
  heightClass = 'h-2',
  textSizeClass = 'text-xs',
  isComplete = false,
  isFailed = false,
}) => {
  const smoothed = useSmoothedProgress(progress, isActive);

  const barColor = isComplete
    ? 'bg-success'
    : isFailed
    ? 'bg-error'
    : barClassName;

  return (
    <div>
      <div className={`flex justify-between ${textSizeClass} text-text-muted mb-1`}>
        <span>{Math.round(smoothed)}%</span>
        <div className="flex items-center gap-2">
          {speed && <span>{speed}</span>}
          {eta && <span>ETA: {eta}</span>}
        </div>
      </div>
      <div className={`${heightClass} bg-border rounded-full overflow-hidden`}>
        <div
          className={`h-full ${barColor} transition-all duration-300 ease-out rounded-full`}
          style={{ width: `${smoothed}%` }}
        />
      </div>
    </div>
  );
};
