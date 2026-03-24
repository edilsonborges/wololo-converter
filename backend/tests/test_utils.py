"""Tests for utility functions"""
import pytest
from app.utils import (
    detect_platform,
    is_allowed_domain,
    validate_url,
    sanitize_filename,
    format_file_size,
    format_duration,
)


class TestDetectPlatform:
    def test_youtube_watch(self):
        assert detect_platform("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "youtube"

    def test_youtube_short(self):
        assert detect_platform("https://youtube.com/shorts/abc123") == "youtube"

    def test_youtu_be(self):
        assert detect_platform("https://youtu.be/dQw4w9WgXcQ") == "youtube"

    def test_youtube_embed(self):
        assert detect_platform("https://www.youtube.com/embed/dQw4w9WgXcQ") == "youtube"

    def test_instagram_reel(self):
        assert detect_platform("https://www.instagram.com/reel/ABC123/") == "instagram"

    def test_instagram_post(self):
        assert detect_platform("https://instagram.com/p/ABC123/") == "instagram"

    def test_instagram_reels(self):
        assert detect_platform("https://www.instagram.com/reels/DWKQUcak0hC/") == "instagram"

    def test_twitter(self):
        assert detect_platform("https://twitter.com/user/status/123456789") == "twitter"

    def test_x_com(self):
        assert detect_platform("https://x.com/user/status/123456789") == "twitter"

    def test_facebook_video(self):
        assert detect_platform("https://www.facebook.com/user/videos/123456") == "facebook"

    def test_threads_post(self):
        assert detect_platform("https://www.threads.net/@zheray_kjr/post/DWMrfYPEons") == "threads"

    def test_threads_com(self):
        assert detect_platform("https://www.threads.com/@zheray_kjr/post/DWMrfYPEons") == "threads"

    def test_unknown_url(self):
        assert detect_platform("https://example.com/video") is None

    def test_empty_string(self):
        assert detect_platform("") is None


class TestIsAllowedDomain:
    def test_youtube_allowed(self):
        assert is_allowed_domain("https://www.youtube.com/watch?v=test") is True

    def test_instagram_allowed(self):
        assert is_allowed_domain("https://www.instagram.com/reel/test") is True

    def test_twitter_allowed(self):
        assert is_allowed_domain("https://twitter.com/user/status/123") is True

    def test_x_allowed(self):
        assert is_allowed_domain("https://x.com/user/status/123") is True

    def test_threads_allowed(self):
        assert is_allowed_domain("https://www.threads.net/@user/post/ABC123") is True

    def test_threads_com_allowed(self):
        assert is_allowed_domain("https://www.threads.com/@user/post/ABC123") is True

    def test_unknown_domain_rejected(self):
        assert is_allowed_domain("https://evil.com/video") is False

    def test_domain_with_port(self):
        assert is_allowed_domain("https://youtube.com:443/watch?v=test") is True

    def test_invalid_url(self):
        assert is_allowed_domain("not-a-url") is False


class TestValidateUrl:
    def test_valid_youtube_url(self):
        is_valid, platform, error = validate_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        assert is_valid is True
        assert platform == "youtube"
        assert error is None

    def test_valid_instagram_url(self):
        is_valid, platform, error = validate_url("https://www.instagram.com/reel/ABC123/")
        assert is_valid is True
        assert platform == "instagram"
        assert error is None

    def test_valid_twitter_url(self):
        is_valid, platform, error = validate_url("https://x.com/user/status/123456789")
        assert is_valid is True
        assert platform == "twitter"
        assert error is None

    def test_empty_url(self):
        is_valid, platform, error = validate_url("")
        assert is_valid is False
        assert error is not None

    def test_no_protocol(self):
        is_valid, platform, error = validate_url("youtube.com/watch?v=test")
        assert is_valid is False

    def test_disallowed_domain(self):
        is_valid, platform, error = validate_url("https://evil.com/video")
        assert is_valid is False
        assert "not supported" in error.lower() or "Domain" in error

    def test_whitespace_trimmed(self):
        is_valid, platform, error = validate_url("  https://www.youtube.com/watch?v=dQw4w9WgXcQ  ")
        assert is_valid is True


class TestSanitizeFilename:
    def test_normal_filename(self):
        assert sanitize_filename("video.mp4") == "video.mp4"

    def test_path_traversal(self):
        result = sanitize_filename("../../etc/passwd")
        assert "/" not in result
        assert "\\" not in result

    def test_special_characters(self):
        result = sanitize_filename('video<>:"|?*.mp4')
        assert "<" not in result
        assert ">" not in result

    def test_long_filename(self):
        long_name = "a" * 300 + ".mp4"
        result = sanitize_filename(long_name)
        assert len(result) <= 204  # 200 + .mp4

    def test_hidden_file(self):
        result = sanitize_filename(".hidden.mp4")
        assert not result.startswith(".")

    def test_null_bytes(self):
        result = sanitize_filename("video\x00.mp4")
        assert "\x00" not in result

    def test_empty_becomes_default(self):
        result = sanitize_filename("")
        assert result.startswith("download")

    def test_only_extension(self):
        # ".mp4" -> dot stripped as hidden file -> "mp4" (no ext left)
        result = sanitize_filename(".mp4")
        assert result == "mp4"


class TestFormatFileSize:
    def test_bytes(self):
        assert format_file_size(500) == "500.0 B"

    def test_kilobytes(self):
        assert format_file_size(1500) == "1.5 KB"

    def test_megabytes(self):
        result = format_file_size(1024 * 1024 * 5)
        assert "MB" in result

    def test_gigabytes(self):
        result = format_file_size(1024 * 1024 * 1024 * 2)
        assert "GB" in result


class TestFormatDuration:
    def test_seconds_only(self):
        assert format_duration(45) == "00:45"

    def test_minutes_and_seconds(self):
        assert format_duration(125) == "02:05"

    def test_hours(self):
        assert format_duration(3661) == "01:01:01"

    def test_zero(self):
        assert format_duration(0) == "00:00"
