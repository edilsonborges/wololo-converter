import { useState, useCallback, useEffect, type FC, type ChangeEvent, type ClipboardEvent } from 'react';
import { PLATFORMS } from '../types';
import { parseURLs, type ParsedURL } from '../urlParser';
import { Icon, PlatformIcon } from './Icon';

interface MultiURLInputProps {
  onUrlsChange: (urls: ParsedURL[]) => void;
  disabled?: boolean;
  resetTrigger?: number; // Change this to reset the input
}

export const MultiURLInput: FC<MultiURLInputProps> = ({ onUrlsChange, disabled, resetTrigger }) => {
  const [text, setText] = useState('');
  const [parsedUrls, setParsedUrls] = useState<ParsedURL[]>([]);

  // Reset the input when resetTrigger changes
  useEffect(() => {
    if (resetTrigger !== undefined && resetTrigger > 0) {
      setText('');
      setParsedUrls([]);
    }
  }, [resetTrigger]);

  const updateUrls = useCallback(
    (newText: string) => {
      setText(newText);
      const urls = parseURLs(newText);
      setParsedUrls(urls);
      onUrlsChange(urls);
    },
    [onUrlsChange]
  );

  const handleChange = useCallback(
    (e: ChangeEvent<HTMLTextAreaElement>) => {
      updateUrls(e.target.value);
    },
    [updateUrls]
  );

  const handlePaste = useCallback(
    async (e: ClipboardEvent<HTMLTextAreaElement>) => {
      // Let the default paste happen, then process
      setTimeout(() => {
        const textarea = e.target as HTMLTextAreaElement;
        updateUrls(textarea.value);
      }, 0);
    },
    [updateUrls]
  );

  const handleClear = useCallback(() => {
    setText('');
    setParsedUrls([]);
    onUrlsChange([]);
  }, [onUrlsChange]);

  const validCount = parsedUrls.filter((u) => u.isValid).length;
  const invalidCount = parsedUrls.filter((u) => !u.isValid).length;

  return (
    <div className="space-y-3">
      <div className="relative">
        <textarea
          value={text}
          onChange={handleChange}
          onPaste={handlePaste}
          placeholder="Paste one or more URLs here (one per line, or separated by commas/spaces)..."
          className="input-field min-h-[120px] resize-y pr-10"
          disabled={disabled}
          autoFocus
        />

        {/* Clear button */}
        {text && (
          <button
            type="button"
            onClick={handleClear}
            className="absolute right-3 top-3 p-1 text-text-muted hover:text-text-primary hover:bg-surface-tertiary rounded transition-colors"
            disabled={disabled}
          >
            <Icon name="x" size="sm" />
          </button>
        )}
      </div>

      {/* URL Count Summary */}
      {parsedUrls.length > 0 && (
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <div className="flex items-center gap-2">
            <span className="text-text-muted">URLs detected:</span>
            <span className="font-medium text-text-primary">{parsedUrls.length}</span>
          </div>
          {validCount > 0 && (
            <div className="flex items-center gap-1 text-success-text">
              <Icon name="check" size="sm" />
              <span>{validCount} valid</span>
            </div>
          )}
          {invalidCount > 0 && (
            <div className="flex items-center gap-1 text-warning-text">
              <Icon name="alertTriangle" size="sm" />
              <span>{invalidCount} unsupported</span>
            </div>
          )}
        </div>
      )}

      {/* Platform breakdown */}
      {parsedUrls.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {parsedUrls.filter((u) => u.isValid).map((parsed, idx) => (
            <div
              key={`${parsed.url}-${idx}`}
              className={`flex items-center gap-1.5 px-2 py-1 rounded-md bg-surface-secondary border border-border-light text-sm`}
            >
              <PlatformIcon platform={parsed.platform || ''} size="sm" className={parsed.platformInfo?.color || 'text-text-muted'} />
              <span className="max-w-[150px] truncate text-text-secondary">{parsed.url}</span>
            </div>
          ))}
          {parsedUrls.filter((u) => !u.isValid).map((parsed, idx) => (
            <div
              key={`invalid-${parsed.url}-${idx}`}
              className="flex items-center gap-1.5 px-2 py-1 rounded-md bg-warning-light border border-warning/20 text-sm text-warning-text"
            >
              <Icon name="alertTriangle" size="sm" />
              <span className="max-w-[150px] truncate">{parsed.url}</span>
            </div>
          ))}
        </div>
      )}

      {/* Supported platforms hint */}
      {!text && (
        <div className="flex items-center justify-center gap-4 text-text-muted text-sm">
          <span>Supported:</span>
          {Object.entries(PLATFORMS).map(([key, platform]) => (
            <span key={platform.name} className="flex items-center gap-1.5">
              <PlatformIcon platform={key} size="sm" className={platform.color} />
              <span>{platform.name}</span>
            </span>
          ))}
        </div>
      )}
    </div>
  );
};
