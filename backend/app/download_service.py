"""Download service using yt-dlp with progress tracking"""
import asyncio
import logging
import shutil
import time
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Awaitable, Dict, Optional, Callable, Any
import yt_dlp
from concurrent.futures import ThreadPoolExecutor

from .config import settings
from .models import JobStatus, OutputFormat, VideoQuality, DownloadJob, utcnow
from .schemas import JobProgressUpdate
from .utils import get_safe_filepath, sanitize_filename, validate_url, detect_platform
from .threads_extractor import extract_threads_info


logger = logging.getLogger(__name__)

# Thread pool for running yt-dlp (it's not async-native)
executor = ThreadPoolExecutor(max_workers=settings.max_concurrent_downloads)

# yt-dlp intermediate artifacts that are never a finished output
TEMP_SUFFIXES = (".part", ".ytdl", ".temp")


class DownloadQueueFull(Exception):
    """All execution and waiting slots have been reserved."""


def format_speed(bytes_per_second: Optional[float]) -> Optional[str]:
    """Human readable transfer speed, e.g. "1.5 MiB/s"."""
    if not bytes_per_second:
        return None
    if bytes_per_second > 1024 * 1024:
        return f"{bytes_per_second / 1024 / 1024:.1f} MiB/s"
    if bytes_per_second > 1024:
        return f"{bytes_per_second / 1024:.1f} KiB/s"
    return f"{bytes_per_second:.0f} B/s"


def format_eta(seconds: Optional[float]) -> Optional[str]:
    """ETA as MM:SS or HH:MM:SS."""
    if not seconds:
        return None
    mins, secs = divmod(int(seconds), 60)
    hours, mins = divmod(mins, 60)
    if hours:
        return f"{hours:02d}:{mins:02d}:{secs:02d}"
    return f"{mins:02d}:{secs:02d}"


def _has_valid_cookies_file() -> bool:
    """Check if a real cookies file exists (not just the placeholder)."""
    if not settings.cookies_file:
        return False
    p = Path(settings.cookies_file)
    if not p.is_file():
        return False
    try:
        text = p.read_text().strip()
        # Placeholder or empty file — ignore
        for line in text.splitlines():
            if line and not line.startswith("#"):
                return True
        return False
    except Exception:
        return False


def _apply_cookie_options(opts: dict) -> dict:
    """Add cookie options for platforms that require authentication."""
    if _has_valid_cookies_file():
        opts["cookiefile"] = settings.cookies_file
    elif settings.cookies_from_browser:
        opts["cookiesfrombrowser"] = (settings.cookies_from_browser,)
    return opts


class DownloadProgress:
    """Track download progress for a job"""

    # Download phase: 0-70%, Conversion phase: 70-95%, Finalization: 95-100%
    DOWNLOAD_MAX = 70.0
    CONVERSION_MIN = 70.0
    CONVERSION_MAX = 95.0

    def __init__(self, job_id: str, callback: Optional[Callable[[JobProgressUpdate], Any]] = None):
        self.job_id = job_id
        self.callback = callback
        self.status = JobStatus.QUEUED
        self.progress = 0.0
        self.speed: Optional[str] = None
        self.eta: Optional[str] = None
        self.current_stage: Optional[str] = None
        self.title: Optional[str] = None
        self.filename: Optional[str] = None
        self.error_message: Optional[str] = None
        self._last_progress = -1  # Avoid spamming updates
        # Interpolation state for conversion phase
        self._last_real_update: float = 0.0
        self._interpolation_timer: Optional[threading.Timer] = None
        self._in_conversion = False
        # Set by cancel_job (or the timeout); checked from the worker thread
        # to abort the download
        self.cancel_event = threading.Event()
        self.timed_out = False
        self.started_at: Optional[datetime] = None

    @property
    def cancelled(self) -> bool:
        return self.cancel_event.is_set()

    def raise_if_cancelled(self):
        """Abort the worker thread if the user cancelled this job."""
        if self.cancel_event.is_set():
            raise yt_dlp.utils.DownloadCancelled("Cancelled by user")

    def _notify(self, download_ready: bool = False):
        """Send progress update via callback"""
        if self.callback:
            update = JobProgressUpdate(
                job_id=self.job_id,
                status=self.status,
                progress=round(self.progress, 1),
                speed=self.speed,
                eta=self.eta,
                current_stage=self.current_stage,
                title=self.title,
                error_message=self.error_message,
                download_ready=download_ready,
            )
            try:
                self.callback(update)
            except Exception:
                pass

    def _start_interpolation(self):
        """Start background interpolation timer for conversion phase"""
        self._in_conversion = True
        self._last_real_update = time.monotonic()
        self._schedule_interpolation()

    def _schedule_interpolation(self):
        """Schedule next interpolation tick"""
        if not self._in_conversion:
            return
        self._interpolation_timer = threading.Timer(2.0, self._interpolation_tick)
        self._interpolation_timer.daemon = True
        self._interpolation_timer.start()

    def _interpolation_tick(self):
        """Increment progress if stuck during conversion phase"""
        if not self._in_conversion:
            return
        elapsed = time.monotonic() - self._last_real_update
        if elapsed >= 5.0 and self.progress < self.CONVERSION_MAX:
            self.progress = min(self.progress + 1.0, self.CONVERSION_MAX)
            self._last_progress = int(self.progress)
            self._notify()
        self._schedule_interpolation()

    def _stop_interpolation(self):
        """Stop the interpolation timer"""
        self._in_conversion = False
        if self._interpolation_timer:
            self._interpolation_timer.cancel()
            self._interpolation_timer = None

    def progress_hook(self, d: dict):
        """yt-dlp progress hook — download phase maps to 0-70%"""
        self.raise_if_cancelled()
        status = d.get("status", "")

        if status == "downloading":
            self.status = JobStatus.DOWNLOADING
            self.current_stage = "Downloading..."
            if not self.title:
                self.title = (d.get("info_dict") or {}).get("title")

            # Extract raw progress (0-100) and scale to 0-70%
            raw_progress = 0.0
            total = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
            downloaded = d.get("downloaded_bytes", 0)

            if total > 0:
                raw_progress = (downloaded / total) * 100
            else:
                # Fallback to fragment progress
                fragment = d.get("fragment_index", 0)
                total_frags = d.get("fragment_count", 0)
                if total_frags > 0:
                    raw_progress = (fragment / total_frags) * 100

            self.progress = raw_progress * self.DOWNLOAD_MAX / 100

            # Extract speed and ETA
            speed = format_speed(d.get("speed"))
            if speed:
                self.speed = speed
            eta = format_eta(d.get("eta"))
            if eta:
                self.eta = eta

            # Extract filename
            if d.get("filename"):
                self.filename = Path(d["filename"]).name

            # Notify every 1% or significant change
            if int(self.progress) > self._last_progress:
                self._last_progress = int(self.progress)
                self._notify()

        elif status == "finished":
            self.current_stage = "Download complete, preparing conversion..."
            self.progress = self.DOWNLOAD_MAX  # 70%
            self._notify()

        elif status == "error":
            self.status = JobStatus.FAILED
            self.error_message = str(d.get("error", "Download error"))
            self._notify()

    def postprocessor_hook(self, d: dict):
        """yt-dlp postprocessor hook — conversion phase maps to 70-95%"""
        self.raise_if_cancelled()
        status = d.get("status", "")
        conv_range = self.CONVERSION_MAX - self.CONVERSION_MIN  # 25%

        if status == "started":
            pp_name = d.get("postprocessor", "")
            if "VideoConvertor" in pp_name or "CopyStream" in pp_name:
                self.status = JobStatus.CONVERTING
                self.current_stage = "Converting video..."
                self.progress = self.CONVERSION_MIN
                self.speed = None
                self.eta = None
                self._start_interpolation()
            elif "ExtractAudio" in pp_name:
                self.status = JobStatus.CONVERTING
                self.current_stage = "Extracting audio..."
                self.progress = self.CONVERSION_MIN
                self.speed = None
                self.eta = None
                self._start_interpolation()
            elif "FFmpeg" in pp_name or "Audio" in pp_name:
                self.status = JobStatus.CONVERTING
                self.current_stage = "Converting format..."
                self.progress = self.CONVERSION_MIN
                self._start_interpolation()
            else:
                self.current_stage = f"Processing ({pp_name})..."
            self._notify()

        elif status == "processing":
            # FFmpeg progress update during conversion: scale to 70-95%
            ffmpeg_progress = d.get("progress", 0) or 0
            self.progress = min(
                self.CONVERSION_MAX,
                self.CONVERSION_MIN + ffmpeg_progress * conv_range / 100,
            )
            self._last_real_update = time.monotonic()
            self._notify()

        elif status == "finished":
            self._stop_interpolation()
            self.current_stage = "Finalizing..."
            self.progress = self.CONVERSION_MAX  # 95%
            self._notify()


class DownloadService:
    """Service to manage video/audio downloads"""

    MAX_COMPLETED_SNAPSHOTS = 100

    def __init__(self):
        self.active_jobs: Dict[str, DownloadProgress] = {}
        self._waiting_jobs: Dict[str, asyncio.Event] = {}
        self._running_jobs: set[str] = set()
        # Keep a bounded terminal snapshot so fast downloads that finish before
        # the browser opens the SSE stream can still replay their final state.
        self.completed_jobs: Dict[str, DownloadProgress] = {}
        self.progress_callbacks: Dict[str, Callable[[JobProgressUpdate], Any]] = {}

    def register_callback(self, job_id: str, callback: Callable[[JobProgressUpdate], Any]):
        """Register a callback for job progress updates"""
        self.progress_callbacks[job_id] = callback
        completed = self.completed_jobs.get(job_id)
        if completed:
            completed.callback = callback
            completed._notify(download_ready=completed.status == JobStatus.COMPLETED)
        elif job_id in self.active_jobs:
            self.active_jobs[job_id].callback = callback

    def unregister_callback(self, job_id: str):
        """Unregister a callback"""
        self.progress_callbacks.pop(job_id, None)
        if job_id in self.active_jobs and self.active_jobs[job_id].callback:
            self.active_jobs[job_id].callback = None
        completed = self.completed_jobs.pop(job_id, None)
        if completed:
            completed.callback = None

    def _remember_completed(self, progress: DownloadProgress):
        """Retain a bounded final state for late SSE subscribers."""
        self.completed_jobs[progress.job_id] = progress
        while len(self.completed_jobs) > self.MAX_COMPLETED_SNAPSHOTS:
            oldest_job_id = next(iter(self.completed_jobs))
            self.completed_jobs.pop(oldest_job_id, None)

    def get_yt_dlp_options(
        self,
        job_id: str,
        quality: VideoQuality,
        progress: DownloadProgress,
        url: str = "",
    ) -> dict:
        """Get yt-dlp options based on quality selection"""
        # Base output path
        output_dir = settings.temp_dir / job_id
        output_dir.mkdir(parents=True, exist_ok=True)

        # Sanitize output template
        output_template = str(output_dir / "%(title).200s.%(ext)s")

        # Base options with security settings
        opts = {
            "outtmpl": output_template,
            "progress_hooks": [progress.progress_hook],
            "postprocessor_hooks": [progress.postprocessor_hook],
            "quiet": True,
            "no_warnings": True,
            "extract_flat": False,
            "noplaylist": True,  # Only download single video
            "socket_timeout": 30,
            "retries": 3,
            "fragment_retries": 3,
            # Security: limit file size
            "max_filesize": settings.max_file_size_mb * 1024 * 1024,
            # No external downloaders for safety
            "external_downloader": None,
            # Restrict to HTTPS
            "prefer_insecure": False,
        }

        _apply_cookie_options(opts)

        # Detect platform for format/codec decisions
        platform = detect_platform(url) if url else None

        if quality == VideoQuality.MP3:
            opts.update({
                "format": "bestaudio/best",
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "320",
                }],
                # -threads 0 for cases that need re-encoding (non-mp3 source)
                "postprocessor_args": {
                    "extractaudio": ["-threads", "0"],
                },
            })
        else:
            # Video quality: extract resolution number from enum value
            height = int(quality.value.replace("p", ""))

            # Instagram uses VP9 codec which QuickTime can't play;
            # re-encode to H.264 for compatibility
            if platform in ("instagram", "threads"):
                pp_args = [
                    "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                    "-c:a", "copy",
                    "-movflags", "+faststart",
                    "-threads", "0",
                ]
            else:
                pp_args = [
                    "-c", "copy",
                    "-movflags", "+faststart",
                    "-threads", "0",
                ]

            opts.update({
                "format": (
                    f"bestvideo[height<={height}][vcodec^=avc1]+bestaudio[acodec^=mp4a]/"
                    f"bestvideo[height<={height}]+bestaudio/"
                    f"bestvideo[width<={height}]+bestaudio/"
                    f"best[height<={height}]/best[width<={height}]/best"
                ),
                "merge_output_format": "mp4",
                "postprocessors": [{
                    "key": "FFmpegCopyStream",
                }],
                "postprocessor_args": {
                    "copystream": pp_args,
                },
            })

        return opts

    def _run_threads_download(
        self,
        url: str,
        job_id: str,
        quality: VideoQuality,
        progress: DownloadProgress,
    ) -> dict:
        """Download a Threads video using the custom extractor."""
        import httpx as _httpx

        try:
            progress.status = JobStatus.VALIDATING
            progress.current_stage = "Extracting video info..."
            progress._notify()

            info = extract_threads_info(url)
            progress.title = info["title"]

            progress.status = JobStatus.DOWNLOADING
            progress.current_stage = "Downloading..."
            progress._notify()

            # Stream the video to disk
            output_dir = settings.temp_dir / job_id
            output_dir.mkdir(parents=True, exist_ok=True)
            safe_name = sanitize_filename(f"{info['title']}.mp4")
            output_file = output_dir / safe_name

            max_bytes = settings.max_file_size_mb * 1024 * 1024
            too_large = f"File is larger than the {settings.max_file_size_mb} MB limit"

            with _httpx.stream(
                "GET",
                info["video_url"],
                headers={"User-Agent": "Mozilla/5.0"},
                follow_redirects=True,
                timeout=60,
            ) as resp:
                resp.raise_for_status()
                total = int(resp.headers.get("content-length", 0))
                if total > max_bytes:
                    raise ValueError(too_large)
                downloaded = 0
                started = time.monotonic()

                with open(output_file, "wb") as f:
                    for chunk in resp.iter_bytes(chunk_size=256 * 1024):
                        progress.raise_if_cancelled()
                        f.write(chunk)
                        downloaded += len(chunk)
                        if downloaded > max_bytes:
                            raise ValueError(too_large)
                        if total > 0:
                            raw = (downloaded / total) * 100
                            progress.progress = raw * progress.DOWNLOAD_MAX / 100
                            if int(progress.progress) > progress._last_progress:
                                progress._last_progress = int(progress.progress)
                                elapsed = time.monotonic() - started
                                if elapsed > 0:
                                    rate = downloaded / elapsed
                                    progress.speed = format_speed(rate)
                                    progress.eta = format_eta((total - downloaded) / rate)
                                progress._notify()

            progress.progress = progress.DOWNLOAD_MAX
            progress.speed = None
            progress.eta = None
            progress._notify()

            if quality == VideoQuality.MP3:
                import subprocess

                progress.raise_if_cancelled()
                progress.status = JobStatus.CONVERTING
                progress.current_stage = "Extracting audio..."
                progress.progress = progress.CONVERSION_MIN
                progress.speed = None
                progress.eta = None
                progress._notify()

                audio_file = output_file.with_suffix(".mp3")
                ffmpeg_result = subprocess.run(
                    [
                        "ffmpeg", "-i", str(output_file),
                        "-vn", "-acodec", "libmp3lame", "-b:a", "320k",
                        "-threads", "0", "-y", str(audio_file),
                    ],
                    capture_output=True,
                    timeout=300,
                )
                if ffmpeg_result.returncode != 0:
                    error = ffmpeg_result.stderr.decode(errors="replace")[:500]
                    raise RuntimeError(f"Audio extraction failed: {error}")

                output_file.unlink()
                output_file = audio_file
                progress.current_stage = "Finalizing..."
                progress.progress = progress.CONVERSION_MAX
                progress._notify()

            return {
                "success": True,
                "title": info["title"],
                "filename": output_file.name,
                "filepath": str(output_file),
                "file_size": output_file.stat().st_size,
                "duration": info.get("duration"),
                "thumbnail_url": info.get("thumbnail_url"),
            }

        except Exception as e:
            # Don't leave a partial video behind (e.g. size limit, network error)
            shutil.rmtree(settings.temp_dir / job_id, ignore_errors=True)
            return {"success": False, "error": str(e)}

    def _run_download(
        self,
        url: str,
        job_id: str,
        quality: VideoQuality,
        progress: DownloadProgress,
    ) -> dict:
        """Run the actual download (blocking, runs in thread pool)"""
        # Threads: use custom extractor (yt-dlp doesn't support it)
        platform = detect_platform(url) if url else None
        if platform == "threads":
            return self._run_threads_download(url, job_id, quality, progress)

        opts = self.get_yt_dlp_options(job_id, quality, progress, url)

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                progress.status = JobStatus.VALIDATING
                progress.current_stage = "Extracting video info..."
                progress._notify()

                # One call extracts metadata and downloads, avoiding a second
                # round-trip to the platform. The title reaches the UI via the
                # progress hook's info_dict as soon as the download starts.
                info = ydl.extract_info(url, download=True) or {}
                progress.title = info.get("title") or progress.title or "Unknown"

                output_file = self._find_output_file(job_id, info)

                return {
                    "success": True,
                    "title": progress.title,
                    "filename": output_file.name,
                    "filepath": str(output_file),
                    "file_size": output_file.stat().st_size,
                    "duration": info.get("duration"),
                    "thumbnail_url": info.get("thumbnail"),
                }

        except yt_dlp.utils.DownloadError as e:
            error_msg = str(e)
            # Clean up common error messages
            if "Private video" in error_msg:
                error_msg = "This video is private and cannot be downloaded"
            elif "Video unavailable" in error_msg:
                error_msg = "This video is unavailable"
            elif "Sign in to confirm" in error_msg:
                error_msg = "YouTube requires authentication. Make sure you're logged in to YouTube in your browser"
            elif "age-restricted" in error_msg.lower():
                error_msg = "This video is age-restricted"
            elif "copyright" in error_msg.lower():
                error_msg = "This video is blocked due to copyright"
            return {"success": False, "error": error_msg}

        except Exception as e:
            return {"success": False, "error": str(e)}

    @staticmethod
    def _find_output_file(job_id: str, info: dict) -> Path:
        """Locate the finished file: yt-dlp's reported path, else newest file."""
        output_dir = settings.temp_dir / job_id
        for download in info.get("requested_downloads") or []:
            filepath = download.get("filepath")
            if filepath and Path(filepath).is_file():
                return Path(filepath)

        output_files = [
            f for f in output_dir.glob("*")
            if f.is_file() and not f.name.endswith(TEMP_SUFFIXES)
        ]
        if not output_files:
            raise Exception("Download completed but no output file found")
        return max(output_files, key=lambda f: f.stat().st_mtime)

    async def start_download(
        self,
        url: str,
        quality: VideoQuality,
        progress_callback: Optional[Callable[[JobProgressUpdate], Any]] = None,
        job_id: Optional[str] = None,
        on_finish: Optional[Callable[["DownloadProgress", dict], Awaitable[Any]]] = None,
        on_enqueue: Optional[Callable[[], Awaitable[Any]]] = None,
    ) -> tuple[str, asyncio.Task, Optional[str]]:
        """Start a download job asynchronously. Returns job_id, task and platform.

        ``on_finish`` is awaited with the final progress and result once the job
        reaches a terminal state (completed, failed or cancelled).
        """
        # Validate URL first
        is_valid, platform, error = validate_url(url)
        if not is_valid:
            raise ValueError(error)

        # Reserve capacity before the first await so simultaneous submissions
        # cannot overfill the queue while their database rows are being stored.
        capacity = settings.max_concurrent_downloads + settings.max_queued_downloads
        if len(self.active_jobs) >= capacity:
            raise DownloadQueueFull("Download queue is full. Please try again later.")

        # Generate job ID
        job_id = job_id or str(uuid.uuid4())

        # Create progress tracker
        progress = DownloadProgress(job_id, progress_callback)
        progress.status = JobStatus.QUEUED
        progress.current_stage = "Waiting for a download slot..."
        self.active_jobs[job_id] = progress

        try:
            if on_enqueue:
                await on_enqueue()
        except BaseException:
            self.active_jobs.pop(job_id, None)
            raise

        # Register callback if provided
        if progress_callback:
            self.progress_callbacks[job_id] = progress_callback

        # Create async task
        loop = asyncio.get_running_loop()
        ready = asyncio.Event()
        self._waiting_jobs[job_id] = ready

        async def download_task():
            result: dict = {"success": False, "error": "Unknown error"}
            try:
                await ready.wait()
                if progress.cancelled:
                    self._remember_completed(progress)
                    result = {"success": False, "error": "Cancelled by user", "cancelled": True}
                    return result

                worker_started = asyncio.Event()

                def run_download():
                    loop.call_soon_threadsafe(worker_started.set)
                    if progress.cancelled:
                        return {"success": False, "error": "Cancelled by user"}
                    progress.started_at = utcnow()
                    progress.status = JobStatus.VALIDATING
                    progress.current_stage = "Starting..."
                    progress._notify()
                    return self._run_download(url, job_id, quality, progress)

                # Run blocking download in thread pool
                future = loop.run_in_executor(executor, run_download)
                # Previews also use this pool. Its wait must not consume the
                # download timeout or mark the job as already started.
                await worker_started.wait()
                try:
                    result = await asyncio.wait_for(
                        asyncio.shield(future),
                        timeout=settings.download_timeout_seconds,
                    )
                except asyncio.TimeoutError:
                    # A thread can't be killed: ask it to stop at the next
                    # yt-dlp hook and wait so the slot is freed only when the
                    # work has really ended.
                    progress.timed_out = True
                    progress.cancel_event.set()
                    await future

                if progress.timed_out:
                    progress.status = JobStatus.FAILED
                    limit = settings.download_timeout_seconds
                    progress.error_message = "Download timed out after " + (
                        f"{limit // 60} minutes" if limit >= 60 else f"{limit} seconds"
                    )
                    shutil.rmtree(settings.temp_dir / job_id, ignore_errors=True)
                    result = {"success": False, "error": progress.error_message}
                    self._remember_completed(progress)
                    progress._notify()
                elif progress.cancelled:
                    # Keep the cancelled state; drop partial/complete files
                    progress.status = JobStatus.CANCELLED
                    progress.error_message = "Cancelled by user"
                    shutil.rmtree(settings.temp_dir / job_id, ignore_errors=True)
                    result = {"success": False, "error": "Cancelled by user", "cancelled": True}
                    self._remember_completed(progress)
                elif result["success"]:
                    progress.status = JobStatus.COMPLETED
                    progress.progress = 100
                    progress.current_stage = "Complete!"
                    progress.filename = result["filename"]
                    self._remember_completed(progress)
                    progress._notify(download_ready=True)
                else:
                    progress.status = JobStatus.FAILED
                    progress.error_message = result.get("error", "Unknown error")
                    self._remember_completed(progress)
                    progress._notify()

                return result

            except Exception as e:
                progress.status = JobStatus.FAILED
                progress.error_message = str(e)
                self._remember_completed(progress)
                progress._notify()
                result = {"success": False, "error": str(e)}
                return result

            finally:
                # Clean up
                progress._stop_interpolation()
                self._waiting_jobs.pop(job_id, None)
                self._running_jobs.discard(job_id)
                self.active_jobs.pop(job_id, None)
                self.progress_callbacks.pop(job_id, None)
                self._dispatch_queued()
                if on_finish:
                    try:
                        await on_finish(progress, result)
                    except Exception:
                        logger.exception("Failed to persist job %s", job_id)

        task = asyncio.create_task(download_task())
        self._dispatch_queued()
        return job_id, task, platform

    def _dispatch_queued(self) -> None:
        """Wake waiting jobs in insertion order when execution slots open."""
        while self._waiting_jobs and len(self._running_jobs) < settings.max_concurrent_downloads:
            job_id = next(iter(self._waiting_jobs))
            ready = self._waiting_jobs.pop(job_id)
            self._running_jobs.add(job_id)
            ready.set()

    def get_job_progress(self, job_id: str) -> Optional[DownloadProgress]:
        """Get current progress for a job"""
        return self.active_jobs.get(job_id)

    def cancel_job(self, job_id: str) -> bool:
        """Cancel a running job"""
        if job_id in self.active_jobs:
            progress = self.active_jobs[job_id]
            # Signal the worker thread; the next yt-dlp hook raises and stops it.
            # The job stays in active_jobs until the thread actually exits so the
            # concurrency limit keeps counting it.
            progress.cancel_event.set()
            progress.status = JobStatus.CANCELLED
            progress.error_message = "Cancelled by user"
            ready = self._waiting_jobs.pop(job_id, None)
            if ready is not None:
                # Queued jobs have no worker to stop. Wake their task to persist
                # cancellation and release queue capacity immediately.
                self.active_jobs.pop(job_id, None)
                self._remember_completed(progress)
                ready.set()
            progress._notify()
            return True
        return False

    @property
    def active_count(self) -> int:
        """Get count of active downloads"""
        return len(self._running_jobs)

    @property
    def queued_count(self) -> int:
        """Get count of jobs waiting for an execution slot."""
        return len(self._waiting_jobs)


# Singleton instance
download_service = DownloadService()


def extract_video_preview(url: str) -> dict:
    """Extract video metadata without downloading. Returns preview data."""
    ALLOWED_QUALITIES = [360, 480, 720, 1080]

    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "socket_timeout": 10,
        "no_check_formats": True,
        "skip_download": True,
        "ignore_no_formats_error": True,
    }

    _apply_cookie_options(opts)

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except yt_dlp.utils.DownloadError as e:
        error_msg = str(e)
        if "Private video" in error_msg:
            raise ValueError("This video is private and cannot be accessed")
        elif "Video unavailable" in error_msg:
            raise ValueError("This video is unavailable")
        raise ValueError(f"Could not fetch video info: {error_msg}")

    if not info:
        raise ValueError("Could not fetch video info")

    # Parse available resolutions from formats
    # Use min(width, height) for portrait videos (e.g. Instagram Reels)
    available = set()
    for fmt in info.get("formats", []):
        height = fmt.get("height")
        width = fmt.get("width")
        if height and isinstance(height, int):
            short_side = min(width, height) if width and isinstance(width, int) else height
            for q in ALLOWED_QUALITIES:
                if short_side >= q:
                    available.add(q)

    duration = info.get("duration")
    if duration is not None:
        duration = int(duration)

    return {
        "title": info.get("title", "Unknown"),
        "thumbnail_url": info.get("thumbnail"),
        "duration": duration,
        "available_qualities": sorted(available),
    }


def get_yt_dlp_version() -> str:
    """Get yt-dlp version string"""
    try:
        return yt_dlp.version.__version__
    except Exception:
        return "unknown"
