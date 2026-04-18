"""Tests for Instagram codec strategy (stream copy vs re-encode)."""
from app.download_service import _pick_instagram_codec_strategy


def _fmt(vcodec: str, height: int) -> dict:
    return {"vcodec": vcodec, "height": height}


class TestPickInstagramCodecStrategy:
    def test_h264_available_within_height_returns_stream_copy(self):
        info = {
            "formats": [
                _fmt("vp9", 1080),
                _fmt("avc1.64001f", 720),
            ]
        }
        args = _pick_instagram_codec_strategy(info, height=720)
        assert args[:2] == ["-c", "copy"]
        assert "libx264" not in args

    def test_h264_with_h264_alias_returns_stream_copy(self):
        info = {"formats": [_fmt("h264", 720)]}
        args = _pick_instagram_codec_strategy(info, height=1080)
        assert args[:2] == ["-c", "copy"]

    def test_only_vp9_returns_reencode(self):
        info = {"formats": [_fmt("vp9", 720), _fmt("vp09.00.30.08", 1080)]}
        args = _pick_instagram_codec_strategy(info, height=720)
        assert "-c:v" in args
        assert "libx264" in args
        assert "veryfast" in args

    def test_h264_above_target_height_triggers_reencode(self):
        info = {"formats": [_fmt("avc1.64001f", 1080)]}
        args = _pick_instagram_codec_strategy(info, height=720)
        assert "libx264" in args

    def test_empty_formats_returns_reencode(self):
        args = _pick_instagram_codec_strategy({"formats": []}, height=720)
        assert "libx264" in args

    def test_missing_formats_returns_reencode(self):
        args = _pick_instagram_codec_strategy({}, height=720)
        assert "libx264" in args

    def test_formats_with_none_codec_are_skipped(self):
        info = {
            "formats": [
                {"vcodec": "none", "height": 720},
                _fmt("avc1", 480),
            ]
        }
        args = _pick_instagram_codec_strategy(info, height=720)
        assert args[:2] == ["-c", "copy"]

    def test_stream_copy_preserves_faststart_and_threads(self):
        info = {"formats": [_fmt("avc1", 720)]}
        args = _pick_instagram_codec_strategy(info, height=720)
        assert "+faststart" in args
        assert "-threads" in args

    def test_reencode_copies_audio_and_sets_faststart(self):
        info = {"formats": [_fmt("vp9", 720)]}
        args = _pick_instagram_codec_strategy(info, height=720)
        # Audio is copied (not re-encoded)
        assert args[args.index("-c:a") + 1] == "copy"
        assert "+faststart" in args
