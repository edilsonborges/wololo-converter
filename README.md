# Wololo Converter

A personal-use web application for downloading videos and audio from social networks.

## Supported Platforms

- YouTube (videos, shorts)
- Instagram (posts, reels)
- Facebook (videos)
- Twitter/X (videos)

## Features

- Download videos in best quality (up to 4K)
- Extract audio only (MP3 or M4A)
- Real-time progress tracking with SSE
- Automatic file cleanup
- Rate limiting for stability
- Secure URL validation (SSRF protection)

## Tech Stack

### Backend
- **Python 3.12** with FastAPI
- **yt-dlp** for video/audio extraction
- **SQLite** with async SQLAlchemy for job tracking
- **SSE** (Server-Sent Events) for real-time progress

### Frontend
- **React 18** with TypeScript
- **Vite** for development and building
- **Tailwind CSS** for styling

### Infrastructure
- **Docker** + **Docker Compose** for deployment
- **Nginx** as reverse proxy

## Quick Start

### Development

1. **Backend**:
```bash
cd backend
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

2. **Frontend**:
```bash
cd frontend
npm install
npm run dev
```

### Production (Docker)

```bash
docker-compose up -d --build
```

The application will be available at:
- Frontend: http://localhost
- API: http://localhost:8000/docs

## Configuration

See `backend/.env.example` for available configuration options:

| Variable | Default | Description |
|----------|---------|-------------|
| DEBUG | false | Enable debug mode |
| MAX_CONCURRENT_DOWNLOADS | 3 | Max parallel downloads |
| MAX_FILE_AGE_HOURS | 1 | Auto-cleanup after N hours |
| MAX_FILE_SIZE_MB | 10000 | Max file size (10GB) |
| RATE_LIMIT_DOWNLOADS | 10/minute | Rate limiting |

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /api/health | Health check |
| POST | /api/validate | Validate URL |
| POST | /api/download | Start download |
| GET | /api/jobs/{id} | Get job status |
| GET | /api/jobs/{id}/progress | SSE progress stream |
| GET | /api/jobs/{id}/download | Download file |
| DELETE | /api/jobs/{id} | Cancel job |

## Architecture

```
┌─────────────────┐     ┌─────────────────┐
│                 │     │                 │
│    Frontend     │────▶│    Backend      │
│  (React/Vite)   │     │   (FastAPI)     │
│                 │     │                 │
└─────────────────┘     └────────┬────────┘
                                 │
                                 ▼
                        ┌─────────────────┐
                        │                 │
                        │     yt-dlp      │
                        │                 │
                        └────────┬────────┘
                                 │
                                 ▼
                        ┌─────────────────┐
                        │                 │
                        │  Social Media   │
                        │   Platforms     │
                        │                 │
                        └─────────────────┘
```

## Security Considerations

1. **URL Validation**: Only whitelisted domains are allowed
2. **Path Traversal**: Filenames are sanitized
3. **Rate Limiting**: Prevents abuse
4. **File Cleanup**: Automatic removal of old files
5. **No User Auth**: Intended for personal/local use only

## Legal Notice

This tool is for personal use only. Respect:
- Copyright laws in your jurisdiction
- Platform terms of service
- Content creators' rights

Do not use for:
- Commercial purposes
- Content you don't have rights to download
- Bypassing DRM or other protection measures

## License

MIT - Personal use only.
