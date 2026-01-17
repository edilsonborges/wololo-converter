import type { FC } from 'react';
import type { JobProgressUpdate, JobStatus } from '../types';

interface ProgressCardProps {
  progress: JobProgressUpdate;
  onCancel: () => void;
  onDownload: () => void;
  downloadUrl: string;
}

const STATUS_DISPLAY: Record<JobStatus, { label: string; color: string }> = {
  queued: { label: 'Queued', color: 'text-gray-400' },
  validating: { label: 'Validating URL...', color: 'text-blue-400' },
  downloading: { label: 'Downloading...', color: 'text-blue-400' },
  converting: { label: 'Converting...', color: 'text-purple-400' },
  finalizing: { label: 'Finalizing...', color: 'text-orange-400' },
  completed: { label: 'Completed!', color: 'text-green-400' },
  failed: { label: 'Failed', color: 'text-red-400' },
  cancelled: { label: 'Cancelled', color: 'text-gray-400' },
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
          <h3 className="text-lg font-semibold text-white truncate">
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
            className="ml-4 p-2 text-gray-400 hover:text-red-400 hover:bg-red-400/10 rounded-lg transition-colors"
            title="Cancel download"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="h-5 w-5"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M6 18L18 6M6 6l12 12"
              />
            </svg>
          </button>
        )}
      </div>

      {/* Progress bar */}
      <div className="mb-4">
        <div className="flex justify-between text-sm text-gray-400 mb-2">
          <span>{Math.round(progress.progress)}%</span>
          <div className="flex items-center gap-4">
            {progress.speed && <span>{progress.speed}</span>}
            {progress.eta && <span>ETA: {progress.eta}</span>}
          </div>
        </div>
        <div className="relative h-3 bg-gray-700 rounded-full overflow-hidden">
          <div
            className={`h-full transition-all duration-300 ease-out rounded-full ${
              isComplete
                ? 'bg-green-500'
                : isFailed
                ? 'bg-red-500'
                : 'bg-gradient-to-r from-red-500 via-orange-500 to-yellow-500'
            }`}
            style={{ width: `${progress.progress}%` }}
          >
            {isActive && <div className="progress-bar-shine" />}
          </div>
        </div>
      </div>

      {/* Error message */}
      {isFailed && progress.error_message && (
        <div className="mb-4 p-3 bg-red-500/10 border border-red-500/30 rounded-lg">
          <p className="text-red-400 text-sm">{progress.error_message}</p>
        </div>
      )}

      {/* Download buttons */}
      {isComplete && (
        <div className="flex gap-3">
          <button
            onClick={onDownload}
            className="btn-primary flex-1 flex items-center justify-center gap-2"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="h-5 w-5"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
              />
            </svg>
            Download File
          </button>
          <a
            href={downloadUrl}
            download
            className="btn-secondary flex items-center justify-center gap-2 px-4"
            title="Direct download link"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="h-5 w-5"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"
              />
            </svg>
          </a>
        </div>
      )}
    </div>
  );
};
