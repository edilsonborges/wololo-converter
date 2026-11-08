"""Tests for the Threads extractor"""
import httpx

from app import threads_extractor
from app.threads_extractor import _caption_title, extract_threads_info

# Real caption from https://www.threads.com/share/BAcQBWFSw_ (JSON-escaped as in the page)
RAW_CAPTION = (
    "The extreme cross pose is here !\\n\\nStart improving your flexibility in as little as 7 days "
    "with my daily stretching routine \\u2014 link in my bio \\u2705\\n\\n#stretching #mobility"
)


def test_caption_title_uses_first_line_only():
    assert _caption_title(RAW_CAPTION) == "The extreme cross pose is here !"


def test_caption_title_truncates_long_lines_at_a_word():
    title = _caption_title("word " * 40)
    assert len(title) <= threads_extractor.TITLE_MAX_CHARS + 1
    assert title.endswith("…")
    assert "  " not in title


def test_caption_title_keeps_accents_and_emoji():
    # Unescaped UTF-8 in the page must not turn into mojibake
    assert _caption_title("Pôr do sol em São Paulo ✅\\nmais") == "Pôr do sol em São Paulo ✅"


def test_caption_title_empty_caption():
    assert _caption_title("\\n\\n  ") == ""


def test_extract_threads_info_builds_short_title(monkeypatch):
    page = (
        '"video_versions":[{"type":101,"url":"https:\\/\\/cdn.example.com\\/v.mp4"}]'
        f'"caption":{{"text":"{RAW_CAPTION}"}}"username":"naoto_mo7575_1"'
    )

    class FakeResponse:
        text = page

        def raise_for_status(self):
            return None

    monkeypatch.setattr(httpx, "get", lambda *args, **kwargs: FakeResponse())

    info = extract_threads_info("https://www.threads.com/share/BAcQBWFSw_")

    assert info["title"] == "@naoto_mo7575_1: The extreme cross pose is here !"
    assert info["video_url"] == "https://cdn.example.com/v.mp4"
    assert "\n" not in info["title"]
