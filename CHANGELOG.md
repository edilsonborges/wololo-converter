# Changelog

All notable changes to Wololo Converter are documented here. Versions follow
[Semantic Versioning](https://semver.org/).

## [0.9.2] - 2026-11-08

### Changed

- Use the original red Wololo mascot for the iOS and Android app icons.
- Match the native apps to the website with white backgrounds, black actions, and neutral borders.

## [0.9.1] - 2026-11-08

### Fixed

- Prevent an iOS crash when saving a video to Photos or resuming a pending save after reopening the app.
- Exercise the actual Photos save path and run iOS interface checks in Release configuration.

## [0.9.0] - 2026-11-08

### Added

- Native iOS app and Share Extension with MP4 and MP3 downloads, local history, and server settings.
- Native Android app with a share target, background downloads, and gallery or music saving.
- Mobile build checks and signed Android APK artifacts in GitHub Actions.
- Optional per-person access keys and a configurable minimum mobile app version.

### Changed

- Downloads wait in a bounded server queue when all execution slots are occupied.
- Waiting time is excluded from the download timeout, and cancelling a queued item releases its place.

### Fixed

- Interrupted jobs receive a clear error after a server restart.
- Polling job progress no longer risks overwriting a finished job in the database.

## [0.8.2] - 2026-11-08

### Fixed

- Threads videos are named after the first line of the post caption (up to
  80 characters) instead of the whole multi-line caption, which produced
  filenames with line breaks that some browsers, such as Safari on iPhone,
  failed to download.
- Download filenames never contain line breaks or control characters.
- Accented characters in Threads captions are no longer garbled.

## [0.8.1] - 2026-11-08

### Fixed

- Bug fixes.

## [0.8.0] - 2026-11-08

### Added

- Click the version in the footer to open the release notes: every version
  with what was added, changed and fixed, read straight from `CHANGELOG.md`.

### Changed

- The frontend Docker image is built from the repository root so it can
  bundle the changelog; a root `.dockerignore` keeps the build context small.

## [0.7.0] - 2026-11-08

### Added

- Each queue item shows how long it took: a live timer while processing and
  the frozen total ("Took 1m 23s") once completed, failed or cancelled.
- Threads downloads report speed and ETA.

### Changed

- yt-dlp extracts metadata and downloads in a single call instead of two,
  saving one round-trip to the platform per download. The title still shows
  as soon as the download starts.
- Backend uses `logging` with timestamps instead of `print`; unhandled errors
  are logged with their traceback.

### Fixed

- `DOWNLOAD_TIMEOUT_SECONDS` is now enforced: a stuck download is stopped,
  its files removed and the job marked as failed, freeing its slot.
- `MAX_FILE_SIZE_MB` is now enforced for Threads downloads.
- Replace deprecated `datetime.utcnow()` usage.
- CI: run Playwright E2E on `ubuntu-24.04` (no Chromium build for the new
  `ubuntu-latest` image).

## [0.6.2] - 2026-11-08

### Fixed

- Cancelling a job now actually stops the yt-dlp worker thread (and Threads
  downloads), removes partial files, and keeps the job counted against the
  concurrency limit until the thread exits. A cancelled job is no longer
  reported as completed or failed afterwards.
- Persist the final job state (status, title, filename, size, duration,
  `completed_at`) to the database, so `GET /api/jobs` no longer lists every
  job as `queued`. Cancelling an already finished job no longer overwrites it.
- "Download" returns the original video after "Save as MP3" instead of the
  newer MP3 file; yt-dlp temp files (`.part`, `.ytdl`) are never served.
- The cleanup task no longer deletes directories of downloads still running
  (long downloads could be removed mid-flight after `MAX_FILE_AGE_HOURS`).
- Video preview ignores a placeholder `cookies.txt` the same way downloads do,
  instead of passing an empty cookies file to yt-dlp.

## [0.6.1] - 2026-10-10

### Fixed

- Recognize Threads `/share/...` links in the frontend and backend so shared
  videos can be downloaded as MP4 or MP3.
- Accept Threads share links through direct automatic download routes.

## [0.6.0] - 2026-08-26

### Added

- Direct automatic downloads from URLs placed after the Wololo domain.
- Automatic support for YouTube, Instagram, TikTok, Threads, and Twitter/X links.
- Automatic browser download when direct-route processing completes.
- Release and machine-update automation based on Git tags.

### Changed

- Canonicalize video URLs and remove tracking, playback-time, playlist, sharing,
  and fragment parameters before processing.
- Update yt-dlp to 2026.08.19 with browser impersonation support.
- Expand shared-link recognition for mobile YouTube, Instagram shared Reels, and
  TikTok `vt.tiktok.com` URLs.

### Fixed

- Replay terminal download state to late SSE subscribers.
- Safely deliver yt-dlp progress events from worker threads to the asyncio loop.
- Remove the unsupported YouTube `tv_embedded` client override.
- Convert Threads downloads to MP3 when audio output is selected.

## Earlier history

Versions before 0.6.0 were not tagged in Git. They are reconstructed from the
commit history and grouped by major delivery; the commits listed are the last
commit of each delivery.

### [0.5.3] - 2026-07-24 — yt-dlp hotfix (`812b7d5`)

- Update and pin yt-dlp to fix Instagram downloads.
- Align backend unit tests and Playwright specs with the quality API and UI.

### [0.5.2] - 2026-04-18 — YouTube cookies and Instagram speed (`e9f830a`)

- Support a Netscape `cookies.txt` file for YouTube in Docker deployments;
  browser cookies disabled by default.
- Instagram: stream copy when the source is already H.264, `veryfast` preset
  when re-encoding, concurrent fragment downloads and larger HTTP chunks.

### [0.5.1] - 2026-03-27 — More platforms and MP3 extraction (`2c0b00b`)

- Re-enable Instagram (posts, reels, TV) with VP9 → H.264 re-encoding for
  QuickTime compatibility; skip preview for Instagram URLs.
- New platforms: Threads (custom extractor) and TikTok.
- "Save as MP3" extracts audio from an already downloaded video.
- Detect available qualities for portrait videos.

### [0.5.0] - 2026-03-13 — Format tags and UI polish (`02f2f98`)

- Format/quality tags on queue items and in the preview; fixed-height preview.
- Quality selector only appears for a valid URL.
- Instagram temporarily disabled (yt-dlp blocked by Instagram).
- Version shown in the footer.

### [0.4.0] - 2026-03-13 — Quality selection and video preview (`6287c03`…`30f0f15`)

- `POST /api/preview` returns title, thumbnail, duration and available qualities.
- New `quality` field (360p/480p/720p/1080p/MP3) replaces `output_format`,
  with backward compatibility; yt-dlp format selection per quality.
- Avoid unnecessary re-encoding; progress split into proportional phases
  (download 0–70%, conversion 70–95%, finalization 95–100%).
- Frontend preview card with thumbnail, quality radio buttons and a smoothly
  animated progress bar.

### [0.3.0] - 2026-02-26 — Output formats, tests and CI (`8ee0939`)

- WebM, WAV, FLAC and OGG output formats alongside MP4/MP3/M4A.
- Faster FFmpeg conversion (preset `fast`, multi-threading).
- Backend (pytest), frontend (vitest) and E2E (Playwright) test suites.
- GitHub Actions CI on push and pull request.

### [0.2.0] - 2026-01-18 — UI refresh (`f4f49e7`)

- New Icon component and updated UI assets.
- Dedicated ports (frontend 47651, backend 47652).
- Video compatibility fix using FFmpeg stream copy.
- Facebook support hidden; queue history shown newest first.
- Open Graph and Twitter meta tags for link previews.

### [0.1.0] - 2026-01-17 — Initial release (`08da1ae`)

- Full-stack app: FastAPI + yt-dlp backend, React + Vite frontend.
- Downloads from YouTube, Instagram, Facebook and Twitter/X as video or audio.
- Download queue with real-time progress over Server-Sent Events.
- Docker Compose deployment.
