"""Custom Threads video extractor — scrapes video data from Threads post pages."""
import re
from typing import Optional
from urllib.parse import unquote

import httpx

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
}


def extract_threads_info(url: str) -> dict:
    """
    Fetch a Threads post page and extract video metadata.

    Returns dict with keys: title, video_url, thumbnail_url, duration,
    width, height, username.
    Raises ValueError if the post has no video or cannot be parsed.
    """
    resp = httpx.get(url, headers=_HEADERS, follow_redirects=True, timeout=20)
    resp.raise_for_status()
    text = resp.text

    # --- video URL (type 101 = progressive mp4) ---
    m = re.search(r'"video_versions":\[\{"type":101,"url":"([^"]+)"', text)
    if not m:
        raise ValueError("No video found in this Threads post")

    video_url = m.group(1).replace("\\/", "/")
    # Fix double-encoded percent signs (\u00253D → %3D)
    video_url = video_url.replace("\\u00253D", "%3D")
    video_url = re.sub(r"\\u0025(\w{2})", lambda x: "%" + x.group(1), video_url)

    # --- dimensions ---
    width: Optional[int] = None
    height: Optional[int] = None
    wm = re.search(r'"original_width":(\d+)', text)
    hm = re.search(r'"original_height":(\d+)', text)
    if wm:
        width = int(wm.group(1))
    if hm:
        height = int(hm.group(1))

    # --- caption / title ---
    caption = ""
    cm = re.search(r'"caption":\{"text":"((?:[^"\\]|\\.)*)"', text)
    if cm:
        caption = cm.group(1).encode().decode("unicode_escape", errors="replace")

    # --- username ---
    username = ""
    um = re.search(r'"username":"([^"]+)"', text)
    if um:
        username = um.group(1)

    title = f"@{username}: {caption}" if caption else f"@{username} – Threads"

    # --- thumbnail ---
    thumbnail_url = None
    og = re.search(r'property="og:image"\s+content="([^"]+)"', text)
    if og:
        thumbnail_url = og.group(1)

    # --- duration ---
    duration: Optional[float] = None
    dm = re.search(r'"video_duration":([\d.]+)', text)
    if dm:
        duration = float(dm.group(1))

    return {
        "title": title,
        "video_url": video_url,
        "thumbnail_url": thumbnail_url,
        "duration": duration,
        "width": width,
        "height": height,
        "username": username,
    }
