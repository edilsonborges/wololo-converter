import { useState, useCallback, type FC, type ChangeEvent, type ClipboardEvent } from 'react';
import { PLATFORMS, type PlatformInfo } from '../types';

interface URLInputProps {
  onUrlChange: (url: string, platform: string | null) => void;
  disabled?: boolean;
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

export const URLInput: FC<URLInputProps> = ({ onUrlChange, disabled }) => {
  const [url, setUrl] = useState('');
  const [detectedPlatform, setDetectedPlatform] = useState<PlatformInfo | null>(null);

  const handleChange = useCallback(
    (e: ChangeEvent<HTMLInputElement>) => {
      const newUrl = e.target.value;
      setUrl(newUrl);

      const platform = detectPlatform(newUrl);
      const platformInfo = platform ? PLATFORMS[platform] : null;
      setDetectedPlatform(platformInfo);

      onUrlChange(newUrl, platform);
    },
    [onUrlChange]
  );

  const handlePaste = useCallback(
    async (e: ClipboardEvent<HTMLInputElement>) => {
      // Let the default paste happen, then process
      setTimeout(() => {
        const input = e.target as HTMLInputElement;
        const newUrl = input.value;
        setUrl(newUrl);

        const platform = detectPlatform(newUrl);
        const platformInfo = platform ? PLATFORMS[platform] : null;
        setDetectedPlatform(platformInfo);

        onUrlChange(newUrl, platform);
      }, 0);
    },
    [onUrlChange]
  );

  const handleClear = useCallback(() => {
    setUrl('');
    setDetectedPlatform(null);
    onUrlChange('', null);
  }, [onUrlChange]);

  return (
    <div className="relative">
      <div className="relative">
        <input
          type="url"
          value={url}
          onChange={handleChange}
          onPaste={handlePaste}
          placeholder="Paste a YouTube, Instagram, Facebook, or Twitter/X URL..."
          className="input-field pr-24"
          disabled={disabled}
          autoFocus
        />

        {/* Platform indicator */}
        {detectedPlatform && (
          <div
            className={`absolute right-12 top-1/2 -translate-y-1/2 flex items-center gap-1 ${detectedPlatform.color}`}
          >
            <span>{detectedPlatform.icon}</span>
            <span className="text-sm font-medium hidden sm:inline">
              {detectedPlatform.name}
            </span>
          </div>
        )}

        {/* Clear button */}
        {url && (
          <button
            type="button"
            onClick={handleClear}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-white transition-colors"
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

      {/* Supported platforms hint */}
      {!url && (
        <div className="mt-2 flex items-center justify-center gap-4 text-gray-500 text-sm">
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
