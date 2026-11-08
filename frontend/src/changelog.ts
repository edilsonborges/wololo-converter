/**
 * Parser for the repository's CHANGELOG.md (Keep a Changelog style), used by
 * the release notes modal. CHANGELOG.md is the single source of truth: it is
 * bundled at build time, so every release shows up automatically.
 */
import changelogMarkdown from '../../CHANGELOG.md?raw';

export interface ReleaseSection {
  heading: string | null;
  items: string[];
}

export interface Release {
  version: string;
  date: string;
  /** Short name of the delivery (used by the reconstructed history entries) */
  title?: string;
  /** Commit reference(s) of the delivery, e.g. "812b7d5" */
  commit?: string;
  sections: ReleaseSection[];
}

// "## [0.6.2] - 2026-11-08" or "### [0.5.3] - 2026-07-24 — yt-dlp hotfix (`812b7d5`)"
const RELEASE_RE = /^#{2,3} \[(\d+\.\d+\.\d+)\] - (\d{4}-\d{2}-\d{2})(?:\s+[—-]\s+(.+?))?(?:\s+\(([^()]*`[^()]*)\))?\s*$/;
const SECTION_RE = /^#{3,4} (.+?)\s*$/;
const H2_RE = /^## /;

export function parseChangelog(markdown: string): Release[] {
  const releases: Release[] = [];
  let release: Release | null = null;
  let section: ReleaseSection | null = null;
  let item: string[] | null = null;

  const flushItem = () => {
    if (item && section) section.items.push(item.join(' '));
    item = null;
  };

  for (const rawLine of markdown.split(/\r?\n/)) {
    const line = rawLine.trimEnd();
    const releaseMatch = RELEASE_RE.exec(line);

    if (releaseMatch) {
      flushItem();
      const [, version, date, title, commit] = releaseMatch;
      release = {
        version,
        date,
        title: title?.trim(),
        commit: commit?.replace(/`/g, '').trim(),
        sections: [],
      };
      releases.push(release);
      section = null;
      continue;
    }

    if (H2_RE.test(line)) {
      // A non-release level-2 heading (e.g. "Earlier history") ends the release
      flushItem();
      release = null;
      section = null;
      continue;
    }

    if (!release) continue;

    const sectionMatch = SECTION_RE.exec(line);
    if (sectionMatch) {
      flushItem();
      section = { heading: sectionMatch[1], items: [] };
      release.sections.push(section);
      continue;
    }

    if (/^\s*- /.test(line)) {
      flushItem();
      if (!section) {
        section = { heading: null, items: [] };
        release.sections.push(section);
      }
      item = [line.replace(/^\s*- /, '').trim()];
      continue;
    }

    if (item && /^\s+\S/.test(line)) {
      // Wrapped continuation of the current bullet
      item.push(line.trim());
      continue;
    }

    flushItem();
  }
  flushItem();

  return releases;
}

let cached: Release[] | null = null;

export function getReleases(): Release[] {
  cached ??= parseChangelog(changelogMarkdown);
  return cached;
}
