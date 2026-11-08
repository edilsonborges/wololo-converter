import type { IconName } from './components/Icon';

// API Types
export type VideoQuality = '360p' | '480p' | '720p' | '1080p' | 'mp3';

export interface ResolvedTrack {
  title: string;
  artist: string;
  duration?: number | null;
  source_url?: string | null;
  video_url?: string | null;
  video_title?: string | null;
}

export interface ResolveResponse {
  album: string;
  tracks: ResolvedTrack[];
}

export interface PreviewResponse {
  title: string;
  thumbnail_url: string;
  duration: number;
  available_qualities: number[];
}

export type JobStatus =
  | 'queued'
  | 'validating'
  | 'downloading'
  | 'converting'
  | 'finalizing'
  | 'completed'
  | 'failed'
  | 'cancelled';

export interface DownloadRequest {
  url: string;
  quality: VideoQuality;
}

export interface DownloadStartResponse {
  job_id: string;
  message: string;
  status: JobStatus;
}

/** Job record returned by GET /api/jobs/{id} (fields used by the client) */
export interface JobResponse {
  id: string;
  url: string;
  status: JobStatus;
  progress: number;
  speed?: string | null;
  eta?: string | null;
  current_stage?: string | null;
  title?: string | null;
  filename?: string | null;
  error_message?: string | null;
}

export interface JobProgressUpdate {
  job_id: string;
  status: JobStatus;
  progress: number;
  speed?: string;
  eta?: string;
  current_stage?: string;
  title?: string;
  error_message?: string;
  download_ready: boolean;
}

export interface URLValidationResponse {
  valid: boolean;
  platform?: string;
  error?: string;
}

export interface HealthResponse {
  status: string;
  version: string;
  yt_dlp_version: string;
  active_downloads: number;
  temp_dir_size_mb: number;
}

// Platform info
export interface PlatformInfo {
  name: string;
  icon: IconName;
  color: string;
}

export const PLATFORMS: Record<string, PlatformInfo> = {
  youtube: {
    name: 'YouTube',
    icon: 'youtube',
    color: 'text-platform-youtube',
  },
  instagram: {
    name: 'Instagram',
    icon: 'instagram',
    color: 'text-platform-instagram',
  },
  // Facebook temporarily hidden - not working
  // facebook: {
  //   name: 'Facebook',
  //   icon: 'facebook',
  //   color: 'text-platform-facebook',
  // },
  tiktok: {
    name: 'TikTok',
    icon: 'music2',
    color: 'text-platform-tiktok',
  },
  threads: {
    name: 'Threads',
    icon: 'atSign',
    color: 'text-platform-threads',
  },
  twitter: {
    name: 'Twitter/X',
    icon: 'twitter',
    color: 'text-platform-twitter',
  },
};

// Queue-related types
export type QueueItemStatus = 'resolving' | 'pending' | 'active' | 'completed' | 'failed' | 'cancelled';

export type QueueProcessingMode = 'sequential' | 'parallel';

export interface QueueItem {
  id: string;
  url: string;
  platform: string | null;
  quality: VideoQuality;
  status: QueueItemStatus;
  jobId?: string;
  progress?: JobProgressUpdate;
  error?: string;
  addedAt: number;
  /** Display name known before the download starts (e.g. "Artist - Track") */
  label?: string;
  /** A music page link that is resolved to YouTube videos before downloading */
  musicLink?: boolean;
  /** When processing actually started (the item left the pending state) */
  startedAt?: number;
  completedAt?: number;
  autoDownload?: boolean;
}

export interface QueueConfig {
  processingMode: QueueProcessingMode;
  maxConcurrent: number; // Only used when mode is 'parallel'
}
