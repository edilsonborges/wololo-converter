import type { IconName } from './components/Icon';

// API Types
export type VideoQuality = '360p' | '480p' | '720p' | '1080p' | 'mp3';

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
  twitter: {
    name: 'Twitter/X',
    icon: 'twitter',
    color: 'text-platform-twitter',
  },
};

// Queue-related types
export type QueueItemStatus = 'pending' | 'active' | 'completed' | 'failed' | 'cancelled';

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
  completedAt?: number;
}

export interface QueueConfig {
  processingMode: QueueProcessingMode;
  maxConcurrent: number; // Only used when mode is 'parallel'
}
