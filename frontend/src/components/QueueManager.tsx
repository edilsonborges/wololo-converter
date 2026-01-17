import { useState, useCallback, useRef, type FC, type DragEvent } from 'react';
import type { QueueItem, QueueConfig, QueueProcessingMode, JobStatus } from '../types';
import { PLATFORMS } from '../types';

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
  pending: { bg: 'bg-gray-600', text: 'text-gray-300', label: 'Pending' },
  active: { bg: 'bg-blue-500', text: 'text-blue-400', label: 'Downloading' },
  completed: { bg: 'bg-green-500', text: 'text-green-400', label: 'Completed' },
  failed: { bg: 'bg-red-500', text: 'text-red-400', label: 'Failed' },
  cancelled: { bg: 'bg-gray-500', text: 'text-gray-400', label: 'Cancelled' },
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
          relative p-3 rounded-lg bg-gray-700/50 border border-gray-600
          ${isDraggable && item.status === 'pending' ? 'cursor-grab active:cursor-grabbing' : ''}
          ${dragOverIndex === index ? 'border-orange-500 border-2' : ''}
          transition-all duration-200
        `}
      >
        <div className="flex items-start gap-3">
          {/* Drag handle for pending items */}
          {isDraggable && item.status === 'pending' && (
            <div className="flex-shrink-0 text-gray-500 mt-1">
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 8h16M4 16h16" />
              </svg>
            </div>
          )}

          {/* Platform icon */}
          <div className={`flex-shrink-0 text-xl ${platformInfo?.color || 'text-gray-400'}`}>
            {platformInfo?.icon || '?'}
          </div>

          {/* Content */}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <span className={`text-xs px-2 py-0.5 rounded-full ${statusStyle.bg} ${statusStyle.text}`}>
                {progress ? JOB_STATUS_MAP[progress.status] || statusStyle.label : statusStyle.label}
              </span>
              {item.progress?.title && (
                <span className="text-sm text-white font-medium truncate">
                  {item.progress.title}
                </span>
              )}
            </div>
            <div className="text-sm text-gray-400 truncate">
              {item.url}
            </div>

            {/* Progress bar for active items */}
            {showProgress && (
              <div className="mt-2">
                <div className="flex justify-between text-xs text-gray-400 mb-1">
                  <span>{Math.round(progress.progress)}%</span>
                  <div className="flex items-center gap-2">
                    {progress.speed && <span>{progress.speed}</span>}
                    {progress.eta && <span>ETA: {progress.eta}</span>}
                  </div>
                </div>
                <div className="h-2 bg-gray-600 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-gradient-to-r from-red-500 via-orange-500 to-yellow-500 transition-all duration-300"
                    style={{ width: `${progress.progress}%` }}
                  />
                </div>
              </div>
            )}

            {/* Error message for failed items */}
            {item.status === 'failed' && item.error && (
              <div className="mt-2 text-xs text-red-400">
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
                className="p-1.5 text-green-400 hover:bg-green-400/20 rounded transition-colors"
                title="Download file"
              >
                <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                </svg>
              </button>
            )}

            {/* Retry button for failed items */}
            {item.status === 'failed' && (
              <button
                onClick={() => onRetry(item.id)}
                className="p-1.5 text-yellow-400 hover:bg-yellow-400/20 rounded transition-colors"
                title="Retry download"
              >
                <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                </svg>
              </button>
            )}

            {/* Cancel button for active items */}
            {item.status === 'active' && (
              <button
                onClick={() => onCancel(item.id)}
                className="p-1.5 text-red-400 hover:bg-red-400/20 rounded transition-colors"
                title="Cancel download"
              >
                <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            )}

            {/* Remove button for pending/cancelled/failed items */}
            {(item.status === 'pending' || item.status === 'cancelled' || item.status === 'failed' || item.status === 'completed') && (
              <button
                onClick={() => onRemove(item.id)}
                className="p-1.5 text-gray-400 hover:text-red-400 hover:bg-red-400/10 rounded transition-colors"
                title="Remove from queue"
              >
                <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
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
        <h2 className="text-lg font-semibold text-white">Download Queue</h2>

        {/* Processing mode toggle */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 bg-gray-700 rounded-lg p-1">
            <button
              onClick={() => handleModeChange('sequential')}
              className={`px-3 py-1 text-sm rounded-md transition-colors ${
                config.processingMode === 'sequential'
                  ? 'bg-orange-500 text-white'
                  : 'text-gray-400 hover:text-white'
              }`}
            >
              Sequential
            </button>
            <button
              onClick={() => handleModeChange('parallel')}
              className={`px-3 py-1 text-sm rounded-md transition-colors ${
                config.processingMode === 'parallel'
                  ? 'bg-orange-500 text-white'
                  : 'text-gray-400 hover:text-white'
              }`}
            >
              Parallel
            </button>
          </div>

          {/* Concurrent count for parallel mode */}
          {config.processingMode === 'parallel' && (
            <div className="flex items-center gap-2">
              <span className="text-sm text-gray-400">Max:</span>
              <div className="flex items-center gap-1">
                <button
                  onClick={() => handleConcurrentChange(config.maxConcurrent - 1)}
                  className="w-6 h-6 flex items-center justify-center rounded bg-gray-700 text-gray-400 hover:text-white hover:bg-gray-600 transition-colors"
                  disabled={config.maxConcurrent <= 1}
                >
                  -
                </button>
                <span className="w-6 text-center text-sm text-white">{config.maxConcurrent}</span>
                <button
                  onClick={() => handleConcurrentChange(config.maxConcurrent + 1)}
                  className="w-6 h-6 flex items-center justify-center rounded bg-gray-700 text-gray-400 hover:text-white hover:bg-gray-600 transition-colors"
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
          <span className="w-2 h-2 rounded-full bg-gray-500"></span>
          <span className="text-gray-400">Pending: {pendingItems.length}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-blue-500 animate-pulse"></span>
          <span className="text-gray-400">Active: {activeItems.length}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-green-500"></span>
          <span className="text-gray-400">Completed: {completedItems.length}</span>
        </div>
        {completedItems.length > 0 && (
          <button
            onClick={onClearCompleted}
            className="ml-auto text-xs text-gray-400 hover:text-white transition-colors"
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
            <h3 className="text-sm font-medium text-blue-400">Active</h3>
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
            <h3 className="text-sm font-medium text-gray-400 flex items-center gap-2">
              Pending
              <span className="text-xs text-gray-500">(drag to reorder)</span>
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
            <h3 className="text-sm font-medium text-gray-500">History</h3>
            <div className="space-y-2 max-h-48 overflow-y-auto">
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
