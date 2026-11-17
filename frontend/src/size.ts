import type { PreviewResponse, VideoQuality } from './types';

const VIDEO_QUALITIES: VideoQuality[] = ['1080p', '720p', '480p', '360p'];

/** Short decimal size, like the server's messages: 6.9 GB, 4 GB, 450 MB */
export function formatSize(bytes: number): string {
  if (bytes >= 1e9) return `${(bytes / 1e9).toFixed(1).replace(/\.0$/, '')} GB`;
  return `${Math.max(1, Math.round(bytes / 1e6))} MB`;
}

export interface SizeCheck {
  size?: number;
  tooLarge: boolean;
  /** Best quality below the requested one that fits the limit */
  suggestion?: { quality: VideoQuality; size: number };
  message?: string;
}

/** Whether a quality fits the server's limit, from the preview's estimates. */
export function checkSize(
  preview: Pick<PreviewResponse, 'sizes' | 'size_limit'> | null | undefined,
  quality: VideoQuality,
): SizeCheck {
  const size = preview?.sizes?.[quality];
  const limit = preview?.size_limit;
  if (size == null || !limit || size <= limit) return { size, tooLarge: false };

  const lower = quality === 'mp3' ? [] : VIDEO_QUALITIES.slice(VIDEO_QUALITIES.indexOf(quality) + 1);
  const fit = lower.find((q) => {
    const s = preview?.sizes?.[q];
    return s != null && s <= limit;
  });
  const suggestion = fit ? { quality: fit, size: preview!.sizes![fit]! } : undefined;
  const label = quality === 'mp3' ? 'MP3' : quality;
  return {
    size,
    tooLarge: true,
    suggestion,
    message:
      `Too large: ~${formatSize(size)} at ${label} (limit ${formatSize(limit)}).` +
      (suggestion ? ` ${suggestion.quality} fits (~${formatSize(suggestion.size)}).` : ' No quality fits.'),
  };
}
