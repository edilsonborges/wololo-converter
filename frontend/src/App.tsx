import { useState, useCallback, useEffect, useRef } from 'react';
import { MultiURLInput, QueueManager, QualitySelector, VideoPreview, Icon, type ParsedURL } from './components';
import { useQueueManager } from './hooks/useQueueManager';
import { api } from './api';
import type { VideoQuality, PreviewResponse } from './types';

function App() {
  // Form state
  const [parsedUrls, setParsedUrls] = useState<ParsedURL[]>([]);
  const [selectedQuality, setSelectedQuality] = useState<VideoQuality>('480p');
  const [resetTrigger, setResetTrigger] = useState(0);

  // Preview state
  const [preview, setPreview] = useState<PreviewResponse | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastPreviewUrlRef = useRef<string | null>(null);

  // Queue manager hook
  const {
    items,
    config,
    setConfig,
    addToQueue,
    removeItem,
    reorderItems,
    cancelItem,
    retryItem,
    clearCompleted,
    downloadFile,
  } = useQueueManager();

  const handleUrlsChange = useCallback((urls: ParsedURL[]) => {
    setParsedUrls(urls);
  }, []);

  // Fetch preview when a single valid URL is detected (500ms debounce)
  useEffect(() => {
    const validUrls = parsedUrls.filter((u) => u.isValid);

    // Only fetch preview for a single URL
    if (validUrls.length !== 1) {
      // Clear preview when not exactly one URL
      if (debounceRef.current) {
        clearTimeout(debounceRef.current);
        debounceRef.current = null;
      }
      setPreview(null);
      setPreviewLoading(false);
      setPreviewError(null);
      lastPreviewUrlRef.current = null;
      return;
    }

    const url = validUrls[0].url;
    const platform = validUrls[0].platform;

    // Skip preview for Instagram/Threads (not needed, slows down UX)
    if (platform === 'instagram' || platform === 'threads') {
      setPreview(null);
      setPreviewLoading(false);
      setPreviewError(null);
      lastPreviewUrlRef.current = null;
      return;
    }

    // Skip if we already fetched preview for this URL
    if (url === lastPreviewUrlRef.current) return;

    // Clear previous debounce
    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
    }

    debounceRef.current = setTimeout(async () => {
      lastPreviewUrlRef.current = url;
      setPreviewLoading(true);
      setPreviewError(null);
      setPreview(null);

      try {
        const result = await api.fetchPreview(url);
        setPreview(result);
      } catch (err) {
        setPreviewError(
          err instanceof Error ? err.message : 'Não foi possível carregar o preview'
        );
      } finally {
        setPreviewLoading(false);
      }
    }, 500);

    return () => {
      if (debounceRef.current) {
        clearTimeout(debounceRef.current);
      }
    };
  }, [parsedUrls]);

  const handleAddToQueue = useCallback(() => {
    const validUrls = parsedUrls.filter((u) => u.isValid);
    if (validUrls.length === 0) return;

    const added = addToQueue(parsedUrls, selectedQuality);
    if (added > 0) {
      // Clear the input and preview after adding to queue
      setParsedUrls([]);
      setPreview(null);
      setPreviewError(null);
      lastPreviewUrlRef.current = null;
      setResetTrigger((prev) => prev + 1);
    }
  }, [parsedUrls, addToQueue, selectedQuality]);

  const validUrlCount = parsedUrls.filter((u) => u.isValid).length;
  const canAddToQueue = validUrlCount > 0;
  const isSingleUrl = validUrlCount === 1;

  return (
    <div className="min-h-screen bg-white">
      {/* Header */}
      <header className="py-8 px-4 border-b border-border-light">
        <div className="max-w-2xl mx-auto text-center">
          <div className="flex items-center justify-center gap-4">
            <img
              src="/wololo-left.png"
              alt="Wololo Left"
              className="w-16 h-16 sm:w-20 sm:h-20 object-contain"
            />
            <h1 className="text-4xl sm:text-5xl font-semibold text-text-primary tracking-tight">
              Wololo Converter
            </h1>
            <img
              src="/wololo-right.png"
              alt="Wololo Right"
              className="w-16 h-16 sm:w-20 sm:h-20 object-contain"
            />
          </div>
          <p className="mt-3 text-text-tertiary">
            Download videos from YouTube, Instagram, Threads and Twitter/X
          </p>
        </div>
      </header>

      {/* Main content */}
      <main className="px-4 py-8">
        <div className="max-w-2xl mx-auto space-y-6">
          {/* Download form */}
          <div className="card space-y-6">
            {/* Multi-URL Input */}
            <MultiURLInput onUrlsChange={handleUrlsChange} disabled={false} resetTrigger={resetTrigger} />

            {/* Video Preview (single URL only) */}
            {isSingleUrl && (
              <VideoPreview
                preview={preview}
                isLoading={previewLoading}
                error={previewError}
                selectedQuality={selectedQuality}
              />
            )}

            {/* Quality Selector - only when there's a valid URL */}
            {canAddToQueue && (
              <QualitySelector
                selectedQuality={selectedQuality}
                onQualityChange={setSelectedQuality}
                availableQualities={isSingleUrl && preview ? preview.available_qualities : undefined}
              />
            )}

            {/* Add to queue button */}
            <button
              onClick={handleAddToQueue}
              disabled={!canAddToQueue}
              className="btn-primary w-full flex items-center justify-center gap-2"
            >
              <Icon name="plus" size="sm" />
              {validUrlCount > 0 ? (
                <>Add {validUrlCount} {validUrlCount === 1 ? 'URL' : 'URLs'} to Queue</>
              ) : (
                <>Add to Queue</>
              )}
            </button>
          </div>

          {/* Queue Manager */}
          {items.length > 0 && (
            <QueueManager
              items={items}
              config={config}
              onConfigChange={setConfig}
              onReorder={reorderItems}
              onRemove={removeItem}
              onCancel={cancelItem}
              onRetry={retryItem}
              onDownload={downloadFile}
              onClearCompleted={clearCompleted}
            />
          )}

          {/* Empty state when no items in queue */}
          {items.length === 0 && (
            <div className="card">
              <div className="text-center py-8">
                <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-surface-tertiary mb-4">
                  <Icon name="inbox" size="xl" className="text-text-muted" />
                </div>
                <h3 className="text-lg font-medium text-text-primary mb-2">
                  Your download queue is empty
                </h3>
                <p className="text-text-tertiary text-sm max-w-sm mx-auto">
                  Paste one or more URLs above and click "Add to Queue" to start downloading.
                  You can process downloads sequentially or in parallel.
                </p>
              </div>
            </div>
          )}
        </div>
      </main>

      {/* Footer */}
      <footer className="py-6 px-4 text-center text-text-muted text-sm border-t border-border-light">
        <p>Personal use only. Respect copyright and platform terms of service.</p>
        <p className="mt-1 text-text-muted/50 text-xs">v0.5.0</p>
      </footer>
    </div>
  );
}

export default App;
