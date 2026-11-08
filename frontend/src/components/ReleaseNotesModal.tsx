import { Fragment, useEffect, useRef, type FC, type ReactNode } from 'react';
import type { Release } from '../changelog';
import { Icon } from './Icon';

interface ReleaseNotesModalProps {
  releases: Release[];
  currentVersion: string;
  onClose: () => void;
}

/** Render `inline code` spans from changelog text without using raw HTML. */
function renderInline(text: string): ReactNode {
  return text.split(/(`[^`]+`)/g).map((part, i) =>
    part.startsWith('`') && part.endsWith('`') && part.length > 1 ? (
      <code key={i} className="px-1 py-0.5 rounded bg-surface-tertiary text-[0.85em] font-mono">
        {part.slice(1, -1)}
      </code>
    ) : (
      <Fragment key={i}>{part}</Fragment>
    ),
  );
}

function formatDate(isoDate: string): string {
  const [year, month, day] = isoDate.split('-').map(Number);
  return new Date(Date.UTC(year, month - 1, day)).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    timeZone: 'UTC',
  });
}

const SECTION_STYLES: Record<string, string> = {
  Added: 'bg-success-light text-success-text',
  Changed: 'bg-info-light text-info-text',
  Fixed: 'bg-warning-light text-warning-text',
  Removed: 'bg-error-light text-error-text',
  Security: 'bg-error-light text-error-text',
};

export const ReleaseNotesModal: FC<ReleaseNotesModalProps> = ({ releases, currentVersion, onClose }) => {
  const closeButtonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const previouslyFocused = document.activeElement as HTMLElement | null;
    closeButtonRef.current?.focus();
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('keydown', onKeyDown);
      document.body.style.overflow = previousOverflow;
      previouslyFocused?.focus?.();
    };
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="release-notes-title"
        className="w-full max-w-2xl max-h-[85vh] flex flex-col rounded-xl bg-surface shadow-xl border border-border text-left"
      >
        <div className="flex items-center justify-between px-6 py-4 border-b border-border-light">
          <div>
            <h2 id="release-notes-title" className="text-lg font-semibold text-text-primary">
              Release notes
            </h2>
            <p className="text-xs text-text-muted">What changed in each version of Wololo Converter</p>
          </div>
          <button
            ref={closeButtonRef}
            type="button"
            onClick={onClose}
            className="p-2 rounded-lg text-text-tertiary hover:bg-surface-tertiary hover:text-text-primary transition-colors"
            aria-label="Close release notes"
          >
            <Icon name="x" size="sm" />
          </button>
        </div>

        <div className="overflow-y-auto px-6 py-4 space-y-6">
          {releases.length === 0 && (
            <p className="text-sm text-text-muted">No release notes available.</p>
          )}
          {releases.map((release) => (
            <section key={release.version} aria-label={`Version ${release.version}`}>
              <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
                <h3 className="text-base font-semibold text-text-primary">v{release.version}</h3>
                {release.version === currentVersion && (
                  <span className="text-[11px] px-2 py-0.5 rounded-full bg-accent-light text-accent font-medium">
                    Current
                  </span>
                )}
                <span className="text-xs text-text-muted">{formatDate(release.date)}</span>
              </div>
              {release.title && (
                <p className="mt-0.5 text-sm font-medium text-text-secondary">{release.title}</p>
              )}

              {release.sections.map((section, i) => (
                <div key={i} className="mt-3">
                  {section.heading && (
                    <span
                      className={`inline-block text-[11px] px-2 py-0.5 rounded-full font-medium ${
                        SECTION_STYLES[section.heading] ?? 'bg-surface-tertiary text-text-secondary'
                      }`}
                    >
                      {section.heading}
                    </span>
                  )}
                  <ul className="mt-2 space-y-1.5 list-disc pl-5 text-sm text-text-secondary marker:text-text-muted">
                    {section.items.map((itemText, j) => (
                      <li key={j}>{renderInline(itemText)}</li>
                    ))}
                  </ul>
                </div>
              ))}

              {release.commit && (
                <p className="mt-2 text-xs text-text-muted">
                  Commit <code className="font-mono">{release.commit}</code>
                </p>
              )}
            </section>
          ))}
        </div>
      </div>
    </div>
  );
};
