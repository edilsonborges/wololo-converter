import type { FC } from 'react';
import type { VideoQuality } from '../types';
import { Icon } from './Icon';

interface FormatSelectorProps {
  selectedFormat: VideoQuality;
  onFormatChange: (format: VideoQuality) => void;
  disabled?: boolean;
}

const QUALITY_OPTIONS: { value: VideoQuality; label: string; description: string }[] = [
  { value: '360p', label: '360p', description: 'SD quality' },
  { value: '480p', label: '480p', description: 'Standard' },
  { value: '720p', label: '720p', description: 'HD' },
  { value: '1080p', label: '1080p', description: 'Full HD' },
  { value: 'mp3', label: 'MP3', description: 'Audio 320kbps' },
];

export const FormatSelector: FC<FormatSelectorProps> = ({
  selectedFormat,
  onFormatChange,
  disabled,
}) => {
  return (
    <div className="space-y-3">
      <label className="block text-sm font-medium text-text-secondary">
        Quality
      </label>
      <div className="grid grid-cols-3 sm:grid-cols-5 gap-2">
        {QUALITY_OPTIONS.map((option) => (
          <button
            key={option.value}
            type="button"
            onClick={() => onFormatChange(option.value)}
            disabled={disabled}
            className={`
              relative p-3 rounded-lg border-2 text-center transition-all duration-200
              ${
                selectedFormat === option.value
                  ? 'border-accent bg-accent-light'
                  : 'border-border bg-white hover:border-border-dark hover:bg-surface-secondary'
              }
              ${disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}
            `}
          >
            <div className="min-w-0">
              <div className={`font-medium text-sm ${selectedFormat === option.value ? 'text-accent' : 'text-text-primary'}`}>
                {option.label}
              </div>
              <div className="text-xs text-text-muted truncate">{option.description}</div>
            </div>

            {selectedFormat === option.value && (
              <div className="absolute top-1.5 right-1.5 text-accent">
                <Icon name="checkCircle" size="xs" />
              </div>
            )}
          </button>
        ))}
      </div>
    </div>
  );
};
