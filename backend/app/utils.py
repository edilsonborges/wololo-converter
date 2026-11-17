"""Utility functions for URL validation, security, and file handling"""
import logging
import os
import re
import shutil
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import parse_qs, urlparse
import asyncio

from .config import settings

logger = logging.getLogger(__name__)


# Platform detection patterns
PLATFORM_PATTERNS = {
    "youtube": [
        r"(?:https?://)?(?:(?:www|m|music)\.)?youtube\.com/watch\?(?:[^#]*&)?v=[\w-]+",
        r"(?:https?://)?(?:(?:www|m)\.)?youtube\.com/shorts/[\w-]+",
        r"(?:https?://)?(?:(?:www|m)\.)?youtube\.com/live/[\w-]+",
        r"(?:https?://)?youtu\.be/[\w-]+",
        r"(?:https?://)?(?:(?:www|m)\.)?youtube\.com/embed/[\w-]+",
    ],
    "instagram": [
        r"(?:https?://)?(?:www\.)?instagram\.com/(?:p|reels?|tv)/[\w-]+",
        r"(?:https?://)?(?:www\.)?instagram\.com/share/(?:p|reel)/[\w-]+",
    ],
    "facebook": [
        r"(?:https?://)?(?:www\.)?facebook\.com/.+/videos/\d+",
        r"(?:https?://)?(?:www\.)?facebook\.com/watch/?\?v=\d+",
        r"(?:https?://)?fb\.watch/[\w-]+",
    ],
    "twitter": [
        r"(?:https?://)?(?:www\.)?(?:twitter|x)\.com/\w+/status/\d+",
    ],
    "threads": [
        r"(?:https?://)?(?:www\.)?threads\.(?:net|com)/@[\w.]+/post/[\w]+",
        r"(?:https?://)?(?:www\.)?threads\.(?:net|com)/share/[\w-]+(?:/|[?#]|$)",
    ],
    "tiktok": [
        r"(?:https?://)?(?:www\.)?tiktok\.com/@[\w.]+/video/\d+",
        r"(?:https?://)?(?:vm|vt)\.tiktok\.com/[\w]+",
        r"(?:https?://)?(?:www\.)?tiktok\.com/t/[\w]+",
    ],
}


def detect_platform(url: str) -> Optional[str]:
    """Detect the platform from a URL"""
    url = url.strip().lower()

    for platform, patterns in PLATFORM_PATTERNS.items():
        for pattern in patterns:
            if re.match(pattern, url, re.IGNORECASE):
                return platform

    return None


def normalize_video_url(url: str) -> str:
    """Remove non-identifying parameters and return a canonical video URL."""
    platform = detect_platform(url)
    if not platform:
        return url

    parsed = urlparse(url)

    if platform == "youtube" and parsed.path == "/watch":
        video_ids = parse_qs(parsed.query).get("v")
        if video_ids:
            return f"https://youtu.be/{video_ids[0]}"

    if platform == "youtube" and parsed.netloc.lower().split(":", 1)[0] == "youtu.be":
        video_id = next((part for part in parsed.path.split("/") if part), None)
        if video_id:
            return f"https://youtu.be/{video_id}"

    return parsed._replace(
        scheme="https",
        params="",
        query="",
        fragment="",
    ).geturl()


YOUTUBE_ID_PATH = re.compile(r"^/(?:shorts|live|embed|v)/([\w-]{6,})")
# Platforms whose post id is unique on its own: /p/ID, /reel/ID and /reels/ID
# are the same Instagram post; any user name in a tweet or TikTok URL works
POST_ID_PATHS = {
    "instagram": re.compile(r"^/(?:share/)?(?:p|reels?|tv)/([\w-]+)"),
    "twitter": re.compile(r"/status/(\d+)"),
    "tiktok": re.compile(r"/video/(\d+)"),
}


def media_key(url: str) -> str:
    """The same video however its link was written: youtu.be/ID,
    youtube.com/watch?v=ID&t=30, m.youtube.com/shorts/ID and tracking
    parameters all give the same key."""
    platform = detect_platform(url)
    parsed = urlparse(url.strip())
    host = parsed.netloc.lower().split(":", 1)[0]
    host = re.sub(r"^(?:www|m|mobile|music)\.", "", host)
    if platform == "youtube":
        if host == "youtu.be":
            video_id = next((part for part in parsed.path.split("/") if part), None)
        elif parsed.path == "/watch":
            video_id = (parse_qs(parsed.query).get("v") or [None])[0]
        else:
            match = YOUTUBE_ID_PATH.match(parsed.path)
            video_id = match.group(1) if match else None
        if video_id:
            return f"youtube:{video_id}"
    pattern = POST_ID_PATHS.get(platform)
    match = pattern.search(parsed.path) if pattern else None
    if match:
        return f"{platform}:{match.group(1)}"
    path = parsed.path.rstrip("/") or "/"
    return f"{platform or 'other'}:{host}{path}"[:300]


def is_allowed_domain(url: str) -> bool:
    """Check if URL domain is in the allowed list"""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()

        # Remove port if present
        if ":" in domain:
            domain = domain.split(":")[0]

        # Check against allowed domains
        for allowed in settings.allowed_domains:
            if domain == allowed.lower() or domain.endswith("." + allowed.lower()):
                return True

        return False
    except Exception:
        return False


def validate_url(url: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Validate a URL for download.
    Returns: (is_valid, platform, error_message)
    """
    url = url.strip()

    # Basic URL validation
    if not url:
        return False, None, "URL cannot be empty"

    if not url.startswith(("http://", "https://")):
        return False, None, "URL must start with http:// or https://"

    # Check domain allowlist (SSRF protection)
    if not is_allowed_domain(url):
        return False, None, "Domain not supported. Supported platforms: YouTube, Instagram, TikTok, Threads, Twitter/X"

    # Detect platform
    platform = detect_platform(url)
    if not platform:
        return False, None, "Could not detect platform. Please ensure the URL is a valid video link."

    return True, platform, None


def sanitize_filename(filename: str) -> str:
    """Sanitize filename to prevent path traversal and other issues"""
    # Remove path separators
    filename = filename.replace("/", "_").replace("\\", "_")

    # Control characters (newlines from post captions, tabs, NUL...) break
    # Content-Disposition on some browsers (iOS Safari): fold into spaces
    filename = re.sub(r"[\x00-\x1f\x7f]+", " ", filename)
    filename = re.sub(r"\s+", " ", filename).strip()

    # Remove or replace problematic characters
    filename = re.sub(r'[<>:"|?*]', "_", filename)

    # Limit length
    name, ext = os.path.splitext(filename)
    if len(name) > 200:
        name = name[:200]
    filename = name + ext

    # Ensure it doesn't start with a dot (hidden file) or dash
    while filename.startswith((".", "-")):
        filename = filename[1:]

    # Default name if empty
    if not filename or filename == ext:
        filename = "download" + ext

    return filename


def get_safe_filepath(job_id: str, filename: str) -> Path:
    """Get a safe file path within the temp directory"""
    safe_filename = sanitize_filename(filename)
    job_dir = settings.temp_dir / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    filepath = job_dir / safe_filename

    # Ensure path is within temp directory (prevent path traversal)
    try:
        filepath.resolve().relative_to(settings.temp_dir.resolve())
    except ValueError:
        raise ValueError("Invalid file path: path traversal detected")

    return filepath


def get_directory_size(path: Path) -> int:
    """Get total size of a directory in bytes"""
    total = 0
    if path.exists():
        for item in path.rglob("*"):
            if item.is_file():
                total += item.stat().st_size
    return total


# yt-dlp intermediate artifacts that are never a finished output
TEMP_SUFFIXES = (".part", ".ytdl", ".temp")


def free_disk_bytes() -> int:
    try:
        return shutil.disk_usage(settings.temp_dir).free
    except OSError:
        return 0


def _unique_size(dirs: list[Path]) -> int:
    """Bytes used by these directories; files hard-linked between them (cache
    hits) count once."""
    seen = set()
    total = 0
    for job_dir in dirs:
        for item in job_dir.glob("*"):
            try:
                stat = item.stat()
            except OSError:
                continue
            if (stat.st_dev, stat.st_ino) not in seen:
                seen.add((stat.st_dev, stat.st_ino))
                total += stat.st_size
    return total


def enforce_storage(active_job_ids: Optional[set[str]] = None, needed_bytes: int = 0) -> int:
    """Remove leftovers and keep the file cache within its limits.

    - Directories with partial files (or nothing to serve) are removed after
      ``max_file_age_hours``.
    - Finished downloads are the cache: removed after ``cache_max_age_hours``,
      and least recently used first while the cache is over ``cache_max_gb``
      or the disk has less than ``min_free_disk_mb`` (+ ``needed_bytes``) free.

    Directories of running jobs are never touched: their mtime doesn't change
    while yt-dlp grows a .part file. Returns the number of directories removed.
    """
    import time

    active_job_ids = active_job_ids or set()
    if not settings.temp_dir.exists():
        return 0

    now = time.time()
    removed = 0
    cache: list[tuple[float, Path]] = []

    def remove(job_dir: Path) -> None:
        nonlocal removed
        shutil.rmtree(job_dir, ignore_errors=True)
        removed += 1

    for job_dir in settings.temp_dir.iterdir():
        if not job_dir.is_dir() or job_dir.name in active_job_ids:
            continue
        try:
            age = now - job_dir.stat().st_mtime
            files = [f for f in job_dir.iterdir() if f.is_file()]
        except OSError:
            continue
        finished = bool(files) and not any(f.name.endswith(TEMP_SUFFIXES) for f in files)
        if not finished:
            if age > settings.max_file_age_hours * 3600:
                remove(job_dir)
        elif age > settings.cache_max_age_hours * 3600:
            remove(job_dir)
        else:
            cache.append((now - age, job_dir))

    cache.sort()  # least recently used first
    budget = settings.cache_max_gb * 1024 ** 3
    wanted_free = settings.min_free_disk_mb * 1024 * 1024 + needed_bytes
    while cache and (
        _unique_size([d for _, d in cache]) > budget or free_disk_bytes() < wanted_free
    ):
        remove(cache.pop(0)[1])
    return removed


def link_job_files(files: list[Path], destination: Path) -> None:
    """Give a new job the files of a cached one without copying them."""
    destination.mkdir(parents=True, exist_ok=True)
    for source in files:
        target = destination / source.name
        try:
            os.link(source, target)
        except OSError:
            shutil.copy2(source, target)
    # Both now count as just used for the cache's LRU order
    now = None
    os.utime(destination, now)
    if files:
        os.utime(files[0].parent, now)


async def cleanup_old_files(active_job_ids: Optional[set[str]] = None) -> int:
    """Periodic cleanup (see enforce_storage)."""
    return await asyncio.to_thread(enforce_storage, active_job_ids)


async def run_cleanup_task():
    """Background task to periodically clean up old files"""
    while True:
        try:
            await asyncio.sleep(settings.cleanup_interval_minutes * 60)
            # Lazy import: download_service imports this module
            from .download_service import download_service

            cleaned = await cleanup_old_files(set(download_service.active_jobs))
            if cleaned > 0:
                logger.info("Cleaned up %d old job directories", cleaned)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.exception("Cleanup error: %s", e)


def format_file_size(size_bytes: int) -> str:
    """Format bytes to human readable size"""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"


def format_duration(seconds: int) -> str:
    """Format seconds to HH:MM:SS"""
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{int(hours):02d}:{int(minutes):02d}:{int(seconds):02d}"
    return f"{int(minutes):02d}:{int(seconds):02d}"
