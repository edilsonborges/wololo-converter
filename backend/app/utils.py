"""Utility functions for URL validation, security, and file handling"""
import os
import re
import shutil
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import urlparse
import asyncio

from .config import settings


# Platform detection patterns
PLATFORM_PATTERNS = {
    "youtube": [
        r"(?:https?://)?(?:www\.)?youtube\.com/watch\?v=[\w-]+",
        r"(?:https?://)?(?:www\.)?youtube\.com/shorts/[\w-]+",
        r"(?:https?://)?youtu\.be/[\w-]+",
        r"(?:https?://)?(?:www\.)?youtube\.com/embed/[\w-]+",
    ],
    "instagram": [
        r"(?:https?://)?(?:www\.)?instagram\.com/(?:p|reel|tv)/[\w-]+",
    ],
    "facebook": [
        r"(?:https?://)?(?:www\.)?facebook\.com/.+/videos/\d+",
        r"(?:https?://)?(?:www\.)?facebook\.com/watch/?\?v=\d+",
        r"(?:https?://)?fb\.watch/[\w-]+",
    ],
    "twitter": [
        r"(?:https?://)?(?:www\.)?(?:twitter|x)\.com/\w+/status/\d+",
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
        return False, None, "Domain not supported. Supported platforms: YouTube, Instagram, Facebook, Twitter/X"

    # Detect platform
    platform = detect_platform(url)
    if not platform:
        return False, None, "Could not detect platform. Please ensure the URL is a valid video link."

    return True, platform, None


def sanitize_filename(filename: str) -> str:
    """Sanitize filename to prevent path traversal and other issues"""
    # Remove path separators
    filename = filename.replace("/", "_").replace("\\", "_")

    # Remove null bytes
    filename = filename.replace("\x00", "")

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


async def cleanup_old_files() -> int:
    """Clean up files older than max_file_age_hours. Returns number of files cleaned."""
    import time
    from datetime import timedelta

    cleaned = 0
    max_age_seconds = settings.max_file_age_hours * 3600
    now = time.time()

    if not settings.temp_dir.exists():
        return 0

    for job_dir in settings.temp_dir.iterdir():
        if not job_dir.is_dir():
            continue

        try:
            # Check directory modification time
            mtime = job_dir.stat().st_mtime
            if now - mtime > max_age_seconds:
                shutil.rmtree(job_dir)
                cleaned += 1
        except Exception:
            pass  # Skip if we can't access/delete

    return cleaned


async def run_cleanup_task():
    """Background task to periodically clean up old files"""
    while True:
        try:
            await asyncio.sleep(settings.cleanup_interval_minutes * 60)
            cleaned = await cleanup_old_files()
            if cleaned > 0:
                print(f"Cleaned up {cleaned} old job directories")
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"Cleanup error: {e}")


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
