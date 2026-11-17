"""Estimate the size of a download before it starts, and refuse oversized ones.

yt-dlp reports a size for each format before downloading: ``filesize``
(exact, YouTube gives it for most formats) or ``filesize_approx``. When a
platform reports neither, bitrate x duration is a fair estimate. MP3s are
encoded at 320 kbps, so their size follows from the duration.
"""
from typing import Optional

from .config import settings
from .models import VideoQuality

MP3_BYTES_PER_SECOND = 320_000 // 8
VIDEO_QUALITIES = (VideoQuality.Q_1080P, VideoQuality.Q_720P, VideoQuality.Q_480P, VideoQuality.Q_360P)


class DownloadRejected(Exception):
    """Refused before downloading (too large or too long)."""

    def __init__(self, message: str, estimated_size: Optional[int] = None,
                 suggested_quality: Optional[str] = None):
        super().__init__(message)
        self.estimated_size = estimated_size
        self.suggested_quality = suggested_quality


def format_bytes(size: float) -> str:
    """Short human size: 6.9 GB, 4 GB, 450 MB (decimal units, like the UI)."""
    if size >= 1e9:
        return f"{size / 1e9:.1f}".removesuffix(".0") + " GB"
    return f"{max(size / 1e6, 1):.0f} MB"


def video_format_spec(height: int) -> str:
    """yt-dlp format for a video quality: H.264 + AAC when available (plays
    everywhere), else the best streams up to that height (short side for
    portrait videos), never upscaled."""
    return (
        f"bestvideo[height<={height}][vcodec^=avc1]+bestaudio[acodec^=mp4a]/"
        f"bestvideo[height<={height}]+bestaudio/"
        f"bestvideo[width<={height}]+bestaudio/"
        f"best[height<={height}]/best[width<={height}]/best"
    )


def _select(ydl, info: dict, height: int) -> Optional[list[dict]]:
    """Ask yt-dlp which formats it would download (None if it can't say)."""
    formats = info.get("formats") or []
    try:
        selector = ydl.build_format_selector(video_format_spec(height))
        chosen = next(iter(selector({
            "formats": formats,
            "has_merged_format": any(_is_combined(f) for f in formats),
            "incomplete_formats": False,
        })), None)
    except Exception:
        return None
    if not chosen:
        return None
    return chosen.get("requested_formats") or [chosen]


def format_size(fmt: dict, duration: Optional[float]) -> Optional[int]:
    """Size of one format in bytes, or None when nothing tells."""
    size = fmt.get("filesize") or fmt.get("filesize_approx")
    if size:
        return int(size)
    bitrate = fmt.get("tbr") or (fmt.get("vbr") or 0) + (fmt.get("abr") or 0)
    if bitrate and duration:
        return int(bitrate * 1000 / 8 * duration)
    return None


def _is_video_only(fmt: dict) -> bool:
    return fmt.get("vcodec") != "none" and fmt.get("acodec") == "none" and bool(fmt.get("height"))


def _is_audio_only(fmt: dict) -> bool:
    return fmt.get("vcodec") == "none" and fmt.get("acodec") not in (None, "none")


def _is_combined(fmt: dict) -> bool:
    # Unknown codecs (None) count as present: many extractors leave them out
    return fmt.get("vcodec") != "none" and fmt.get("acodec") != "none" and bool(fmt.get("height"))


def _rank(fmt: dict) -> tuple:
    return (fmt.get("height") or 0, fmt.get("fps") or 0, fmt.get("tbr") or 0)


def _pick_formats(formats: list[dict], height: int) -> list[dict]:
    """Mirror the format selection in DownloadService.get_yt_dlp_options:
    best H.264 video up to ``height`` + AAC audio, else best video + best
    audio, else a single file with both."""
    video_only = [f for f in formats if _is_video_only(f)]
    audio_only = [f for f in formats if _is_audio_only(f)]
    combined = [f for f in formats if _is_combined(f)]
    best_audio = lambda pool: max(pool, key=lambda f: f.get("abr") or f.get("tbr") or 0) if pool else None

    def fits(f, side="height"):
        return (f.get(side) or 0) and f[side] <= height

    avc = [f for f in video_only if fits(f) and str(f.get("vcodec", "")).startswith("avc1")]
    aac = [f for f in audio_only if str(f.get("acodec", "")).startswith("mp4a")]
    if avc and aac:
        return [max(avc, key=_rank), best_audio(aac)]
    for side in ("height", "width"):
        videos = [f for f in video_only if fits(f, side)]
        if videos and audio_only:
            return [max(videos, key=_rank), best_audio(audio_only)]
    for side in ("height", "width"):
        single = [f for f in combined if fits(f, side)]
        if single:
            return [max(single, key=_rank)]
    if combined:
        return [max(combined, key=_rank)]
    return []


def _total(formats: list[dict], duration: Optional[float]) -> Optional[int]:
    sizes = [format_size(f, duration) for f in formats]
    if not sizes or any(s is None for s in sizes):
        return None
    return sum(sizes)


def estimate_quality_sizes(info: dict, ydl=None) -> dict[str, int]:
    """Estimated size per quality (only the ones that can be estimated).
    With the yt-dlp instance the formats are the ones it would pick;
    without it, a close approximation of that choice."""
    duration = info.get("duration")
    formats = info.get("formats") or []
    sizes = {}
    for quality in VIDEO_QUALITIES:
        height = int(quality.value[:-1])
        picked = _select(ydl, info, height) if ydl is not None else None
        size = _total(picked if picked is not None else _pick_formats(formats, height), duration)
        if size:
            sizes[quality.value] = size
    if duration:
        sizes[VideoQuality.MP3.value] = int(duration * MP3_BYTES_PER_SECOND)
    return sizes


def estimate_download_size(info: dict, quality: VideoQuality) -> Optional[int]:
    """Size of what yt-dlp is about to download for this job."""
    duration = info.get("duration")
    if quality == VideoQuality.MP3:
        return int(duration * MP3_BYTES_PER_SECOND) if duration else None
    requested = info.get("requested_formats") or ([info] if info.get("format_id") else [])
    return _total(requested, duration)


def size_limit_bytes() -> int:
    return settings.max_file_size_mb * 1_000_000


def check_download(info: dict, quality: VideoQuality, ydl=None) -> Optional[int]:
    """Raise DownloadRejected when the job would be too large.

    Returns the estimated size (None when unknown). Without an estimate the
    duration limit applies instead, so a video of unknown size can't be
    arbitrarily long.
    """
    limit = size_limit_bytes()
    size = estimate_download_size(info, quality)
    if size is not None:
        if size <= limit:
            return size
        label = "MP3" if quality == VideoQuality.MP3 else quality.value
        message = f"This video is too large: ~{format_bytes(size)} at {label} (limit {format_bytes(limit)})."
        suggestion = suggest_quality(estimate_quality_sizes(info, ydl), quality)
        if suggestion:
            message += f" Try {suggestion[0]} (~{format_bytes(suggestion[1])})."
        raise DownloadRejected(message, size, suggestion[0] if suggestion else None)

    duration = info.get("duration")
    max_seconds = settings.max_duration_minutes * 60
    if duration and duration > max_seconds:
        hours = max_seconds / 3600
        raise DownloadRejected(
            f"This video is too long to download here (limit {hours:g} hours)."
        )
    return None


def suggest_quality(sizes: dict[str, int], requested: VideoQuality) -> Optional[tuple[str, int]]:
    """The best video quality below the requested one that fits the limit."""
    limit = size_limit_bytes()
    if requested == VideoQuality.MP3:
        return None
    candidates = VIDEO_QUALITIES[VIDEO_QUALITIES.index(requested) + 1:]
    for quality in candidates:
        size = sizes.get(quality.value)
        if size is not None and size <= limit:
            return quality.value, size
    return None
