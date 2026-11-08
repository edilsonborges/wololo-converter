"""Resolve artlist.io album/song links to matching YouTube videos.

The track list is read with a headless browser (the site sits behind a
Cloudflare check), then each track is searched on YouTube and matched by
title, rendition (instrumental, remix, ...) and duration. The matching rules
mirror scripts/tracks-to-mp3.mjs.
"""
import json
import logging
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from typing import Optional
from urllib.parse import quote_plus

import httpx

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/143.0 Safari/537.36"
)
SOURCE_URL_RE = re.compile(
    r"^https?://(?:www\.)?artlist\.io/royalty-free-music/(album|song)/[^/?#]+/\d+",
    re.IGNORECASE,
)

# Words that mark a different rendition. A candidate with one of these words
# that the track title doesn't have is another version of the song.
VARIANT_WORDS = {
    "instrumental", "karaoke", "remix", "live", "cover", "sped", "slowed", "reverb",
    "nightcore", "8d", "extended", "acapella", "cappella", "mix", "edit", "loop", "hour",
}

# One browser at a time: Chromium is memory hungry
browser_executor = ThreadPoolExecutor(max_workers=1)


def is_music_link(url: str) -> bool:
    return bool(SOURCE_URL_RE.match(url.strip()))


# ------------------------------------------------------------------ matching

def normalize(text: Optional[str]) -> str:
    text = unicodedata.normalize("NFD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _tokens(text: Optional[str]) -> set[str]:
    return set(normalize(text).split())


def base_title(title: str) -> str:
    """'Dale Candela - Instrumental version' -> 'Dale Candela'"""
    title = re.sub(r"\s*[-–]\s*[^-–]*\bversion\b\s*$", "", title, flags=re.IGNORECASE)
    title = re.sub(
        r"\s*[(\[][^)\]]*\b(version|instrumental)\b[^)\]]*[)\]]\s*$", "", title, flags=re.IGNORECASE
    )
    return title.strip()


def parse_duration(value) -> Optional[int]:
    """'3:16', '1:02:03' or ISO 'PT3M15S' -> seconds"""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    value = str(value).strip()
    iso = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", value, re.IGNORECASE)
    if iso:
        h, m, s = (int(g) if g else 0 for g in iso.groups())
        return h * 3600 + m * 60 + s
    try:
        parts = [int(p) for p in value.split(":")]
    except ValueError:
        return None
    total = 0
    for part in parts:
        total = total * 60 + part
    return total


def search_query(track: dict) -> str:
    instrumental = " instrumental" if "instrumental" in track["title"].lower() else ""
    return f"{track['artist']} {base_title(track['title'])}{instrumental}".strip()


def pick_best_match(track: dict, candidates: list[dict], tolerance: Optional[float] = None) -> Optional[dict]:
    """Return the candidate that is the same recording as the track, or None."""
    wanted = _tokens(base_title(track["title"]))
    track_words = _tokens(track["title"])
    artist = normalize(track.get("artist"))
    duration = track.get("duration")
    if duration is None:
        return None
    tolerance = tolerance if tolerance is not None else max(4, duration * 0.03)

    scored = []
    for candidate in candidates:
        if candidate.get("duration") is None:
            continue
        words = _tokens(candidate["title"])
        if not wanted <= words:
            continue
        if any(w in words and w not in track_words for w in VARIANT_WORDS):
            continue
        if "instrumental" in track_words and "instrumental" not in words:
            continue
        diff = abs(candidate["duration"] - duration)
        if diff > tolerance:
            continue

        # Prefer the artist's own channel (incl. "Artist - Topic"), then
        # uploads naming the artist, then anything else
        penalty = 5
        if artist and artist in normalize(candidate.get("channel")):
            penalty = 0
        elif artist and artist in normalize(candidate["title"]):
            penalty = 2
        scored.append((diff + penalty, diff, candidate))

    if not scored:
        return None
    scored.sort(key=lambda s: s[0])
    return scored[0][2]


# ------------------------------------------------------------------ sources

_RECORDING_JS = """(els) => {
  for (const s of els) {
    try { const d = JSON.parse(s.textContent); if (d['@type'] === 'MusicRecording') return d; } catch (e) {}
  }
  return null;
}"""

PAGE_ATTEMPTS = 3
SEARCH_ATTEMPTS = 2


def _allow_document_only(route):
    """Load only the HTML (and Cloudflare's check). Everything we need is in
    the server-rendered page; running the site's heavy JavaScript in a
    GPU-less container pins the CPU and stalls the page."""
    request = route.request
    if (
        request.resource_type == "document"
        or "challenges.cloudflare.com" in request.url
        or "/cdn-cgi/" in request.url
    ):
        return route.continue_()
    return route.abort()


def _open(browser, url: str):
    """Open a page, waiting through Cloudflare's check; retries with a fresh
    browser context because the check occasionally doesn't clear."""
    last_error = None
    for attempt in range(PAGE_ATTEMPTS):
        context = browser.new_context(user_agent=USER_AGENT)
        page = context.new_page()
        page.route("**/*", _allow_document_only)
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_function(
                "() => !/just a moment/i.test(document.title) && !!document.querySelector('h1')",
                timeout=20000,
                polling=500,
            )
            return context, page
        except Exception as e:
            last_error = e
            logger.warning("Music page check did not clear (attempt %d): %s", attempt + 1, url)
            context.close()
    raise ValueError("The music page is temporarily blocking access, try again in a minute") from last_error


def _read_song(browser, url: str) -> dict:
    context, page = _open(browser, url)
    try:
        recording = page.eval_on_selector_all('script[type="application/ld+json"]', _RECORDING_JS)
    finally:
        context.close()
    if not recording:
        raise ValueError("Could not read the song details")
    artist = (recording.get("byArtist") or {}).get("name") or (recording.get("producer") or {}).get("name") or ""
    return {
        "title": recording.get("name", ""),
        "artist": artist,
        "duration": parse_duration(recording.get("duration")),
        "source_url": url,
    }


def fetch_tracks(url: str) -> dict:
    """Read {album, tracks: [{title, artist, duration, source_url}]} from an album/song page.

    Album pages only render durations client-side, so the album page gives the
    song links and each song page gives title, artist and duration (JSON-LD).
    """
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            if "/album/" not in url:
                track = _read_song(browser, url)
                return {"album": track["title"], "tracks": [track]}

            context, page = _open(browser, url)
            try:
                album = page.locator("h1").first.inner_text().strip()
                song_urls = page.eval_on_selector_all(
                    'a[href*="/royalty-free-music/song/"]',
                    "els => [...new Set(els.map((a) => a.href.split(/[?#]/)[0]))]",
                )
            finally:
                context.close()
            return {"album": album, "tracks": [_read_song(browser, u) for u in song_urls]}
        finally:
            browser.close()


def search_youtube(query: str) -> list[dict]:
    """Search YouTube; returns [{id, title, channel, duration}]."""
    url = f"https://www.youtube.com/results?search_query={quote_plus(query)}&hl=en&gl=US"
    response = httpx.get(
        url,
        headers={"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9", "Cookie": "SOCS=CAI"},
        timeout=20,
        follow_redirects=True,
    )
    response.raise_for_status()
    match = re.search(r"var ytInitialData = (\{.*?\});</script>", response.text, re.DOTALL)
    if not match:
        raise ValueError("Could not parse YouTube search results")

    videos = []

    def walk(node):
        if isinstance(node, dict):
            if "videoRenderer" in node:
                videos.append(node["videoRenderer"])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(json.loads(match.group(1)))
    return [
        {
            "id": v.get("videoId"),
            "title": "".join(r.get("text", "") for r in (v.get("title") or {}).get("runs", [])),
            "channel": ((v.get("ownerText") or {}).get("runs") or [{}])[0].get("text", ""),
            "duration": parse_duration((v.get("lengthText") or {}).get("simpleText")),
        }
        for v in videos
        if v.get("videoId")
    ]


def resolve(url: str) -> dict:
    """Resolve a music link to {album, tracks: [{title, artist, duration, video_url, video_title}]}."""
    data = fetch_tracks(url)
    resolved = []
    for track in data["tracks"]:
        match = None
        candidates: list[dict] = []
        # YouTube results vary between identical searches; search again (and
        # merge) before giving up on a track
        for _ in range(SEARCH_ATTEMPTS):
            try:
                candidates += search_youtube(search_query(track))
            except Exception:
                logger.exception("YouTube search failed for %s - %s", track["artist"], track["title"])
            match = pick_best_match(track, candidates)
            if match:
                break
        resolved.append({
            **track,
            "video_url": f"https://www.youtube.com/watch?v={match['id']}" if match else None,
            "video_title": match["title"] if match else None,
        })
    return {"album": data["album"], "tracks": resolved}
