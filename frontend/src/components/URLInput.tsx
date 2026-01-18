import { useState, useCallback, type FC, type ChangeEvent, type ClipboardEvent } from 'react';
import { PLATFORMS, type PlatformInfo } from '../types';
import { Icon, PlatformIcon } from './Icon';

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
  const [platformKey, setPlatformKey] = useState<string | null>(null);

  const handleChange = useCallback(
    (e: ChangeEvent<HTMLInputElement>) => {
      const newUrl = e.target.value;
      setUrl(newUrl);

      const platform = detectPlatform(newUrl);
      const platformInfo = platform ? PLATFORMS[platform] : null;
      setDetectedPlatform(platformInfo);
      setPlatformKey(platform);

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
        setPlatformKey(platform);

        onUrlChange(newUrl, platform);
      }, 0);
    },
    [onUrlChange]
  );

  const handleClear = useCallback(() => {
    setUrl('');
    setDetectedPlatform(null);
    setPlatformKey(null);
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
        {detectedPlatform && platformKey && (
          <div
            className={`absolute right-12 top-1/2 -translate-y-1/2 flex items-center gap-1.5 ${detectedPlatform.color}`}
          >
            <PlatformIcon platform={platformKey} size="sm" />
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
            className="absolute right-3 top-1/2 -translate-y-1/2 p-1 text-text-muted hover:text-text-primary hover:bg-surface-tertiary rounded transition-colors"
            disabled={disabled}
          >
            <Icon name="x" size="sm" />
          </button>
        )}
      </div>

      {/* Supported platforms hint */}
      {!url && (
        <div className="mt-2 flex items-center justify-center gap-4 text-text-muted text-sm">
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
