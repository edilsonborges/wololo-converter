import { PLATFORMS, type PlatformInfo } from './types';

export interface ParsedURL {
  url: string;
  platform: string | null;
  platformInfo: PlatformInfo | null;
  isValid: boolean;
}

// Pattern matching for platforms
const PLATFORM_PATTERNS: Record<string, RegExp[]> = {
  youtube: [
    /(?:https?:\/\/)?(?:(?:www|m|music)\.)?youtube\.com\/watch\?(?:[^#]*&)?v=[\w-]+/i,
    /(?:https?:\/\/)?(?:(?:www|m)\.)?youtube\.com\/shorts\/[\w-]+/i,
    /(?:https?:\/\/)?(?:(?:www|m)\.)?youtube\.com\/live\/[\w-]+/i,
    /(?:https?:\/\/)?(?:(?:www|m)\.)?youtube\.com\/embed\/[\w-]+/i,
    /(?:https?:\/\/)?youtu\.be\/[\w-]+/i,
  ],
  instagram: [
    /(?:https?:\/\/)?(?:www\.)?instagram\.com\/(?:p|reels?|tv)\/[\w-]+/i,
    /(?:https?:\/\/)?(?:www\.)?instagram\.com\/share\/(?:p|reel)\/[\w-]+/i,
  ],
  tiktok: [
    /(?:https?:\/\/)?(?:www\.)?tiktok\.com\/@[\w.]+\/video\/\d+/i,
    /(?:https?:\/\/)?(?:vm|vt)\.tiktok\.com\/[\w]+/i,
    /(?:https?:\/\/)?(?:www\.)?tiktok\.com\/t\/[\w]+/i,
  ],
  twitter: [
    /(?:https?:\/\/)?(?:www\.)?(?:twitter|x)\.com\/\w+\/status\/\d+/i,
  ],
  threads: [
    /(?:https?:\/\/)?(?:www\.)?threads\.(?:net|com)\/@[\w.]+\/post\/[\w]+/i,
  ],
};

export function detectPlatform(url: string): string | null {
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

export function normalizeVideoUrl(url: string, platform: string): string {
  const source = /^https?:\/\//i.test(url) ? url : `https://${url}`;

  try {
    const parsed = new URL(source);

    if (platform === 'youtube' && parsed.pathname === '/watch') {
      const videoId = parsed.searchParams.get('v');
      if (videoId) return `https://youtu.be/${videoId}`;
    }

    if (platform === 'youtube' && parsed.hostname === 'youtu.be') {
      const videoId = parsed.pathname.split('/').filter(Boolean)[0];
      if (videoId) return `https://youtu.be/${videoId}`;
    }

    parsed.protocol = 'https:';
    parsed.username = '';
    parsed.password = '';
    parsed.search = '';
    parsed.hash = '';
    return parsed.toString();
  } catch {
    return url;
  }
}

export function parseURLs(text: string): ParsedURL[] {
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
      url: platform ? normalizeVideoUrl(url, platform) : url,
      platform,
      platformInfo,
      isValid: platform !== null,
    };
  });
}

interface RouteLocation {
  pathname: string;
  search: string;
  hash: string;
}

/**
 * Converts a source URL placed after the app root into a queue-ready URL.
 *
 * Supported examples:
 * /https://x.com/user/status/123?s=48
 * /x.com/user/status/123?s=48
 */
export function parseAutoDownloadRoute(location: RouteLocation): ParsedURL | null {
  if (!location.pathname || location.pathname === '/') return null;

  let path = location.pathname.slice(1);
  try {
    path = decodeURIComponent(path);
  } catch {
    return null;
  }

  // Be tolerant of a proxy that merges the two slashes after the protocol.
  path = path.replace(/^(https?):\/(?!\/)/i, '$1://');
  path = path.replace(/^\/+/, '');

  const sourceUrl = /^https?:\/\//i.test(path) ? path : `https://${path}`;
  const candidate = `${sourceUrl}${location.search}${location.hash}`;

  try {
    const parsed = new URL(candidate);
    if (!['http:', 'https:'].includes(parsed.protocol)) return null;
  } catch {
    return null;
  }

  const result = parseURLs(candidate)[0];
  return result?.isValid ? result : null;
}
