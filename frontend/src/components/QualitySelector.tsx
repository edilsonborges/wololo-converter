import type { FC } from 'react';
import type { VideoQuality } from '../types';
import { Icon } from './Icon';

interface QualitySelectorProps {
  selectedQuality: VideoQuality;
  onQualityChange: (quality: VideoQuality) => void;
  availableQualities?: number[];
  disabled?: boolean;
}

const QUALITY_OPTIONS: { value: VideoQuality; label: string; description: string; resolution?: number }[] = [
  { value: '360p', label: '360p', description: 'SD quality', resolution: 360 },
  { value: '480p', label: '480p', description: 'Standard', resolution: 480 },
  { value: '720p', label: '720p', description: 'HD', resolution: 720 },
  { value: '1080p', label: '1080p', description: 'Full HD', resolution: 1080 },
  { value: 'mp3', label: 'MP3', description: 'Audio 320kbps' },
];

export const QualitySelector: FC<QualitySelectorProps> = ({
  selectedQuality,
  onQualityChange,
  availableQualities,
  disabled,
}) => {
  const isOptionAvailable = (option: typeof QUALITY_OPTIONS[number]): boolean => {
    // MP3 is always available
    if (!option.resolution) return true;
    // If no preview loaded, all video options are enabled
    if (!availableQualities) return true;
    // Check if the resolution exists in available qualities
    return availableQualities.some((q) => q >= option.resolution!);
  };

  return (
    <div className="space-y-3">
      <label className="block text-sm font-medium text-text-secondary">
        Quality
      </label>
      <div className="flex flex-wrap gap-2">
        {QUALITY_OPTIONS.map((option) => {
          const available = isOptionAvailable(option);
          const isSelected = selectedQuality === option.value;
          const isDisabled = disabled || !available;

          return (
            <button
              key={option.value}
              type="button"
              onClick={() => onQualityChange(option.value)}
              disabled={isDisabled}
              title={!available ? 'Qualidade não disponível para este vídeo' : undefined}
              className={`
                relative px-4 py-2.5 rounded-lg border-2 text-center transition-all duration-200
                ${
                  isSelected
                    ? 'border-accent bg-accent-light'
                    : available
                      ? 'border-border bg-white hover:border-border-dark hover:bg-surface-secondary'
                      : 'border-border bg-surface-tertiary opacity-50 cursor-not-allowed'
                }
                ${isDisabled ? 'cursor-not-allowed' : 'cursor-pointer'}
                ${disabled ? 'opacity-50' : ''}
              `}
            >
              <div className="min-w-0">
                <div className={`font-medium text-sm ${isSelected ? 'text-accent' : !available ? 'text-text-muted' : 'text-text-primary'}`}>
                  {option.label}
                </div>
                <div className="text-xs text-text-muted truncate">{option.description}</div>
              </div>

              {isSelected && (
                <div className="absolute top-1 right-1 text-accent">
                  <Icon name="checkCircle" size="xs" />
                </div>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
};
