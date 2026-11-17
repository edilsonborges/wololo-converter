# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Wololo Converter is a personal-use web application for downloading videos and audio from YouTube, Instagram, TikTok, Facebook, and Twitter/X. It uses yt-dlp under the hood with a FastAPI backend and React frontend.

## Commands

### Backend (from `backend/`)
```bash
# Setup
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Run dev server (port 47652)
uvicorn app.main:app --reload

# Run all tests
pip install -r requirements-test.txt
pytest

# Run a single test file or test
pytest tests/test_routes.py
pytest tests/test_utils.py::test_validate_url_youtube
```

### Frontend (from `frontend/`)
```bash
# Setup & dev server (port 47651)
npm install
npm run dev

# Build
npm run build        # runs tsc && vite build

# Tests
npm run test         # vitest run (single pass)
npm run test:watch   # vitest (watch mode)
npm run test:e2e     # playwright test

# Lint
npm run lint         # eslint
```

### Production
```bash
docker-compose up -d --build
# Frontend: http://localhost:47651 | Backend API: http://localhost:47652
```

## Architecture

**Backend** (`backend/app/`) — Python 3.12, FastAPI:
- `main.py` — App entrypoint with lifespan (DB init, background cleanup task), CORS, rate limiter
- `routes.py` — All API routes under `/api` prefix. Manages SSE connections (`sse_connections` dict) and active download tasks (`download_tasks` dict) at module level
- `download_service.py` — Core download logic. `DownloadService` singleton manages yt-dlp downloads in a `ThreadPoolExecutor` (yt-dlp is blocking). `DownloadProgress` tracks per-job state with progress phases: download (0-70%), conversion (70-95%), finalization (95-100%). Uses interpolation timers during conversion phase for smooth progress
- `models.py` — SQLAlchemy models (`DownloadJob`, `JobStats`) and enums (`JobStatus`, `OutputFormat`, `VideoQuality`)
- `schemas.py` — Pydantic schemas for request/response validation
- `config.py` — `Settings` class using pydantic-settings, reads from `.env`
- `database.py` — Async SQLAlchemy with SQLite (aiosqlite), `StaticPool`
- `utils.py` — URL validation (domain whitelist), file cleanup, sanitization

**Frontend** (`frontend/src/`) — React 18, TypeScript, Vite, Tailwind CSS:
- `App.tsx` — Main component: URL input, video preview, quality selector, queue manager
- `api.ts` — API client with SSE subscription (`EventSource`) for real-time progress
- `types.ts` — Shared TypeScript types mirroring backend enums/schemas
- `hooks/useQueueManager.ts` — Core hook for download queue logic (sequential/parallel processing, SSE lifecycle)
- `components/` — `MultiURLInput`, `QueueManager`, `QualitySelector`, `VideoPreview`, `ProgressCard`, `SmoothProgressBar`, `Icon`

**Agent access**: `GET /api/download?url=<encoded URL>[&quality=...]` (default 720p) waits `LINK_DOWNLOAD_WAIT_SECONDS` (25 s) and returns the file, or `202` with `status_url`/`download_url`. Agent guide in `frontend/public/llms.txt`; OpenAPI at `/api/openapi.json`; `robots.txt` blocks `/api/` except the contract. Short links: `/<video link>` and `/<quality>/<video link>` go to the SPA for browsers (Accept text/html, see `parseAutoDownloadRoute`) and to `GET /api/d/...` for other clients; `/d/<link>` always hits the API (nginx passes `$request_uri` raw). Keep `llms.txt` in sync when the API changes.

**Status & admin**: `monitoring.py` runs a background loop (every `STATUS_CHECK_INTERVAL_SECONDS`) that probes the website (`STATUS_SITE_URL`) and the API into `status_checks`, and samples CPU/memory/disk into `system_samples`. `GET /api/status` builds the 90-day page from those probes; only the website component is public (`PUBLIC_COMPONENTS`), the API probe stays internal. `admin.py` serves `/api/admin/*` behind `ADMIN_PASSWORD` (signed cookie scoped to `/api/admin`); the SPA routes `/status`, `/login` and `/admin` in `main.tsx`. Jobs store `client_ip` (CF-Connecting-IP first), `client_name` (API key name), `source` (web/app/link) and `user_agent`; new columns are added in `database.add_missing_job_columns`. Days before the monitor started come from `status_backfill`, filled by `scripts/backfill-status.sh` (tunnel log + Cloudflare analytics via a read-only token in `~/.config/cloudflare/analytics-token`; re-runnable; `--dry-run` to preview).

**Communication flow**: Frontend calls REST endpoints to start downloads, then subscribes to SSE (`/api/jobs/{id}/progress`) for real-time progress updates. The backend runs yt-dlp in a thread pool and pushes progress via `asyncio.Queue` to SSE connections.

## Key Design Decisions

- yt-dlp runs in `ThreadPoolExecutor` because it's synchronous — all async code goes through `run_in_executor`
- Instagram videos get re-encoded to H.264 (VP9 → libx264) for QuickTime compatibility; other platforms use stream copy
- `quality` field replaces deprecated `output_format` field — routes handle backward compat mapping
- Frontend preview is skipped for Instagram URLs (slows down UX)
- Vite dev server proxies `/api` to backend port 47652
- Backend port: 47652, Frontend port: 47651
- Tests use in-memory SQLite via `conftest.py` fixtures (`db_session`, `client`)
- `pytest.ini` sets `asyncio_mode = auto` — no need for `@pytest.mark.asyncio`
