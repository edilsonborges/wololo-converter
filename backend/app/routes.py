"""API routes for Wololo Converter"""
import asyncio
import json
import logging
import re
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Dict
from urllib.parse import unquote, urlencode

from fastapi import APIRouter, HTTPException, Depends, Query, Request, Response
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from slowapi import Limiter
from sse_starlette.sse import EventSourceResponse

from .config import settings
from .access import api_key_name, client_ip, rate_limit_identity, validate_api_key
from .database import get_session, get_db_context
from .models import DownloadJob, JobStatus, OutputFormat, VideoQuality, utcnow
from .schemas import (
    DownloadAcceptedResponse,
    DownloadFailedResponse,
    DownloadRequest,
    DownloadStartResponse,
    JobResponse,
    URLValidationResponse,
    HealthResponse,
    ErrorResponse,
    JobProgressUpdate,
    PreviewRequest,
    PreviewResponse,
    ResolveRequest,
    ResolveResponse,
)
from . import monitoring, music_links
from .download_service import (
    TEMP_SUFFIXES,
    DownloadProgress,
    DownloadQueueFull,
    download_service,
    get_yt_dlp_version,
    extract_video_preview,
    executor,
)
from .utils import validate_url, get_directory_size, format_file_size
from .version import APP_VERSION


logger = logging.getLogger(__name__)

# Rate limiter
limiter = Limiter(key_func=rate_limit_identity)

# Router
router = APIRouter(dependencies=[Depends(validate_api_key)])

# Store for SSE connections and active download tasks
sse_connections: Dict[str, asyncio.Queue] = {}
download_tasks: Dict[str, asyncio.Task] = {}

TERMINAL_STATUSES = (JobStatus.COMPLETED.value, JobStatus.FAILED.value, JobStatus.CANCELLED.value)
VIDEO_EXTENSIONS = (".mp4", ".webm", ".mkv")


async def persist_job_result(progress: DownloadProgress, result: dict) -> None:
    """Store the terminal state of a job in the database."""
    values = {
        "status": progress.status.value,
        "progress": progress.progress,
        "speed": None,
        "eta": None,
        "current_stage": progress.current_stage,
        "error_message": progress.error_message,
        "completed_at": utcnow(),
        "started_at": progress.started_at,
    }
    if progress.title:
        values["title"] = progress.title
    if result.get("success"):
        values.update(
            title=result.get("title") or progress.title,
            filename=result.get("filename"),
            file_size=result.get("file_size"),
            duration=round(result["duration"]) if result.get("duration") is not None else None,
            thumbnail_url=result.get("thumbnail_url"),
        )

    async with get_db_context() as db:
        await db.execute(
            update(DownloadJob).where(DownloadJob.id == progress.job_id).values(**values)
        )


CONTENT_TYPES = {
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".mkv": "video/x-matroska",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".opus": "audio/opus",
    ".ogg": "audio/ogg",
}


def file_response(file_path: Path) -> FileResponse:
    """Send a finished file as an attachment."""
    return FileResponse(
        path=str(file_path),
        filename=file_path.name,
        media_type=CONTENT_TYPES.get(file_path.suffix.lower(), "application/octet-stream"),
    )


def _servable_files(job_dir: Path) -> list[Path]:
    return [
        f for f in job_dir.glob("*")
        if f.is_file() and not f.name.endswith(TEMP_SUFFIXES)
    ]


def find_primary_file(job_dir: Path, job: DownloadJob) -> Path | None:
    """Find the file produced by the job itself (not a later audio extraction)."""
    files = _servable_files(job_dir)
    if not files:
        return None

    if job.filename:
        recorded = job_dir / job.filename
        if recorded in files:
            return recorded

    if job.quality != VideoQuality.MP3.value:
        videos = [f for f in files if f.suffix.lower() in VIDEO_EXTENSIONS]
        if videos:
            return max(videos, key=lambda f: f.stat().st_mtime)

    return max(files, key=lambda f: f.stat().st_mtime)


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    temp_size = get_directory_size(settings.temp_dir)

    return HealthResponse(
        status="healthy",
        version=APP_VERSION,
        min_app_version=settings.min_app_version,
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
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(executor, extract_video_preview, preview_request.url)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch video info: {str(e)}")


@router.post("/resolve", response_model=ResolveResponse)
@limiter.limit("10/minute")
async def resolve_music_link(request: Request, resolve_request: ResolveRequest):
    """Resolve a music page link into the matching YouTube video of each track"""
    url = resolve_request.url.strip()
    if not music_links.is_music_link(url):
        raise HTTPException(status_code=400, detail="Unsupported link")

    loop = asyncio.get_running_loop()
    try:
        return await asyncio.wait_for(
            loop.run_in_executor(music_links.browser_executor, music_links.resolve, url),
            timeout=180,
        )
    except ValueError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Timed out reading the music page")
    except Exception as e:
        logger.exception("Failed to resolve %s", url)
        raise HTTPException(status_code=502, detail=f"Could not read the music page: {e}")


async def queue_download(
    url: str,
    quality: VideoQuality,
    db: AsyncSession,
    platform: str,
    request: Request,
    source: str,
) -> tuple[str, asyncio.Task]:
    """Create the job row and hand the download to the shared queue."""
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

    # Map quality to output_format for DB storage
    db_output_format = (
        OutputFormat.AUDIO_MP3.value if quality == VideoQuality.MP3
        else OutputFormat.VIDEO.value
    )

    # Create the job row before the download starts so the final state
    # can always be persisted, even for downloads that finish instantly.
    job_id = str(uuid.uuid4())
    job = DownloadJob(
        id=job_id,
        url=url,
        platform=platform,
        output_format=db_output_format,
        quality=quality.value,
        status=JobStatus.QUEUED.value,
        created_at=utcnow(),
        client_ip=client_ip(request),
        client_name=api_key_name(request),
        source=source,
        user_agent=(request.headers.get("User-Agent") or "")[:500] or None,
    )

    async def persist_queued_job():
        db.add(job)
        await db.commit()

    job_id, task, _ = await download_service.start_download(
        url=url,
        quality=quality,
        progress_callback=progress_callback,
        job_id=job_id,
        on_finish=persist_job_result,
        on_enqueue=persist_queued_job,
    )

    # Track the task until it finishes
    download_tasks[job_id] = task
    task.add_done_callback(lambda _t, jid=job_id: download_tasks.pop(jid, None))
    return job_id, task


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

    try:
        # The apps send an access key; the website doesn't
        source = "app" if request.headers.get("X-Wololo-Key") else "web"
        job_id, _ = await queue_download(download_request.url, quality, db, platform, request, source)
        return DownloadStartResponse(
            job_id=job_id,
            message="Download started",
            status=JobStatus.QUEUED,
        )

    except DownloadQueueFull as e:
        raise HTTPException(status_code=429, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start download: {str(e)}")


LINK_QUERY_PARAMS = {"url", "quality"}


def link_source_url(request: Request, url: str) -> str:
    """Rebuild a source URL that was pasted without percent-encoding.

    In ``?url=https://www.youtube.com/watch?feature=share&v=ID`` the ``&``
    ends the ``url`` parameter early and ``v`` arrives as a parameter of its
    own. Parameters this endpoint doesn't know belong to the source URL, so
    they are appended back in their original order.
    """
    extras = [
        (key, value) for key, value in request.query_params.multi_items()
        if key not in LINK_QUERY_PARAMS
    ]
    if not extras:
        return url
    separator = "&" if "?" in url else "?"
    return url + separator + urlencode(extras)


@router.get(
    "/download",
    summary="Download a video from a single link",
    status_code=200,
    response_class=FileResponse,
    responses={
        200: {
            "description": "The finished file, sent as an attachment "
            "(MP4 for video qualities, MP3 for `mp3`).",
            "content": {
                "video/mp4": {"schema": {"type": "string", "format": "binary"}},
                "audio/mpeg": {"schema": {"type": "string", "format": "binary"}},
            },
        },
        202: {
            "model": DownloadAcceptedResponse,
            "description": "Still downloading. Poll `status_url` until `status` is "
            "`completed`, then GET `download_url`. The `Location` header carries "
            "`status_url` and `Retry-After` the suggested polling interval.",
        },
        400: {"model": ErrorResponse, "description": "Invalid or unsupported URL"},
        401: {"model": ErrorResponse, "description": "Invalid `X-Wololo-Key` (the key is optional)"},
        422: {"model": DownloadFailedResponse, "description": "The download failed, or a parameter is invalid"},
        429: {"model": ErrorResponse, "description": "Rate limit reached or download queue full"},
    },
)
@limiter.limit(settings.rate_limit_downloads)
async def download_from_link(
    request: Request,
    url: str = Query(
        ...,
        min_length=10,
        max_length=2048,
        description="Full URL of the video, percent-encoded "
        "(e.g. `https%3A%2F%2Fwww.youtube.com%2Fwatch%3Fv%3D379BagNcNf4`).",
    ),
    quality: VideoQuality = Query(
        VideoQuality.Q_720P,
        description="Video height or `mp3`. Defaults to 720p: the best available "
        "up to 720p, never upscaled.",
    ),
    db: AsyncSession = Depends(get_session),
):
    """Start a download with one GET and receive the file when it's quick.

    The response waits a few seconds for the download. If the file is ready it
    is returned as an attachment; otherwise the job keeps running in the
    background and the response is `202` with the URLs to follow it.
    """
    return await serve_link(request, link_source_url(request, url), quality, db)


async def serve_link(
    request: Request,
    source_url: str,
    quality: VideoQuality,
    db: AsyncSession,
) -> Response:
    """Shared by GET /api/download and the short /<link> form: queue the
    download, wait a little, and answer with the file or a 202."""
    try:
        source_url = DownloadRequest(url=source_url, quality=quality).url
    except ValidationError as e:
        message = e.errors()[0].get("msg", "Invalid URL")
        raise HTTPException(status_code=400, detail=message.removeprefix("Value error, "))

    is_valid, platform, error = validate_url(source_url)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error)

    try:
        job_id, task = await queue_download(source_url, quality, db, platform, request, "link")
    except DownloadQueueFull as e:
        raise HTTPException(status_code=429, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # asyncio.wait never cancels the task: the download carries on if the
    # wait ends or the client goes away.
    done, _ = await asyncio.wait({task}, timeout=settings.link_download_wait_seconds)
    if task in done:
        result = task.result()
        if result.get("success"):
            job_dir = settings.temp_dir / job_id
            recorded = SimpleNamespace(filename=result.get("filename"), quality=quality.value)
            file_path = find_primary_file(job_dir, recorded) if job_dir.exists() else None
            if file_path:
                return file_response(file_path)
        else:
            status = JobStatus.CANCELLED if result.get("cancelled") else JobStatus.FAILED
            return JSONResponse(
                status_code=422,
                content=DownloadFailedResponse(
                    job_id=job_id,
                    status=status,
                    detail=result.get("error") or "Download failed",
                ).model_dump(mode="json"),
            )

    progress = download_service.get_job_progress(job_id)
    status = progress.status if progress else JobStatus.QUEUED
    retry_after = 5
    body = DownloadAcceptedResponse(
        job_id=job_id,
        status=status,
        message="Download in progress. Poll status_url until status is completed, "
        "then GET download_url.",
        status_url=f"/api/jobs/{job_id}",
        download_url=f"/api/jobs/{job_id}/download",
        progress_url=f"/api/jobs/{job_id}/progress",
        retry_after_seconds=retry_after,
    )
    return JSONResponse(
        status_code=202,
        content=body.model_dump(mode="json"),
        headers={"Location": body.status_url, "Retry-After": str(retry_after)},
    )


SHORT_LINK_QUALITIES = {q.value: q for q in VideoQuality}


def short_link_target(raw_path: str, query_string: str) -> tuple[str, VideoQuality]:
    """Read ``[/<quality>]/<video link>`` from the raw request path.

    The link is taken as typed, without percent-encoding: its own query
    string (``?v=...&t=...``) is the request's query string. Proxies that
    merge slashes turn ``https://`` into ``https:/``, so that is undone.
    """
    target = raw_path.lstrip("/")
    quality = VideoQuality.Q_720P
    first, _, rest = target.partition("/")
    if first.lower() in SHORT_LINK_QUALITIES and rest:
        quality = SHORT_LINK_QUALITIES[first.lower()]
        target = rest.lstrip("/")
    if re.match(r"^https?%3a", target, re.IGNORECASE):
        target = unquote(target)
    target = re.sub(r"^(https?):/+", r"\1://", target, flags=re.IGNORECASE)
    if not re.match(r"^https?://", target, re.IGNORECASE):
        target = "https://" + target
    if query_string:
        target += "?" + query_string
    return target, quality


@router.get(
    "/d/{target:path}",
    summary="Download from a short link: /<video link> or /<quality>/<video link>",
    response_class=FileResponse,
    responses={
        200: {"description": "The finished file, as an attachment.",
              "content": {"video/mp4": {"schema": {"type": "string", "format": "binary"}},
                          "audio/mpeg": {"schema": {"type": "string", "format": "binary"}}}},
        202: {"model": DownloadAcceptedResponse, "description": "Still downloading; follow `status_url`."},
        400: {"model": ErrorResponse, "description": "Invalid or unsupported URL"},
        422: {"model": DownloadFailedResponse, "description": "The download failed"},
        429: {"model": ErrorResponse, "description": "Rate limit reached or download queue full"},
    },
)
@limiter.limit(settings.rate_limit_downloads)
async def download_from_short_link(
    request: Request,
    target: str,
    db: AsyncSession = Depends(get_session),
):
    """Same as `GET /api/download`, with the video link pasted as-is.

    On the website the short form is `https://wololo.edilson.dev/<video link>`
    (e.g. `/https://www.youtube.com/watch?v=379BagNcNf4`); prefix a quality
    (`/mp3/<link>`, `/1080p/<link>`) to change the default 720p.
    """
    raw_path = request.scope.get("raw_path", b"").decode("latin-1")
    marker = "/d/"
    raw_target = raw_path[raw_path.index(marker) + len(marker):] if marker in raw_path else target
    source_url, quality = short_link_target(raw_target, request.scope.get("query_string", b"").decode("latin-1"))
    return await serve_link(request, source_url, quality, db)


@router.get("/status", summary="Service and platform status for the last 90 days")
async def service_status(db: AsyncSession = Depends(get_session)):
    """Current state and daily history of the website, the API and downloads
    per platform (as shown on /status)."""
    return await monitoring.cached_status(db)


@router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job_status(job_id: str, db: AsyncSession = Depends(get_session)):
    """Get status of a download job"""
    result = await db.execute(select(DownloadJob).where(DownloadJob.id == job_id))
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Update with live progress if available
    response = JobResponse.model_validate(job)
    progress = download_service.get_job_progress(job_id)
    if progress:
        response.status = progress.status
        response.progress = progress.progress
        response.speed = progress.speed
        response.eta = progress.eta
        response.current_stage = progress.current_stage
        response.title = progress.title
        response.started_at = progress.started_at

    return response


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

    # While the job runs its folder holds partial streams; don't serve them
    progress = download_service.get_job_progress(job_id)
    if progress and progress.status not in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
        raise HTTPException(
            status_code=409,
            detail=f"Download is not finished yet (status: {progress.status.value}). "
            f"Poll /api/jobs/{job_id} until status is completed.",
        )

    # Find the file
    job_dir = settings.temp_dir / job_id
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail="Download files have expired")

    file_path = find_primary_file(job_dir, job)
    if not file_path:
        raise HTTPException(status_code=404, detail="No downloadable files found")

    return file_response(file_path)


@router.post("/jobs/{job_id}/extract-audio")
async def extract_audio(job_id: str):
    """Extract MP3 audio from a completed video download"""
    job_dir = settings.temp_dir / job_id
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail="Download files have expired")

    # Find the video file
    video_files = [
        f for f in _servable_files(job_dir)
        if f.suffix.lower() in VIDEO_EXTENSIONS
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

    loop = asyncio.get_running_loop()

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
    # Signal the worker thread to stop. The asyncio task is intentionally not
    # cancelled: it must keep running until the thread exits so cleanup and
    # the concurrency limit stay correct.
    download_service.cancel_job(job_id)

    # Don't overwrite jobs that already reached a terminal state
    await db.execute(
        update(DownloadJob)
        .where(DownloadJob.id == job_id)
        .where(DownloadJob.status.notin_(TERMINAL_STATUSES))
        .values(status=JobStatus.CANCELLED.value, completed_at=utcnow())
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
