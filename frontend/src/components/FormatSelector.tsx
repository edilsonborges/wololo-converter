import type { FC } from 'react';
import { FORMAT_OPTIONS, type OutputFormat } from '../types';
import { Icon } from './Icon';

interface FormatSelectorProps {
  selectedFormat: OutputFormat;
  onFormatChange: (format: OutputFormat) => void;
  disabled?: boolean;
}

export const FormatSelector: FC<FormatSelectorProps> = ({
  selectedFormat,
  onFormatChange,
  disabled,
}) => {
  return (
    <div className="space-y-3">
      <label className="block text-sm font-medium text-text-secondary">
        Output Format
      </label>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        {FORMAT_OPTIONS.map((option) => (
          <button
            key={option.value}
            type="button"
            onClick={() => onFormatChange(option.value)}
            disabled={disabled}
            className={`
              relative p-4 rounded-lg border-2 text-left transition-all duration-200
              ${
                selectedFormat === option.value
                  ? 'border-accent bg-accent-light'
                  : 'border-border bg-white hover:border-border-dark hover:bg-surface-secondary'
              }
              ${disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}
            `}
          >
            <div className="flex items-start gap-3">
              <div className={`${selectedFormat === option.value ? 'text-accent' : 'text-text-tertiary'}`}>
                <Icon name={option.icon} size="lg" />
              </div>
              <div>
                <div className={`font-medium ${selectedFormat === option.value ? 'text-accent' : 'text-text-primary'}`}>
                  {option.label}
                </div>
                <div className="text-sm text-text-muted">{option.description}</div>
              </div>
            </div>

            {/* Selected indicator */}
            {selectedFormat === option.value && (
              <div className="absolute top-2 right-2 text-accent">
                <Icon name="checkCircle" size="sm" />
              </div>
            )}
          </button>
        ))}
      </div>
    </div>
  );
};
