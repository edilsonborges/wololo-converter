"""Tests for database models and enums"""
import pytest
from app.models import JobStatus, OutputFormat


class TestJobStatus:
    def test_all_statuses_exist(self):
        expected = ["queued", "validating", "downloading", "converting", "finalizing", "completed", "failed", "cancelled"]
        for status in expected:
            assert JobStatus(status) is not None

    def test_status_values(self):
        assert JobStatus.QUEUED.value == "queued"
        assert JobStatus.COMPLETED.value == "completed"
        assert JobStatus.FAILED.value == "failed"


class TestOutputFormat:
    def test_video_formats(self):
        assert OutputFormat.VIDEO.value == "video"
        assert OutputFormat.VIDEO_WEBM.value == "video_webm"

    def test_audio_formats(self):
        assert OutputFormat.AUDIO_MP3.value == "audio_mp3"
        assert OutputFormat.AUDIO_M4A.value == "audio_m4a"
        assert OutputFormat.AUDIO_WAV.value == "audio_wav"
        assert OutputFormat.AUDIO_FLAC.value == "audio_flac"
        assert OutputFormat.AUDIO_OGG.value == "audio_ogg"

    def test_total_format_count(self):
        assert len(OutputFormat) == 7
