// API Types
export type OutputFormat = 'video' | 'audio_mp3' | 'audio_m4a';

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
  output_format: OutputFormat;
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
  icon: string;
  color: string;
}

export const PLATFORMS: Record<string, PlatformInfo> = {
  youtube: {
    name: 'YouTube',
    icon: '📺',
    color: 'text-red-500',
  },
  instagram: {
    name: 'Instagram',
    icon: '📷',
    color: 'text-pink-500',
  },
  facebook: {
    name: 'Facebook',
    icon: '👍',
    color: 'text-blue-500',
  },
  twitter: {
    name: 'Twitter/X',
    icon: '🐦',
    color: 'text-sky-400',
  },
};

export const FORMAT_OPTIONS = [
  {
    value: 'video' as OutputFormat,
    label: 'Video (Best Quality)',
    description: 'MP4 format, up to 4K',
    icon: '🎬',
  },
  {
    value: 'audio_mp3' as OutputFormat,
    label: 'Audio (MP3)',
    description: 'MP3 320kbps',
    icon: '🎵',
  },
  {
    value: 'audio_m4a' as OutputFormat,
    label: 'Audio (M4A)',
    description: 'AAC audio, better quality',
    icon: '🎶',
  },
];

// Queue-related types
export type QueueItemStatus = 'pending' | 'active' | 'completed' | 'failed' | 'cancelled';

export type QueueProcessingMode = 'sequential' | 'parallel';

export interface QueueItem {
  id: string;
  url: string;
  platform: string | null;
  format: OutputFormat;
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
