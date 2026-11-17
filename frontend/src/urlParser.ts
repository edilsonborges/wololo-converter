import { PLATFORMS, type PlatformInfo, type VideoQuality } from './types';

export interface ParsedURL {
  url: string;
  platform: string | null;
  platformInfo: PlatformInfo | null;
  isValid: boolean;
  /** How many more times the same video appeared in the pasted text */
  duplicates?: number;
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
    /(?:https?:\/\/)?(?:www\.)?threads\.(?:net|com)\/share\/[\w-]+(?:\/|[?#]|$)/i,
  ],
  // Music pages resolved to YouTube videos (downloaded as MP3); not listed
  // among the supported platforms
  music: [
    /^(?:https?:\/\/)?(?:www\.)?artlist\.io\/royalty-free-music\/(?:album|song)\/[^/?#\s]+\/\d+/i,
  ],
};

export const MUSIC_PLATFORM = 'music';

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

const YOUTUBE_ID_PATH = /^\/(?:shorts|live|embed|v)\/([\w-]{6,})/;
const POST_ID_PATHS: Record<string, RegExp> = {
  instagram: /^\/(?:share\/)?(?:p|reels?|tv)\/([\w-]+)/,
  twitter: /\/status\/(\d+)/,
  tiktok: /\/video\/(\d+)/,
};

/**
 * The same video however its link was written (mirrors media_key on the
 * server): youtu.be/ID, youtube.com/watch?v=ID&t=30 and m.youtube.com/shorts/ID
 * share a key, as do /p/ID and /reel/ID on Instagram.
 */
export function mediaKey(url: string, platform: string | null = detectPlatform(url)): string {
  const source = /^https?:\/\//i.test(url) ? url : `https://${url}`;
  let parsed: URL;
  try {
    parsed = new URL(source);
  } catch {
    return url.trim().toLowerCase();
  }
  const host = parsed.hostname.toLowerCase().replace(/^(?:www|m|mobile|music)\./, '');
  if (platform === 'youtube') {
    let id: string | null = null;
    if (host === 'youtu.be') id = parsed.pathname.split('/').filter(Boolean)[0] ?? null;
    else if (parsed.pathname === '/watch') id = parsed.searchParams.get('v');
    else id = parsed.pathname.match(YOUTUBE_ID_PATH)?.[1] ?? null;
    if (id) return `youtube:${id}`;
  }
  const post = platform ? parsed.pathname.match(POST_ID_PATHS[platform] ?? /$^/) : null;
  if (post) return `${platform}:${post[1]}`;
  return `${platform ?? 'other'}:${host}${parsed.pathname.replace(/\/+$/, '') || '/'}`;
}

export function parseURLs(text: string): ParsedURL[] {
  // Split by newlines, commas, or spaces and filter empty strings
  const lines = text
    .split(/[\n,\s]+/)
    .map((line) => line.trim())
    .filter((line) => line.length > 0);

  // The same video written in different ways counts once
  const seen = new Map<string, ParsedURL>();
  const result: ParsedURL[] = [];
  for (const line of lines) {
    const platform = detectPlatform(line);
    const key = platform ? mediaKey(line, platform) : line;
    const first = seen.get(key);
    if (first) {
      first.duplicates = (first.duplicates ?? 0) + 1;
      continue;
    }
    const parsed: ParsedURL = {
      url: platform ? normalizeVideoUrl(line, platform) : line,
      platform,
      platformInfo: platform ? PLATFORMS[platform] ?? null : null,
      isValid: platform !== null,
    };
    seen.set(key, parsed);
    result.push(parsed);
  }
  return result;
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
const ROUTE_QUALITY = /^\/(360p|480p|720p|1080p|mp3)\//i;

/**
 * Quality of a short link: /mp3/<link> or /1080p/<link>. Without a prefix the
 * short link uses 720p, the same default as the API.
 */
export function parseAutoDownloadQuality(pathname: string): VideoQuality {
  const match = pathname.match(ROUTE_QUALITY);
  return (match ? match[1].toLowerCase() : '720p') as VideoQuality;
}

export function parseAutoDownloadRoute(location: RouteLocation): ParsedURL | null {
  if (!location.pathname || location.pathname === '/') return null;

  let path = location.pathname.slice(1);
  try {
    path = decodeURIComponent(path);
  } catch {
    return null;
  }

  // Optional quality prefix: /mp3/<link>, /1080p/<link>
  const qualityMatch = path.match(/^(360p|480p|720p|1080p|mp3)\/(.+)$/i);
  if (qualityMatch) path = qualityMatch[2];

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
