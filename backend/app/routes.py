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
from .models import DownloadJob, JobStatus, OutputFormat
from .schemas import (
    DownloadRequest,
    DownloadStartResponse,
    JobResponse,
    URLValidationResponse,
    HealthResponse,
    ErrorResponse,
    JobProgressUpdate,
)
from .download_service import download_service, get_yt_dlp_version
from .utils import validate_url, get_directory_size, format_file_size


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
        version="1.0.0",
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
        # Create progress callback for SSE
        def progress_callback(update: JobProgressUpdate):
            if update.job_id in sse_connections:
                try:
                    sse_connections[update.job_id].put_nowait(update)
                except asyncio.QueueFull:
                    pass

        # Start download
        job_id, task, detected_platform = await download_service.start_download(
            url=download_request.url,
            output_format=download_request.output_format,
            progress_callback=progress_callback,
        )

        # Store task
        download_tasks[job_id] = task

        # Create job in database
        job = DownloadJob(
            id=job_id,
            url=download_request.url,
            platform=detected_platform,
            output_format=download_request.output_format.value,
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

    # Register callback with download service
    def callback(update: JobProgressUpdate):
        try:
            queue.put_nowait(update)
        except asyncio.QueueFull:
            # Drop old messages if queue is full
            try:
                queue.get_nowait()
                queue.put_nowait(update)
            except Exception:
                pass

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
