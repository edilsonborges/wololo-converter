import { useState, useCallback, useRef, type FC, type DragEvent } from 'react';
import type { QueueItem, QueueConfig, QueueProcessingMode, JobStatus } from '../types';
import { PLATFORMS } from '../types';
import { Icon, PlatformIcon } from './Icon';

interface QueueManagerProps {
  items: QueueItem[];
  config: QueueConfig;
  onConfigChange: (config: QueueConfig) => void;
  onReorder: (fromIndex: number, toIndex: number) => void;
  onRemove: (id: string) => void;
  onCancel: (id: string) => void;
  onRetry: (id: string) => void;
  onDownload: (jobId: string) => void;
  onClearCompleted: () => void;
}

const STATUS_STYLES: Record<string, { bg: string; text: string; label: string }> = {
  pending: { bg: 'bg-surface-tertiary', text: 'text-text-secondary', label: 'Pending' },
  active: { bg: 'bg-info-light', text: 'text-info-text', label: 'Downloading' },
  completed: { bg: 'bg-success-light', text: 'text-success-text', label: 'Completed' },
  failed: { bg: 'bg-error-light', text: 'text-error-text', label: 'Failed' },
  cancelled: { bg: 'bg-surface-tertiary', text: 'text-text-muted', label: 'Cancelled' },
};

const JOB_STATUS_MAP: Record<JobStatus, string> = {
  queued: 'Queued',
  validating: 'Validating...',
  downloading: 'Downloading...',
  converting: 'Converting...',
  finalizing: 'Finalizing...',
  completed: 'Completed',
  failed: 'Failed',
  cancelled: 'Cancelled',
};

export const QueueManager: FC<QueueManagerProps> = ({
  items,
  config,
  onConfigChange,
  onReorder,
  onRemove,
  onCancel,
  onRetry,
  onDownload,
  onClearCompleted,
}) => {
  const [draggedIndex, setDraggedIndex] = useState<number | null>(null);
  const [dragOverIndex, setDragOverIndex] = useState<number | null>(null);
  const dragNodeRef = useRef<HTMLDivElement | null>(null);

  const pendingItems = items.filter((i) => i.status === 'pending');
  const activeItems = items.filter((i) => i.status === 'active');
  const completedItems = items.filter((i) => i.status === 'completed' || i.status === 'failed' || i.status === 'cancelled');

  const handleDragStart = useCallback((e: DragEvent<HTMLDivElement>, index: number) => {
    setDraggedIndex(index);
    dragNodeRef.current = e.currentTarget;
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', String(index));

    // Add dragging class after a brief delay to allow the drag image to be captured
    setTimeout(() => {
      if (dragNodeRef.current) {
        dragNodeRef.current.classList.add('opacity-50');
      }
    }, 0);
  }, []);

  const handleDragEnd = useCallback(() => {
    if (dragNodeRef.current) {
      dragNodeRef.current.classList.remove('opacity-50');
    }
    setDraggedIndex(null);
    setDragOverIndex(null);
    dragNodeRef.current = null;
  }, []);

  const handleDragOver = useCallback((e: DragEvent<HTMLDivElement>, index: number) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';

    if (draggedIndex !== null && draggedIndex !== index) {
      setDragOverIndex(index);
    }
  }, [draggedIndex]);

  const handleDragLeave = useCallback(() => {
    setDragOverIndex(null);
  }, []);

  const handleDrop = useCallback((e: DragEvent<HTMLDivElement>, toIndex: number) => {
    e.preventDefault();
    const fromIndex = draggedIndex;

    if (fromIndex !== null && fromIndex !== toIndex) {
      // Only allow reordering of pending items
      const fromItem = items[fromIndex];
      const toItem = items[toIndex];

      if (fromItem.status === 'pending' && toItem.status === 'pending') {
        onReorder(fromIndex, toIndex);
      }
    }

    handleDragEnd();
  }, [draggedIndex, items, onReorder, handleDragEnd]);

  const handleModeChange = useCallback((mode: QueueProcessingMode) => {
    onConfigChange({ ...config, processingMode: mode });
  }, [config, onConfigChange]);

  const handleConcurrentChange = useCallback((value: number) => {
    onConfigChange({ ...config, maxConcurrent: Math.max(1, Math.min(5, value)) });
  }, [config, onConfigChange]);

  const renderQueueItem = (item: QueueItem, index: number, isDraggable: boolean) => {
    const statusStyle = STATUS_STYLES[item.status] || STATUS_STYLES.pending;
    const platformInfo = item.platform ? PLATFORMS[item.platform] : null;
    const progress = item.progress;
    const showProgress = item.status === 'active' && progress;

    return (
      <div
        key={item.id}
        draggable={isDraggable && item.status === 'pending'}
        onDragStart={(e) => handleDragStart(e, index)}
        onDragEnd={handleDragEnd}
        onDragOver={(e) => handleDragOver(e, index)}
        onDragLeave={handleDragLeave}
        onDrop={(e) => handleDrop(e, index)}
        className={`
          relative p-3 rounded-lg bg-surface-secondary border border-border-light
          ${isDraggable && item.status === 'pending' ? 'cursor-grab active:cursor-grabbing' : ''}
          ${dragOverIndex === index ? 'border-accent border-2' : ''}
          transition-all duration-200
        `}
      >
        <div className="flex items-start gap-3">
          {/* Drag handle for pending items */}
          {isDraggable && item.status === 'pending' && (
            <div className="flex-shrink-0 text-text-muted mt-1">
              <Icon name="gripHorizontal" size="sm" />
            </div>
          )}

          {/* Platform icon */}
          <div className={`flex-shrink-0 ${platformInfo?.color || 'text-text-muted'}`}>
            <PlatformIcon platform={item.platform || ''} size="md" />
          </div>

          {/* Content */}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <span className={`text-xs px-2 py-0.5 rounded-full ${statusStyle.bg} ${statusStyle.text}`}>
                {progress ? JOB_STATUS_MAP[progress.status] || statusStyle.label : statusStyle.label}
              </span>
              {item.progress?.title && (
                <span className="text-sm text-text-primary font-medium truncate">
                  {item.progress.title}
                </span>
              )}
            </div>
            <div className="text-sm text-text-muted truncate">
              {item.url}
            </div>

            {/* Progress bar for active items */}
            {showProgress && (
              <div className="mt-2">
                <div className="flex justify-between text-xs text-text-muted mb-1">
                  <span>{Math.round(progress.progress)}%</span>
                  <div className="flex items-center gap-2">
                    {progress.speed && <span>{progress.speed}</span>}
                    {progress.eta && <span>ETA: {progress.eta}</span>}
                  </div>
                </div>
                <div className="h-2 bg-border rounded-full overflow-hidden">
                  <div
                    className="h-full bg-accent transition-all duration-300"
                    style={{ width: `${progress.progress}%` }}
                  />
                </div>
              </div>
            )}

            {/* Error message for failed items */}
            {item.status === 'failed' && item.error && (
              <div className="mt-2 text-xs text-error-text">
                {item.error}
              </div>
            )}
          </div>

          {/* Actions */}
          <div className="flex-shrink-0 flex items-center gap-1">
            {/* Download button for completed items */}
            {item.status === 'completed' && item.jobId && (
              <button
                onClick={() => onDownload(item.jobId!)}
                className="p-1.5 text-success hover:bg-success-light rounded transition-colors"
                title="Download file"
              >
                <Icon name="download" size="sm" />
              </button>
            )}

            {/* Retry button for failed items */}
            {item.status === 'failed' && (
              <button
                onClick={() => onRetry(item.id)}
                className="p-1.5 text-warning hover:bg-warning-light rounded transition-colors"
                title="Retry download"
              >
                <Icon name="refreshCw" size="sm" />
              </button>
            )}

            {/* Cancel button for active items */}
            {item.status === 'active' && (
              <button
                onClick={() => onCancel(item.id)}
                className="p-1.5 text-error hover:bg-error-light rounded transition-colors"
                title="Cancel download"
              >
                <Icon name="x" size="sm" />
              </button>
            )}

            {/* Remove button for pending/cancelled/failed items */}
            {(item.status === 'pending' || item.status === 'cancelled' || item.status === 'failed' || item.status === 'completed') && (
              <button
                onClick={() => onRemove(item.id)}
                className="p-1.5 text-text-muted hover:text-error hover:bg-error-light rounded transition-colors"
                title="Remove from queue"
              >
                <Icon name="trash2" size="sm" />
              </button>
            )}
          </div>
        </div>
      </div>
    );
  };

  if (items.length === 0) {
    return null;
  }

  return (
    <div className="card space-y-4">
      {/* Header with config */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h2 className="text-lg font-semibold text-text-primary">Download Queue</h2>

        {/* Processing mode toggle */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1 bg-surface-tertiary rounded-lg p-1">
            <button
              onClick={() => handleModeChange('sequential')}
              className={`px-3 py-1 text-sm rounded-md transition-colors ${
                config.processingMode === 'sequential'
                  ? 'bg-white text-text-primary shadow-sm'
                  : 'text-text-muted hover:text-text-primary'
              }`}
            >
              Sequential
            </button>
            <button
              onClick={() => handleModeChange('parallel')}
              className={`px-3 py-1 text-sm rounded-md transition-colors ${
                config.processingMode === 'parallel'
                  ? 'bg-white text-text-primary shadow-sm'
                  : 'text-text-muted hover:text-text-primary'
              }`}
            >
              Parallel
            </button>
          </div>

          {/* Concurrent count for parallel mode */}
          {config.processingMode === 'parallel' && (
            <div className="flex items-center gap-2">
              <span className="text-sm text-text-muted">Max:</span>
              <div className="flex items-center gap-1">
                <button
                  onClick={() => handleConcurrentChange(config.maxConcurrent - 1)}
                  className="w-6 h-6 flex items-center justify-center rounded bg-surface-tertiary text-text-muted hover:text-text-primary hover:bg-border-light transition-colors"
                  disabled={config.maxConcurrent <= 1}
                >
                  -
                </button>
                <span className="w-6 text-center text-sm text-text-primary">{config.maxConcurrent}</span>
                <button
                  onClick={() => handleConcurrentChange(config.maxConcurrent + 1)}
                  className="w-6 h-6 flex items-center justify-center rounded bg-surface-tertiary text-text-muted hover:text-text-primary hover:bg-border-light transition-colors"
                  disabled={config.maxConcurrent >= 5}
                >
                  +
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Queue stats */}
      <div className="flex items-center gap-4 text-sm">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-text-muted"></span>
          <span className="text-text-muted">Pending: {pendingItems.length}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-info animate-pulse"></span>
          <span className="text-text-muted">Active: {activeItems.length}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-success"></span>
          <span className="text-text-muted">Completed: {completedItems.length}</span>
        </div>
        {completedItems.length > 0 && (
          <button
            onClick={onClearCompleted}
            className="ml-auto text-xs text-text-muted hover:text-text-primary transition-colors"
          >
            Clear completed
          </button>
        )}
      </div>

      {/* Queue items by section */}
      <div className="space-y-4">
        {/* Active downloads */}
        {activeItems.length > 0 && (
          <div className="space-y-2">
            <h3 className="text-sm font-medium text-info-text">Active</h3>
            <div className="space-y-2">
              {items.filter((i) => i.status === 'active').map((item) =>
                renderQueueItem(item, items.indexOf(item), false)
              )}
            </div>
          </div>
        )}

        {/* Pending items - draggable */}
        {pendingItems.length > 0 && (
          <div className="space-y-2">
            <h3 className="text-sm font-medium text-text-muted flex items-center gap-2">
              Pending
              <span className="text-xs text-text-muted">(drag to reorder)</span>
            </h3>
            <div className="space-y-2">
              {items.filter((i) => i.status === 'pending').map((item) =>
                renderQueueItem(item, items.indexOf(item), true)
              )}
            </div>
          </div>
        )}

        {/* Completed/Failed items */}
        {completedItems.length > 0 && (
          <div className="space-y-2">
            <h3 className="text-sm font-medium text-text-muted">History</h3>
            <div className="space-y-2 max-h-48 overflow-y-auto queue-scrollbar">
              {items.filter((i) => ['completed', 'failed', 'cancelled'].includes(i.status)).map((item) =>
                renderQueueItem(item, items.indexOf(item), false)
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
