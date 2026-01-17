import { useState, useCallback, useRef, useEffect } from 'react';
import { api, ApiError } from '../api';
import type { QueueItem, QueueConfig, OutputFormat, JobProgressUpdate, QueueItemStatus } from '../types';

interface ParsedURL {
  url: string;
  platform: string | null;
  isValid: boolean;
}

// Generate unique ID
function generateId(): string {
  return `${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
}

export function useQueueManager() {
  const [items, setItems] = useState<QueueItem[]>([]);
  const [config, setConfig] = useState<QueueConfig>({
    processingMode: 'sequential',
    maxConcurrent: 2,
  });

  // Refs to track SSE cleanups and processing state
  const cleanupRefs = useRef<Map<string, () => void>>(new Map());
  const processingRef = useRef(false);

  // Cleanup all SSE connections on unmount
  useEffect(() => {
    return () => {
      cleanupRefs.current.forEach((cleanup) => cleanup());
      cleanupRefs.current.clear();
    };
  }, []);

  // Add URLs to queue
  const addToQueue = useCallback((parsedUrls: ParsedURL[], format: OutputFormat) => {
    const validUrls = parsedUrls.filter((u) => u.isValid);

    const newItems: QueueItem[] = validUrls.map((parsed) => ({
      id: generateId(),
      url: parsed.url,
      platform: parsed.platform,
      format,
      status: 'pending' as QueueItemStatus,
      addedAt: Date.now(),
    }));

    setItems((prev) => [...prev, ...newItems]);
    return newItems.length;
  }, []);

  // Update a single item
  const updateItem = useCallback((id: string, updates: Partial<QueueItem>) => {
    setItems((prev) =>
      prev.map((item) =>
        item.id === id ? { ...item, ...updates } : item
      )
    );
  }, []);

  // Reorder items (drag and drop)
  const reorderItems = useCallback((fromIndex: number, toIndex: number) => {
    setItems((prev) => {
      const newItems = [...prev];
      const [removed] = newItems.splice(fromIndex, 1);
      newItems.splice(toIndex, 0, removed);
      return newItems;
    });
  }, []);

  // Remove an item from queue
  const removeItem = useCallback((id: string) => {
    // Cleanup any SSE connection
    const cleanup = cleanupRefs.current.get(id);
    if (cleanup) {
      cleanup();
      cleanupRefs.current.delete(id);
    }

    setItems((prev) => prev.filter((item) => item.id !== id));
  }, []);

  // Cancel an active download
  const cancelItem = useCallback(async (id: string) => {
    const item = items.find((i) => i.id === id);
    if (!item || !item.jobId) return;

    try {
      await api.cancelJob(item.jobId);
    } catch {
      // Ignore cancel errors
    }

    // Cleanup SSE connection
    const cleanup = cleanupRefs.current.get(id);
    if (cleanup) {
      cleanup();
      cleanupRefs.current.delete(id);
    }

    updateItem(id, { status: 'cancelled' });
  }, [items, updateItem]);

  // Retry a failed item
  const retryItem = useCallback((id: string) => {
    updateItem(id, {
      status: 'pending',
      error: undefined,
      jobId: undefined,
      progress: undefined,
    });
  }, [updateItem]);

  // Clear completed/failed/cancelled items
  const clearCompleted = useCallback(() => {
    setItems((prev) =>
      prev.filter((item) => !['completed', 'failed', 'cancelled'].includes(item.status))
    );
  }, []);

  // Download a completed file
  const downloadFile = useCallback((jobId: string) => {
    const downloadUrl = api.getDownloadUrl(jobId);
    const link = document.createElement('a');
    link.href = downloadUrl;
    link.download = '';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  }, []);

  // Start processing a single item
  const startItemDownload = useCallback(async (item: QueueItem) => {
    updateItem(item.id, { status: 'active' });

    try {
      const response = await api.startDownload({
        url: item.url,
        output_format: item.format,
      });

      updateItem(item.id, { jobId: response.job_id });

      // Subscribe to progress updates
      const cleanup = api.subscribeToProgress(response.job_id, {
        onProgress: (update: JobProgressUpdate) => {
          updateItem(item.id, { progress: update });
        },
        onComplete: (update: JobProgressUpdate) => {
          updateItem(item.id, {
            progress: update,
            status: update.status === 'completed' ? 'completed' : 'failed',
            error: update.error_message,
            completedAt: Date.now(),
          });

          // Cleanup SSE ref
          cleanupRefs.current.delete(item.id);
        },
        onError: (err) => {
          updateItem(item.id, {
            status: 'failed',
            error: err.message,
            completedAt: Date.now(),
          });

          // Cleanup SSE ref
          cleanupRefs.current.delete(item.id);
        },
      });

      cleanupRefs.current.set(item.id, cleanup);
    } catch (err) {
      updateItem(item.id, {
        status: 'failed',
        error: err instanceof ApiError ? err.message : 'Failed to start download',
        completedAt: Date.now(),
      });
    }
  }, [updateItem]);

  // Process the queue
  const processQueue = useCallback(async () => {
    if (processingRef.current) return;
    processingRef.current = true;

    const processLoop = async () => {
      // Get current state
      const currentItems = items;
      const pendingItems = currentItems.filter((i) => i.status === 'pending');
      const activeItems = currentItems.filter((i) => i.status === 'active');

      if (pendingItems.length === 0) {
        processingRef.current = false;
        return;
      }

      if (config.processingMode === 'sequential') {
        // Sequential: Only one at a time
        if (activeItems.length === 0 && pendingItems.length > 0) {
          await startItemDownload(pendingItems[0]);
        }
      } else {
        // Parallel: Up to maxConcurrent at a time
        const slotsAvailable = config.maxConcurrent - activeItems.length;
        const itemsToStart = pendingItems.slice(0, slotsAvailable);

        for (const item of itemsToStart) {
          startItemDownload(item);
        }
      }
    };

    await processLoop();
  }, [items, config, startItemDownload]);

  // Auto-process queue when items change or processing completes
  useEffect(() => {
    const pendingItems = items.filter((i) => i.status === 'pending');
    const activeItems = items.filter((i) => i.status === 'active');

    // Check if we should start processing
    if (pendingItems.length > 0) {
      if (config.processingMode === 'sequential' && activeItems.length === 0) {
        // Sequential mode: start next if nothing active
        processQueue();
      } else if (config.processingMode === 'parallel' && activeItems.length < config.maxConcurrent) {
        // Parallel mode: start more if slots available
        processQueue();
      }
    } else if (pendingItems.length === 0 && activeItems.length === 0) {
      processingRef.current = false;
    }
  }, [items, config, processQueue]);

  // Start processing manually
  const startProcessing = useCallback(() => {
    processQueue();
  }, [processQueue]);

  // Stop processing (cancel all active)
  const stopProcessing = useCallback(async () => {
    const activeItems = items.filter((i) => i.status === 'active');

    for (const item of activeItems) {
      await cancelItem(item.id);
    }

    processingRef.current = false;
  }, [items, cancelItem]);

  // Check if there are items to process
  const hasItemsToProcess = items.some((i) => i.status === 'pending');
  const hasActiveItems = items.some((i) => i.status === 'active');

  return {
    items,
    config,
    setConfig,
    isProcessing: hasActiveItems,
    hasItemsToProcess,

    // Actions
    addToQueue,
    removeItem,
    reorderItems,
    cancelItem,
    retryItem,
    clearCompleted,
    downloadFile,
    startProcessing,
    stopProcessing,
  };
}
