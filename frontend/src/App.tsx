import { useState, useCallback } from 'react';
import { MultiURLInput, QueueManager, Icon, type ParsedURL } from './components';
import { useQueueManager } from './hooks/useQueueManager';

function App() {
  // Form state
  const [parsedUrls, setParsedUrls] = useState<ParsedURL[]>([]);
  const [resetTrigger, setResetTrigger] = useState(0);

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

  const handleAddToQueue = useCallback(() => {
    const validUrls = parsedUrls.filter((u) => u.isValid);
    if (validUrls.length === 0) return;

    // Always use 'video' format since we only support video now
    const added = addToQueue(parsedUrls, 'video');
    if (added > 0) {
      // Clear the input after adding to queue
      setParsedUrls([]);
      setResetTrigger((prev) => prev + 1);
    }
  }, [parsedUrls, addToQueue]);

  const validUrlCount = parsedUrls.filter((u) => u.isValid).length;
  const canAddToQueue = validUrlCount > 0;

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
            Download videos from YouTube, Instagram, and Twitter/X
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
      </footer>
    </div>
  );
}

export default App;
