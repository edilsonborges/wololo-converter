"""Tests for Pydantic schemas"""
import pytest
from pydantic import ValidationError
from app.schemas import DownloadRequest, JobProgressUpdate
from app.models import JobStatus, OutputFormat, VideoQuality


class TestDownloadRequest:
    def test_valid_request(self):
        req = DownloadRequest(url="https://www.youtube.com/watch?v=test123")
        assert req.url == "https://www.youtube.com/watch?v=test123"
        assert req.quality == VideoQuality.Q_480P
        assert req.output_format is None

    def test_valid_request_with_format(self):
        req = DownloadRequest(url="https://www.youtube.com/watch?v=test123", output_format="audio_mp3")
        assert req.output_format == OutputFormat.AUDIO_MP3

    def test_all_formats_accepted(self):
        for fmt in OutputFormat:
            req = DownloadRequest(url="https://www.youtube.com/watch?v=test123", output_format=fmt.value)
            assert req.output_format == fmt

    def test_invalid_url_no_protocol(self):
        with pytest.raises(ValidationError):
            DownloadRequest(url="youtube.com/watch?v=test")

    def test_url_too_short(self):
        with pytest.raises(ValidationError):
            DownloadRequest(url="http://a")

    def test_url_whitespace_stripped(self):
        req = DownloadRequest(url="  https://www.youtube.com/watch?v=test123  ")
        assert req.url == "https://www.youtube.com/watch?v=test123"


class TestJobProgressUpdate:
    def test_minimal_progress(self):
        update = JobProgressUpdate(
            job_id="test-123",
            status=JobStatus.DOWNLOADING,
            progress=50.0,
        )
        assert update.job_id == "test-123"
        assert update.progress == 50.0
        assert update.download_ready is False

    def test_complete_progress(self):
        update = JobProgressUpdate(
            job_id="test-123",
            status=JobStatus.COMPLETED,
            progress=100.0,
            speed="5.0 MiB/s",
            eta="00:00",
            current_stage="Complete!",
            title="Test Video",
            download_ready=True,
        )
        assert update.download_ready is True
        assert update.title == "Test Video"
