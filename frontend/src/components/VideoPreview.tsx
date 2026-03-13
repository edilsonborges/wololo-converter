import type { FC } from 'react';
import type { PreviewResponse } from '../types';

interface VideoPreviewProps {
  preview: PreviewResponse | null;
  isLoading: boolean;
  error: string | null;
}

function formatDuration(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (h > 0) {
    return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  }
  return `${m}:${String(s).padStart(2, '0')}`;
}

export const VideoPreview: FC<VideoPreviewProps> = ({ preview, isLoading, error }) => {
  if (isLoading) {
    return (
      <div className="animate-pulse space-y-3">
        <div className="aspect-video bg-surface-tertiary rounded-lg" />
        <div className="h-5 bg-surface-tertiary rounded w-3/4" />
        <div className="h-4 bg-surface-tertiary rounded w-1/4" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4 bg-error-light border border-error/20 rounded-lg">
        <p className="text-error-text text-sm">{error}</p>
      </div>
    );
  }

  if (!preview) {
    return null;
  }

  return (
    <div className="space-y-3">
      <div className="aspect-video bg-surface-tertiary rounded-lg overflow-hidden">
        <img
          src={preview.thumbnail_url}
          alt={preview.title}
          className="w-full h-full object-cover"
        />
      </div>
      <div>
        <h3 className="text-sm font-medium text-text-primary line-clamp-2">
          {preview.title}
        </h3>
        <p className="text-xs text-text-muted mt-1">
          {formatDuration(preview.duration)}
        </p>
      </div>
    </div>
  );
};
