import type { FC } from 'react';
import { FORMAT_OPTIONS, type OutputFormat } from '../types';

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
      <label className="block text-sm font-medium text-gray-400">
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
                  ? 'border-orange-500 bg-orange-500/10'
                  : 'border-gray-700 bg-gray-800/50 hover:border-gray-600'
              }
              ${disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}
            `}
          >
            <div className="flex items-start gap-3">
              <span className="text-2xl">{option.icon}</span>
              <div>
                <div className="font-medium text-white">{option.label}</div>
                <div className="text-sm text-gray-400">{option.description}</div>
              </div>
            </div>

            {/* Selected indicator */}
            {selectedFormat === option.value && (
              <div className="absolute top-2 right-2">
                <svg
                  className="w-5 h-5 text-orange-500"
                  fill="currentColor"
                  viewBox="0 0 20 20"
                >
                  <path
                    fillRule="evenodd"
                    d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
                    clipRule="evenodd"
                  />
                </svg>
              </div>
            )}
          </button>
        ))}
      </div>
    </div>
  );
};
