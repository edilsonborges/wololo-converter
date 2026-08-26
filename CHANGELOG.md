# Changelog

All notable changes to Wololo Converter are documented here. Versions follow
[Semantic Versioning](https://semver.org/).

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
