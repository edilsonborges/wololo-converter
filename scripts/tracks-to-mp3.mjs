#!/usr/bin/env node
/**
 * Find the tracks of an artlist.io album or song page on YouTube and download
 * them as MP3 through a running Wololo backend.
 *
 * Usage:
 *   node scripts/tracks-to-mp3.mjs <artlist album/song URL> [options]
 *
 * Options:
 *   --out <dir>        Output directory (default: ~/Downloads/wololo-mp3/<album>)
 *   --api <url>        Wololo backend (default: http://localhost:47652)
 *   --dry-run          Only show which YouTube video would be used per track
 *   --tolerance <s>    Max duration difference in seconds (default: max(4s, 3%))
 *
 * Requirements: Node 18+, and Playwright's Chromium from the frontend
 * (`cd frontend && npm install && npx playwright install chromium`). Artlist
 * pages sit behind a Cloudflare check, so they are read with a real browser.
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const USER_AGENT =
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0 Safari/537.36';
const SOURCE_URL_RE = /^https:\/\/(www\.)?artlist\.io\/royalty-free-music\/(album|song)\/[^/]+\/\d+/;

// Words that mark a different rendition of a song. A YouTube candidate that
// has one of these words while the Artlist title doesn't is another version.
const VARIANT_WORDS = [
  'instrumental', 'karaoke', 'remix', 'live', 'cover', 'sped', 'slowed', 'reverb',
  'nightcore', '8d', 'extended', 'acapella', 'cappella', 'mix', 'edit', 'loop', 'hour',
];

// ---------------------------------------------------------------- matching

export function normalize(text) {
  return (text || '')
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
    .trim();
}

const tokens = (text) => normalize(text).split(' ').filter(Boolean);

/** "Dale Candela - Instrumental version" -> "Dale Candela" */
export function baseTitle(title) {
  return title
    .replace(/\s*[-–]\s*[^-–]*\bversion\b\s*$/i, '')
    .replace(/\s*[([][^)\]]*\b(version|instrumental)\b[^)\]]*[)\]]\s*$/i, '')
    .trim();
}

/** "3:16", "1:02:03" or ISO "PT3M15S" -> seconds */
export function parseDuration(value) {
  if (value == null) return null;
  if (typeof value === 'number') return value;
  const iso = /^PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$/i.exec(value.trim());
  if (iso) return (+iso[1] || 0) * 3600 + (+iso[2] || 0) * 60 + (+iso[3] || 0);
  const parts = value.trim().split(':').map(Number);
  if (!parts.length || parts.some(Number.isNaN)) return null;
  return parts.reduce((total, part) => total * 60 + part, 0);
}

/**
 * Pick the YouTube video that is the same recording as the track, or null.
 * track: { title, artist, duration (s) }
 * candidates: [{ id, title, channel, duration (s) }]
 */
export function pickBestMatch(track, candidates, toleranceSeconds) {
  const wanted = new Set(tokens(baseTitle(track.title)));
  const trackWords = new Set(tokens(track.title));
  const artist = normalize(track.artist);
  const tolerance = toleranceSeconds ?? Math.max(4, track.duration * 0.03);

  const scored = [];
  for (const candidate of candidates) {
    if (candidate.duration == null) continue;
    const words = new Set(tokens(candidate.title));

    // Every word of the song name must be in the video title
    if (![...wanted].every((w) => words.has(w))) continue;

    // Same rendition: no extra variant words, and instrumental only if wanted
    if (VARIANT_WORDS.some((w) => words.has(w) && !trackWords.has(w))) continue;
    if (trackWords.has('instrumental') && !words.has('instrumental')) continue;

    const diff = Math.abs(candidate.duration - track.duration);
    if (diff > tolerance) continue;

    // Prefer the artist's own channel (incl. "Artist - Topic"), then uploads
    // that name the artist, then anything else
    let penalty = 5;
    if (artist && normalize(candidate.channel).includes(artist)) penalty = 0;
    else if (artist && normalize(candidate.title).includes(artist)) penalty = 2;
    scored.push({ candidate, score: diff + penalty, diff });
  }

  scored.sort((a, b) => a.score - b.score);
  return scored[0] ? { ...scored[0].candidate, durationDiff: scored[0].diff } : null;
}

export function searchQuery(track) {
  const instrumental = /instrumental/i.test(track.title) ? ' instrumental' : '';
  return `${track.artist} ${baseTitle(track.title)}${instrumental}`.trim();
}

export function safeFilename(name) {
  return name.replace(/[/\\?%*:|"<>\x00-\x1f]/g, '_').replace(/^[.\s-]+/, '').slice(0, 200) || 'track';
}

// ---------------------------------------------------------------- sources

function loadPlaywright() {
  const here = path.dirname(fileURLToPath(import.meta.url));
  const require = createRequire(path.join(here, '..', 'frontend', 'package.json'));
  try {
    return require('playwright');
  } catch {
    throw new Error(
      'Playwright not found. Run: cd frontend && npm install && npx playwright install chromium',
    );
  }
}

/** Read the track list (title, artist, duration) of an Artlist album or song page. */
export async function fetchTracks(url) {
  const { chromium } = loadPlaywright();
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ userAgent: USER_AGENT });
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 });
    await page
      .waitForFunction(() => !/just a moment/i.test(document.title), null, { timeout: 30000 })
      .catch(() => {
        throw new Error('Blocked by the Cloudflare check; try again in a minute.');
      });
    await page.waitForSelector('h1', { timeout: 30000 });

    if (/\/album\//.test(url)) {
      await page.waitForSelector('[data-testid="AudioDuration"]', { timeout: 30000 });
      const album = (await page.locator('h1').first().innerText()).trim();
      const rows = await page.evaluate(() =>
        [...document.querySelectorAll('[data-testid="AudioDuration"]')].map((durationEl) => {
          let row = durationEl;
          while (row && !row.querySelector('[data-testid="artist-name"]')) row = row.parentElement;
          const link = row?.querySelector('a[href*="/royalty-free-music/song/"]');
          return {
            title: link?.innerText.trim(),
            artist: row?.querySelector('[data-testid="artist-name"]')?.innerText.trim(),
            duration: durationEl.innerText.trim(),
          };
        }),
      );
      const tracks = rows
        .filter((r) => r.title && r.artist)
        .map((r) => ({ ...r, duration: parseDuration(r.duration) }));
      return { album, tracks };
    }

    // Song page: schema.org MusicRecording JSON-LD
    const recording = await page.evaluate(() => {
      for (const s of document.querySelectorAll('script[type="application/ld+json"]')) {
        try {
          const data = JSON.parse(s.textContent);
          if (data['@type'] === 'MusicRecording') return data;
        } catch {
          /* ignore */
        }
      }
      return null;
    });
    if (!recording) throw new Error('Could not read the song details from the page.');
    const track = {
      title: recording.name,
      artist: recording.byArtist?.name || recording.producer?.name || '',
      duration: parseDuration(recording.duration),
    };
    return { album: track.title, tracks: [track] };
  } finally {
    await browser.close();
  }
}

/** Search YouTube and return [{ id, title, channel, duration }]. */
export async function searchYouTube(query) {
  const url = `https://www.youtube.com/results?search_query=${encodeURIComponent(query)}&hl=en&gl=US`;
  const res = await fetch(url, {
    headers: { 'User-Agent': USER_AGENT, 'Accept-Language': 'en-US,en;q=0.9', Cookie: 'SOCS=CAI' },
  });
  if (!res.ok) throw new Error(`YouTube search failed (${res.status})`);
  const match = (await res.text()).match(/var ytInitialData = (\{.*?\});<\/script>/s);
  if (!match) throw new Error('Could not parse YouTube search results');

  const videos = [];
  (function walk(node) {
    if (!node || typeof node !== 'object') return;
    if (node.videoRenderer) videos.push(node.videoRenderer);
    for (const value of Object.values(node)) walk(value);
  })(JSON.parse(match[1]));

  return videos.map((v) => ({
    id: v.videoId,
    title: (v.title?.runs || []).map((r) => r.text).join(''),
    channel: v.ownerText?.runs?.[0]?.text || '',
    duration: parseDuration(v.lengthText?.simpleText),
  }));
}

// ---------------------------------------------------------------- download

async function api(base, pathname, init) {
  const res = await fetch(new URL(pathname, base), init);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* not JSON */
    }
    throw new Error(`${pathname}: ${res.status} ${typeof detail === 'string' ? detail : JSON.stringify(detail)}`);
  }
  return res;
}

async function downloadMp3(base, videoId, destination) {
  const start = await api(base, '/api/download', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url: `https://www.youtube.com/watch?v=${videoId}`, quality: 'mp3' }),
  });
  const { job_id: jobId } = await start.json();

  const deadline = Date.now() + 15 * 60 * 1000;
  for (;;) {
    const job = await (await api(base, `/api/jobs/${jobId}`)).json();
    if (job.status === 'completed') break;
    if (job.status === 'failed' || job.status === 'cancelled') {
      throw new Error(job.error_message || `job ${job.status}`);
    }
    if (Date.now() > deadline) throw new Error('timed out waiting for the download');
    await new Promise((r) => setTimeout(r, 1500));
  }

  const file = await api(base, `/api/jobs/${jobId}/download`);
  fs.writeFileSync(destination, Buffer.from(await file.arrayBuffer()));
}

// ---------------------------------------------------------------- cli

function parseArgs(argv) {
  const args = { url: null, out: null, api: 'http://localhost:47652', dryRun: false, tolerance: undefined };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--out') args.out = argv[++i];
    else if (a === '--api') args.api = argv[++i];
    else if (a === '--dry-run') args.dryRun = true;
    else if (a === '--tolerance') args.tolerance = Number(argv[++i]);
    else if (a === '-h' || a === '--help') args.help = true;
    else if (!args.url) args.url = a;
    else throw new Error(`Unexpected argument: ${a}`);
  }
  return args;
}

const fmt = (s) => (s == null ? '?' : `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, '0')}`);

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.help || !args.url) {
    console.log('Usage: node scripts/tracks-to-mp3.mjs <artlist album/song URL> [--out dir] [--api url] [--dry-run] [--tolerance s]');
    process.exit(args.help ? 0 : 1);
  }
  if (!SOURCE_URL_RE.test(args.url)) {
    throw new Error('Expected an artlist.io /royalty-free-music/album/... or /song/... URL');
  }

  if (!args.dryRun) {
    await api(args.api, '/api/health').catch((e) => {
      throw new Error(`Wololo backend not reachable at ${args.api} (${e.message})`);
    });
  }

  console.log('Reading track list...');
  const { album, tracks } = await fetchTracks(args.url);
  if (!tracks.length) throw new Error('No tracks found on the page');
  console.log(`${album}: ${tracks.length} track(s)\n`);

  const outDir = args.out || path.join(os.homedir(), 'Downloads', 'wololo-mp3', safeFilename(album));
  if (!args.dryRun) fs.mkdirSync(outDir, { recursive: true });

  const summary = [];
  for (const [index, track] of tracks.entries()) {
    const label = `[${index + 1}/${tracks.length}] ${track.artist} - ${track.title} (${fmt(track.duration)})`;
    console.log(label);
    try {
      const candidates = await searchYouTube(searchQuery(track));
      const match = pickBestMatch(track, candidates, args.tolerance);
      if (!match) {
        console.log('  ✗ no matching video on YouTube, skipped\n');
        summary.push({ track, status: 'not found' });
        continue;
      }
      console.log(`  → ${match.title} — ${match.channel} (${fmt(match.duration)}) https://youtu.be/${match.id}`);

      if (args.dryRun) {
        summary.push({ track, status: 'match', match });
        console.log();
        continue;
      }

      const destination = path.join(outDir, `${safeFilename(`${track.artist} - ${track.title}`)}.mp3`);
      if (fs.existsSync(destination)) {
        console.log('  ✓ already downloaded\n');
        summary.push({ track, status: 'exists', match });
        continue;
      }
      await downloadMp3(args.api, match.id, destination);
      console.log(`  ✓ saved ${destination}\n`);
      summary.push({ track, status: 'downloaded', match });
    } catch (e) {
      console.log(`  ✗ ${e.message}\n`);
      summary.push({ track, status: 'error', error: e.message });
    }
  }

  const count = (s) => summary.filter((x) => x.status === s).length;
  console.log(
    args.dryRun
      ? `Matched ${count('match')}/${tracks.length}, not found ${count('not found')}.`
      : `Downloaded ${count('downloaded')}, already present ${count('exists')}, not found ${count('not found')}, errors ${count('error')}.` +
          `\nFolder: ${outDir}`,
  );
  if (count('error')) process.exitCode = 1;
}

if (process.argv[1] && fileURLToPath(import.meta.url) === path.resolve(process.argv[1])) {
  main().catch((e) => {
    console.error(`Error: ${e.message}`);
    process.exit(1);
  });
}
