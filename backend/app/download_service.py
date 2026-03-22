"""Download service using yt-dlp with progress tracking"""
import asyncio
import time
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Callable, Any
import yt_dlp
from concurrent.futures import ThreadPoolExecutor

from .config import settings
from .models import JobStatus, OutputFormat, VideoQuality, DownloadJob
from .schemas import JobProgressUpdate
from .utils import get_safe_filepath, sanitize_filename, validate_url, detect_platform


# Thread pool for running yt-dlp (it's not async-native)
executor = ThreadPoolExecutor(max_workers=settings.max_concurrent_downloads)


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
        status = d.get("status", "")

        if status == "downloading":
            self.status = JobStatus.DOWNLOADING
            self.current_stage = "Downloading..."

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

            # Extract speed
            speed = d.get("speed")
            if speed:
                if speed > 1024 * 1024:
                    self.speed = f"{speed / 1024 / 1024:.1f} MiB/s"
                elif speed > 1024:
                    self.speed = f"{speed / 1024:.1f} KiB/s"
                else:
                    self.speed = f"{speed:.0f} B/s"

            # Extract ETA
            eta = d.get("eta")
            if eta:
                mins, secs = divmod(int(eta), 60)
                hours, mins = divmod(mins, 60)
                if hours:
                    self.eta = f"{hours:02d}:{mins:02d}:{secs:02d}"
                else:
                    self.eta = f"{mins:02d}:{secs:02d}"

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

    def __init__(self):
        self.active_jobs: Dict[str, DownloadProgress] = {}
        self.progress_callbacks: Dict[str, Callable[[JobProgressUpdate], Any]] = {}

    def register_callback(self, job_id: str, callback: Callable[[JobProgressUpdate], Any]):
        """Register a callback for job progress updates"""
        self.progress_callbacks[job_id] = callback
        if job_id in self.active_jobs:
            self.active_jobs[job_id].callback = callback

    def unregister_callback(self, job_id: str):
        """Unregister a callback"""
        self.progress_callbacks.pop(job_id, None)
        if job_id in self.active_jobs and self.active_jobs[job_id].callback:
            self.active_jobs[job_id].callback = None

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
            if platform == "instagram":
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

    def _run_download(
        self,
        url: str,
        job_id: str,
        quality: VideoQuality,
        progress: DownloadProgress,
    ) -> dict:
        """Run the actual download (blocking, runs in thread pool)"""
        opts = self.get_yt_dlp_options(job_id, quality, progress, url)

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                # First, extract info
                progress.status = JobStatus.VALIDATING
                progress.current_stage = "Extracting video info..."
                progress._notify()

                info = ydl.extract_info(url, download=False)
                progress.title = info.get("title", "Unknown")

                # Start download
                progress.status = JobStatus.DOWNLOADING
                progress.current_stage = "Starting download..."
                progress._notify()

                ydl.download([url])

                # Find the output file
                output_dir = settings.temp_dir / job_id
                files = list(output_dir.glob("*"))

                # Filter out part files and find the actual output
                output_files = [f for f in files if not f.suffix.endswith(".part")]

                if not output_files:
                    raise Exception("Download completed but no output file found")

                # Get the most recently modified file
                output_file = max(output_files, key=lambda f: f.stat().st_mtime)

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
            elif "age-restricted" in error_msg.lower():
                error_msg = "This video is age-restricted"
            elif "copyright" in error_msg.lower():
                error_msg = "This video is blocked due to copyright"
            return {"success": False, "error": error_msg}

        except Exception as e:
            return {"success": False, "error": str(e)}

    async def start_download(
        self,
        url: str,
        quality: VideoQuality,
        progress_callback: Optional[Callable[[JobProgressUpdate], Any]] = None,
    ) -> tuple[str, asyncio.Task]:
        """Start a download job asynchronously. Returns job_id and task."""
        # Validate URL first
        is_valid, platform, error = validate_url(url)
        if not is_valid:
            raise ValueError(error)

        # Generate job ID
        job_id = str(uuid.uuid4())

        # Create progress tracker
        progress = DownloadProgress(job_id, progress_callback)
        progress.status = JobStatus.QUEUED
        progress.current_stage = "Starting..."
        self.active_jobs[job_id] = progress

        # Register callback if provided
        if progress_callback:
            self.progress_callbacks[job_id] = progress_callback

        # Create async task
        loop = asyncio.get_event_loop()

        async def download_task():
            try:
                # Run blocking download in thread pool
                result = await loop.run_in_executor(
                    executor,
                    self._run_download,
                    url,
                    job_id,
                    quality,
                    progress,
                )

                if result["success"]:
                    progress.status = JobStatus.COMPLETED
                    progress.progress = 100
                    progress.current_stage = "Complete!"
                    progress.filename = result["filename"]
                    progress._notify(download_ready=True)
                else:
                    progress.status = JobStatus.FAILED
                    progress.error_message = result.get("error", "Unknown error")
                    progress._notify()

                return result

            except Exception as e:
                progress.status = JobStatus.FAILED
                progress.error_message = str(e)
                progress._notify()
                return {"success": False, "error": str(e)}

            finally:
                # Clean up
                self.active_jobs.pop(job_id, None)
                self.progress_callbacks.pop(job_id, None)

        task = asyncio.create_task(download_task())
        return job_id, task, platform

    def get_job_progress(self, job_id: str) -> Optional[DownloadProgress]:
        """Get current progress for a job"""
        return self.active_jobs.get(job_id)

    def cancel_job(self, job_id: str) -> bool:
        """Cancel a running job"""
        if job_id in self.active_jobs:
            self.active_jobs[job_id].status = JobStatus.CANCELLED
            self.active_jobs[job_id].error_message = "Cancelled by user"
            self.active_jobs[job_id]._notify()
            return True
        return False

    @property
    def active_count(self) -> int:
        """Get count of active downloads"""
        return len(self.active_jobs)


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
    }

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
