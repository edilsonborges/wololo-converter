import type { FC } from 'react';
import type { JobProgressUpdate, JobStatus } from '../types';
import { Icon } from './Icon';

interface ProgressCardProps {
  progress: JobProgressUpdate;
  onCancel: () => void;
  onDownload: () => void;
  downloadUrl: string;
}

const STATUS_DISPLAY: Record<JobStatus, { label: string; color: string }> = {
  queued: { label: 'Queued', color: 'text-text-muted' },
  validating: { label: 'Validating URL...', color: 'text-info-text' },
  downloading: { label: 'Downloading...', color: 'text-info-text' },
  converting: { label: 'Converting...', color: 'text-accent' },
  finalizing: { label: 'Finalizing...', color: 'text-warning-text' },
  completed: { label: 'Completed!', color: 'text-success-text' },
  failed: { label: 'Failed', color: 'text-error-text' },
  cancelled: { label: 'Cancelled', color: 'text-text-muted' },
};

export const ProgressCard: FC<ProgressCardProps> = ({
  progress,
  onCancel,
  onDownload,
  downloadUrl,
}) => {
  const statusInfo = STATUS_DISPLAY[progress.status] || STATUS_DISPLAY.queued;
  const isActive = ['queued', 'validating', 'downloading', 'converting', 'finalizing'].includes(
    progress.status
  );
  const isComplete = progress.status === 'completed';
  const isFailed = progress.status === 'failed';

  return (
    <div className="card">
      {/* Title and status */}
      <div className="flex items-start justify-between mb-4">
        <div className="flex-1 min-w-0">
          <h3 className="text-lg font-semibold text-text-primary truncate">
            {progress.title || 'Processing...'}
          </h3>
          <div className={`text-sm ${statusInfo.color} mt-1`}>
            {progress.current_stage || statusInfo.label}
          </div>
        </div>

        {/* Cancel button for active downloads */}
        {isActive && (
          <button
            onClick={onCancel}
            className="ml-4 p-2 text-text-muted hover:text-error hover:bg-error-light rounded-lg transition-colors"
            title="Cancel download"
          >
            <Icon name="x" size="sm" />
          </button>
        )}
      </div>

      {/* Progress bar */}
      <div className="mb-4">
        <div className="flex justify-between text-sm text-text-muted mb-2">
          <span>{Math.round(progress.progress)}%</span>
          <div className="flex items-center gap-4">
            {progress.speed && <span>{progress.speed}</span>}
            {progress.eta && <span>ETA: {progress.eta}</span>}
          </div>
        </div>
        <div className="relative h-3 bg-surface-tertiary rounded-full overflow-hidden">
          <div
            className={`h-full transition-all duration-300 ease-out rounded-full ${
              isComplete
                ? 'bg-success'
                : isFailed
                ? 'bg-error'
                : 'bg-accent'
            }`}
            style={{ width: `${progress.progress}%` }}
          >
            {isActive && <div className="progress-bar-shine" />}
          </div>
        </div>
      </div>

      {/* Error message */}
      {isFailed && progress.error_message && (
        <div className="mb-4 p-3 bg-error-light border border-error/20 rounded-lg">
          <p className="text-error-text text-sm">{progress.error_message}</p>
        </div>
      )}

      {/* Download buttons */}
      {isComplete && (
        <div className="flex gap-3">
          <button
            onClick={onDownload}
            className="btn-primary flex-1 flex items-center justify-center gap-2"
          >
            <Icon name="download" size="sm" />
            Download File
          </button>
          <a
            href={downloadUrl}
            download
            className="btn-secondary flex items-center justify-center gap-2 px-4"
            title="Direct download link"
          >
            <Icon name="externalLink" size="sm" />
          </a>
        </div>
      )}
    </div>
  );
};
