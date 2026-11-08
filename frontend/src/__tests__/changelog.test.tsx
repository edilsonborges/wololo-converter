import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { parseChangelog, getReleases } from '../changelog';
import { ReleaseNotesModal } from '../components/ReleaseNotesModal';
import packageJson from '../../package.json';

const SAMPLE = `# Changelog

Intro text.

## [1.1.0] - 2026-11-08

### Added

- New thing with \`code\`.
- Wrapped bullet that
  continues here.

### Fixed

- A fix.

## [1.0.0] - 2026-01-01

### Added

- First release.

## Earlier history

Versions before 1.0.0 were not tagged.

### [0.2.0] - 2025-12-01 — Big delivery (\`abc1234\`)

- Something old.

### [0.1.0] - 2025-11-01 — Initial (\`aaa1111\`…\`bbb2222\`)

- First commit.
`;

describe('parseChangelog', () => {
  it('parses releases, sections and wrapped bullets', () => {
    const releases = parseChangelog(SAMPLE);
    expect(releases.map((r) => r.version)).toEqual(['1.1.0', '1.0.0', '0.2.0', '0.1.0']);

    const [latest] = releases;
    expect(latest.date).toBe('2026-11-08');
    expect(latest.sections.map((s) => s.heading)).toEqual(['Added', 'Fixed']);
    expect(latest.sections[0].items).toEqual([
      'New thing with `code`.',
      'Wrapped bullet that continues here.',
    ]);
  });

  it('parses history entries with title and commit and no sub-sections', () => {
    const releases = parseChangelog(SAMPLE);
    const history = releases.find((r) => r.version === '0.2.0')!;
    expect(history.title).toBe('Big delivery');
    expect(history.commit).toBe('abc1234');
    expect(history.sections).toEqual([{ heading: null, items: ['Something old.'] }]);
    expect(releases.find((r) => r.version === '0.1.0')!.commit).toBe('aaa1111…bbb2222');
  });

  it('does not attach the "Earlier history" intro to the previous release', () => {
    const releases = parseChangelog(SAMPLE);
    const v100 = releases.find((r) => r.version === '1.0.0')!;
    expect(v100.sections).toEqual([{ heading: 'Added', items: ['First release.'] }]);
  });
});

describe('bundled CHANGELOG.md', () => {
  it('contains the current app version first and every release has content', () => {
    const releases = getReleases();
    expect(releases[0].version).toBe(packageJson.version);
    expect(releases.length).toBeGreaterThanOrEqual(10);
    for (const release of releases) {
      expect(release.sections.flatMap((s) => s.items).length).toBeGreaterThan(0);
    }
  });
});

describe('ReleaseNotesModal', () => {
  const releases = parseChangelog(SAMPLE);

  it('lists versions, marks the current one and renders inline code', () => {
    render(<ReleaseNotesModal releases={releases} currentVersion="1.1.0" onClose={() => {}} />);
    expect(screen.getByRole('dialog', { name: 'Release notes' })).toBeInTheDocument();
    expect(screen.getByText('v1.1.0')).toBeInTheDocument();
    expect(screen.getByText('v0.1.0')).toBeInTheDocument();
    expect(screen.getAllByText('Current')).toHaveLength(1);
    expect(screen.getByText('code').tagName).toBe('CODE');
    expect(screen.getByText('Big delivery')).toBeInTheDocument();
  });

  it('closes with Escape, the close button and a backdrop click', () => {
    const onClose = vi.fn();
    const { container } = render(
      <ReleaseNotesModal releases={releases} currentVersion="1.1.0" onClose={onClose} />,
    );
    fireEvent.keyDown(document, { key: 'Escape' });
    fireEvent.click(screen.getByRole('button', { name: 'Close release notes' }));
    fireEvent.mouseDown(container.firstChild as Element);
    expect(onClose).toHaveBeenCalledTimes(3);
  });
});
