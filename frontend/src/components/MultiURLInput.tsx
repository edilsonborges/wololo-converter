import { useState, useCallback, useEffect, type FC, type ChangeEvent, type ClipboardEvent } from 'react';
import { PLATFORMS, type PlatformInfo } from '../types';

interface MultiURLInputProps {
  onUrlsChange: (urls: ParsedURL[]) => void;
  disabled?: boolean;
  resetTrigger?: number; // Change this to reset the input
}

export interface ParsedURL {
  url: string;
  platform: string | null;
  platformInfo: PlatformInfo | null;
  isValid: boolean;
}

// Pattern matching for platforms
const PLATFORM_PATTERNS: Record<string, RegExp[]> = {
  youtube: [
    /(?:https?:\/\/)?(?:www\.)?youtube\.com\/watch\?v=[\w-]+/i,
    /(?:https?:\/\/)?(?:www\.)?youtube\.com\/shorts\/[\w-]+/i,
    /(?:https?:\/\/)?youtu\.be\/[\w-]+/i,
  ],
  instagram: [
    /(?:https?:\/\/)?(?:www\.)?instagram\.com\/(?:p|reel|tv)\/[\w-]+/i,
  ],
  facebook: [
    /(?:https?:\/\/)?(?:www\.)?facebook\.com\/.+\/videos\/\d+/i,
    /(?:https?:\/\/)?(?:www\.)?facebook\.com\/watch\/?\?v=\d+/i,
    /(?:https?:\/\/)?fb\.watch\/[\w-]+/i,
  ],
  twitter: [
    /(?:https?:\/\/)?(?:www\.)?(?:twitter|x)\.com\/\w+\/status\/\d+/i,
  ],
};

function detectPlatform(url: string): string | null {
  const trimmedUrl = url.trim().toLowerCase();
  for (const [platform, patterns] of Object.entries(PLATFORM_PATTERNS)) {
    for (const pattern of patterns) {
      if (pattern.test(trimmedUrl)) {
        return platform;
      }
    }
  }
  return null;
}

function parseURLs(text: string): ParsedURL[] {
  // Split by newlines, commas, or spaces and filter empty strings
  const lines = text
    .split(/[\n,\s]+/)
    .map((line) => line.trim())
    .filter((line) => line.length > 0);

  // Remove duplicates
  const uniqueUrls = [...new Set(lines)];

  return uniqueUrls.map((url) => {
    const platform = detectPlatform(url);
    const platformInfo = platform ? PLATFORMS[platform] : null;
    return {
      url,
      platform,
      platformInfo,
      isValid: platform !== null,
    };
  });
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
            className="absolute right-3 top-3 text-gray-400 hover:text-white transition-colors"
            disabled={disabled}
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

      {/* URL Count Summary */}
      {parsedUrls.length > 0 && (
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <div className="flex items-center gap-2">
            <span className="text-gray-400">URLs detected:</span>
            <span className="font-medium text-white">{parsedUrls.length}</span>
          </div>
          {validCount > 0 && (
            <div className="flex items-center gap-1 text-green-400">
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
              <span>{validCount} valid</span>
            </div>
          )}
          {invalidCount > 0 && (
            <div className="flex items-center gap-1 text-yellow-400">
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
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
              className={`flex items-center gap-1 px-2 py-1 rounded-md bg-gray-700/50 text-sm ${parsed.platformInfo?.color || 'text-gray-400'}`}
            >
              <span>{parsed.platformInfo?.icon}</span>
              <span className="max-w-[150px] truncate text-gray-300">{parsed.url}</span>
            </div>
          ))}
          {parsedUrls.filter((u) => !u.isValid).map((parsed, idx) => (
            <div
              key={`invalid-${parsed.url}-${idx}`}
              className="flex items-center gap-1 px-2 py-1 rounded-md bg-yellow-500/10 border border-yellow-500/30 text-sm text-yellow-400"
            >
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01" />
              </svg>
              <span className="max-w-[150px] truncate">{parsed.url}</span>
            </div>
          ))}
        </div>
      )}

      {/* Supported platforms hint */}
      {!text && (
        <div className="flex items-center justify-center gap-4 text-gray-500 text-sm">
          <span>Supported:</span>
          {Object.values(PLATFORMS).map((platform) => (
            <span key={platform.name} className="flex items-center gap-1">
              {platform.icon} {platform.name}
            </span>
          ))}
        </div>
      )}
    </div>
  );
};
