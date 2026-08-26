"""API routes for Wololo Converter"""
import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Dict

from fastapi import APIRouter, HTTPException, Depends, Request, Response
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from slowapi import Limiter
from slowapi.util import get_remote_address
from sse_starlette.sse import EventSourceResponse

from .config import settings
from .database import get_session, get_db_context
from .models import DownloadJob, JobStatus, OutputFormat, VideoQuality
from .schemas import (
    DownloadRequest,
    DownloadStartResponse,
    JobResponse,
    URLValidationResponse,
    HealthResponse,
    ErrorResponse,
    JobProgressUpdate,
    PreviewRequest,
    PreviewResponse,
)
from .download_service import download_service, get_yt_dlp_version, extract_video_preview, executor
from .utils import validate_url, get_directory_size, format_file_size
from .version import APP_VERSION


# Rate limiter
limiter = Limiter(key_func=get_remote_address)

# Router
router = APIRouter()

# Store for SSE connections and active download tasks
sse_connections: Dict[str, asyncio.Queue] = {}
download_tasks: Dict[str, asyncio.Task] = {}


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    temp_size = get_directory_size(settings.temp_dir)

    return HealthResponse(
        status="healthy",
        version=APP_VERSION,
        yt_dlp_version=get_yt_dlp_version(),
        active_downloads=download_service.active_count,
        temp_dir_size_mb=round(temp_size / 1024 / 1024, 2),
    )


@router.post("/validate", response_model=URLValidationResponse)
async def validate_url_endpoint(request: DownloadRequest):
    """Validate a URL without starting download"""
    is_valid, platform, error = validate_url(request.url)

    return URLValidationResponse(
        valid=is_valid,
        platform=platform,
        error=error,
    )


@router.post("/preview", response_model=PreviewResponse)
async def preview_video(request: Request, preview_request: PreviewRequest):
    """Get video metadata without downloading"""
    is_valid, platform, error = validate_url(preview_request.url)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error)

    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(executor, extract_video_preview, preview_request.url)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch video info: {str(e)}")


@router.post(
    "/download",
    response_model=DownloadStartResponse,
    responses={400: {"model": ErrorResponse}, 429: {"model": ErrorResponse}},
)
@limiter.limit(settings.rate_limit_downloads)
async def start_download(
    request: Request,
    download_request: DownloadRequest,
    db: AsyncSession = Depends(get_session),
):
    """Start a new download job"""
    # Validate URL
    is_valid, platform, error = validate_url(download_request.url)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error)

    # Check concurrent download limit
    if download_service.active_count >= settings.max_concurrent_downloads:
        raise HTTPException(
            status_code=429,
            detail=f"Too many concurrent downloads. Maximum is {settings.max_concurrent_downloads}.",
        )

    try:
        event_loop = asyncio.get_running_loop()

        # Create progress callback for SSE
        def progress_callback(update: JobProgressUpdate):
            def enqueue_update():
                queue = sse_connections.get(update.job_id)
                if not queue:
                    return
                try:
                    queue.put_nowait(update)
                except asyncio.QueueFull:
                    pass

            # yt-dlp invokes progress hooks from its worker thread.
            event_loop.call_soon_threadsafe(enqueue_update)

        # Resolve quality: use quality field, fallback to output_format for backward compat
        quality = download_request.quality
        if download_request.output_format is not None and quality == VideoQuality.Q_480P:
            # User sent deprecated output_format, map it
            if download_request.output_format in (
                OutputFormat.AUDIO_MP3, OutputFormat.AUDIO_M4A,
                OutputFormat.AUDIO_WAV, OutputFormat.AUDIO_FLAC,
                OutputFormat.AUDIO_OGG,
            ):
                quality = VideoQuality.MP3
            # else keep default video quality

        # Start download
        job_id, task, detected_platform = await download_service.start_download(
            url=download_request.url,
            quality=quality,
            progress_callback=progress_callback,
        )

        # Store task
        download_tasks[job_id] = task

        # Map quality to output_format for DB storage
        db_output_format = (
            OutputFormat.AUDIO_MP3.value if quality == VideoQuality.MP3
            else OutputFormat.VIDEO.value
        )

        # Create job in database
        job = DownloadJob(
            id=job_id,
            url=download_request.url,
            platform=detected_platform,
            output_format=db_output_format,
            quality=quality.value,
            status=JobStatus.QUEUED.value,
            created_at=datetime.utcnow(),
        )
        db.add(job)
        await db.commit()

        return DownloadStartResponse(
            job_id=job_id,
            message="Download started",
            status=JobStatus.QUEUED,
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start download: {str(e)}")


@router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job_status(job_id: str, db: AsyncSession = Depends(get_session)):
    """Get status of a download job"""
    result = await db.execute(select(DownloadJob).where(DownloadJob.id == job_id))
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Update with live progress if available
    progress = download_service.get_job_progress(job_id)
    if progress:
        job.status = progress.status.value
        job.progress = progress.progress
        job.speed = progress.speed
        job.eta = progress.eta
        job.current_stage = progress.current_stage
        job.title = progress.title

    return JobResponse.model_validate(job)


@router.get("/jobs/{job_id}/progress")
async def job_progress_sse(job_id: str, request: Request):
    """SSE endpoint for real-time progress updates"""

    # Create queue for this connection
    queue: asyncio.Queue[JobProgressUpdate] = asyncio.Queue(maxsize=50)
    sse_connections[job_id] = queue
    event_loop = asyncio.get_running_loop()

    # Register callback with download service
    def callback(update: JobProgressUpdate):
        def enqueue_update():
            try:
                queue.put_nowait(update)
            except asyncio.QueueFull:
                # Drop the oldest message if the queue is full.
                try:
                    queue.get_nowait()
                    queue.put_nowait(update)
                except Exception:
                    pass

        # Progress callbacks may run inside the yt-dlp worker thread.
        event_loop.call_soon_threadsafe(enqueue_update)

    download_service.register_callback(job_id, callback)

    async def event_generator():
        try:
            while True:
                # Check if client disconnected
                if await request.is_disconnected():
                    break

                try:
                    # Wait for next progress update with timeout
                    update = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield {
                        "event": "progress",
                        "data": update.model_dump_json(),
                    }

                    # If download is complete or failed, send final event and close
                    if update.status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]:
                        yield {
                            "event": "complete",
                            "data": update.model_dump_json(),
                        }
                        break

                except asyncio.TimeoutError:
                    # Send keepalive
                    yield {"event": "ping", "data": "{}"}

        finally:
            # Cleanup
            sse_connections.pop(job_id, None)
            download_service.unregister_callback(job_id)

    return EventSourceResponse(event_generator())


@router.get("/jobs/{job_id}/download")
async def download_file(job_id: str, db: AsyncSession = Depends(get_session)):
    """Download the completed file"""
    # Check job exists and is completed
    result = await db.execute(select(DownloadJob).where(DownloadJob.id == job_id))
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Find the file
    job_dir = settings.temp_dir / job_id
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail="Download files have expired")

    # Get files in directory (exclude part files)
    files = [f for f in job_dir.glob("*") if not f.name.endswith(".part")]

    if not files:
        raise HTTPException(status_code=404, detail="No downloadable files found")

    # Get the most recent file
    file_path = max(files, key=lambda f: f.stat().st_mtime)

    # Determine content type
    suffix = file_path.suffix.lower()
    content_types = {
        ".mp4": "video/mp4",
        ".webm": "video/webm",
        ".mkv": "video/x-matroska",
        ".mp3": "audio/mpeg",
        ".m4a": "audio/mp4",
        ".opus": "audio/opus",
        ".ogg": "audio/ogg",
    }
    content_type = content_types.get(suffix, "application/octet-stream")

    return FileResponse(
        path=str(file_path),
        filename=file_path.name,
        media_type=content_type,
    )


@router.post("/jobs/{job_id}/extract-audio")
async def extract_audio(job_id: str):
    """Extract MP3 audio from a completed video download"""
    job_dir = settings.temp_dir / job_id
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail="Download files have expired")

    # Find the video file
    video_exts = ('.mp4', '.webm', '.mkv')
    video_files = [
        f for f in job_dir.glob("*")
        if f.suffix.lower() in video_exts and not f.name.endswith(".part")
    ]
    if not video_files:
        raise HTTPException(status_code=404, detail="No video file found")

    video_file = max(video_files, key=lambda f: f.stat().st_mtime)
    audio_file = video_file.with_suffix(".mp3")

    # If already extracted, return immediately
    if audio_file.exists():
        return {
            "filename": audio_file.name,
            "file_size": audio_file.stat().st_size,
        }

    # Run ffmpeg in thread pool to avoid blocking the event loop
    import subprocess

    loop = asyncio.get_event_loop()

    def _extract():
        result = subprocess.run(
            [
                "ffmpeg", "-i", str(video_file),
                "-vn", "-acodec", "libmp3lame", "-q:a", "0",
                "-threads", "0",
                "-y", str(audio_file),
            ],
            capture_output=True,
            timeout=300,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.decode(errors="replace")[:500])

    try:
        await loop.run_in_executor(executor, _extract)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Audio extraction failed: {e}")

    return {
        "filename": audio_file.name,
        "file_size": audio_file.stat().st_size,
    }


@router.get("/jobs/{job_id}/download-audio")
async def download_audio_file(job_id: str):
    """Download extracted audio file"""
    job_dir = settings.temp_dir / job_id
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail="Download files have expired")

    audio_files = [f for f in job_dir.glob("*.mp3")]
    if not audio_files:
        raise HTTPException(status_code=404, detail="No audio file found. Extract audio first.")

    audio_file = max(audio_files, key=lambda f: f.stat().st_mtime)

    return FileResponse(
        path=str(audio_file),
        filename=audio_file.name,
        media_type="audio/mpeg",
    )


@router.delete("/jobs/{job_id}")
async def cancel_job(job_id: str, db: AsyncSession = Depends(get_session)):
    """Cancel a download job"""
    # Cancel in download service
    cancelled = download_service.cancel_job(job_id)

    # Cancel the task if exists
    if job_id in download_tasks:
        download_tasks[job_id].cancel()
        download_tasks.pop(job_id, None)

    # Update database
    await db.execute(
        update(DownloadJob)
        .where(DownloadJob.id == job_id)
        .values(status=JobStatus.CANCELLED.value)
    )
    await db.commit()

    return {"message": "Job cancelled", "job_id": job_id}


@router.get("/jobs", response_model=list[JobResponse])
async def list_jobs(
    limit: int = 20,
    offset: int = 0,
    db: AsyncSession = Depends(get_session),
):
    """List recent download jobs"""
    result = await db.execute(
        select(DownloadJob)
        .order_by(DownloadJob.created_at.desc())
        .limit(min(limit, 100))
        .offset(offset)
    )
    jobs = result.scalars().all()

    return [JobResponse.model_validate(job) for job in jobs]
