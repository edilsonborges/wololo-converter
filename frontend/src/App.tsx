import { useState, useCallback } from 'react';
import { MultiURLInput, FormatSelector, QueueManager, type ParsedURL } from './components';
import { useQueueManager } from './hooks/useQueueManager';
import type { OutputFormat } from './types';

function App() {
  // Form state
  const [parsedUrls, setParsedUrls] = useState<ParsedURL[]>([]);
  const [format, setFormat] = useState<OutputFormat>('video');
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

  const handleFormatChange = useCallback((newFormat: OutputFormat) => {
    setFormat(newFormat);
  }, []);

  const handleAddToQueue = useCallback(() => {
    const validUrls = parsedUrls.filter((u) => u.isValid);
    if (validUrls.length === 0) return;

    const added = addToQueue(parsedUrls, format);
    if (added > 0) {
      // Clear the input after adding to queue
      setParsedUrls([]);
      setResetTrigger((prev) => prev + 1);
    }
  }, [parsedUrls, format, addToQueue]);

  const validUrlCount = parsedUrls.filter((u) => u.isValid).length;
  const canAddToQueue = validUrlCount > 0;

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-gray-800 to-gray-900">
      {/* Header */}
      <header className="py-8 px-4">
        <div className="max-w-2xl mx-auto text-center">
          <h1 className="text-4xl sm:text-5xl font-bold bg-gradient-to-r from-red-500 via-orange-500 to-yellow-500 bg-clip-text text-transparent">
            Wololo Converter
          </h1>
          <p className="mt-3 text-gray-400">
            Download videos and audio from YouTube, Instagram, Facebook, and Twitter/X
          </p>
        </div>
      </header>

      {/* Main content */}
      <main className="px-4 pb-12">
        <div className="max-w-2xl mx-auto space-y-6">
          {/* Download form */}
          <div className="card space-y-6">
            {/* Multi-URL Input */}
            <MultiURLInput onUrlsChange={handleUrlsChange} disabled={false} resetTrigger={resetTrigger} />

            {/* Format Selector */}
            <FormatSelector
              selectedFormat={format}
              onFormatChange={handleFormatChange}
              disabled={false}
            />

            {/* Add to queue button */}
            <button
              onClick={handleAddToQueue}
              disabled={!canAddToQueue}
              className="btn-primary w-full flex items-center justify-center gap-2"
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
                  d="M12 4v16m8-8H4"
                />
              </svg>
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
                <div className="text-6xl mb-4">📥</div>
                <h3 className="text-lg font-medium text-white mb-2">
                  Your download queue is empty
                </h3>
                <p className="text-gray-400 text-sm max-w-sm mx-auto">
                  Paste one or more URLs above and click "Add to Queue" to start downloading.
                  You can process downloads sequentially or in parallel.
                </p>
              </div>
            </div>
          )}
        </div>
      </main>

      {/* Footer */}
      <footer className="py-6 px-4 text-center text-gray-500 text-sm">
        <p>Personal use only. Respect copyright and platform terms of service.</p>
      </footer>
    </div>
  );
}

export default App;
