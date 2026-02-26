"""Tests for download service"""
import pytest
from app.download_service import DownloadProgress, DownloadService
from app.models import JobStatus, OutputFormat


class TestDownloadProgress:
    def test_initial_state(self):
        progress = DownloadProgress("test-123")
        assert progress.job_id == "test-123"
        assert progress.status == JobStatus.QUEUED
        assert progress.progress == 0.0

    def test_progress_hook_downloading(self):
        progress = DownloadProgress("test-123")
        progress.progress_hook({
            "status": "downloading",
            "total_bytes": 1000,
            "downloaded_bytes": 500,
            "speed": 1024 * 1024 * 2,  # 2 MiB/s
            "eta": 65,
        })
        assert progress.status == JobStatus.DOWNLOADING
        assert progress.progress == 50.0
        assert "MiB/s" in progress.speed
        assert progress.eta == "01:05"

    def test_progress_hook_speed_kib(self):
        progress = DownloadProgress("test-123")
        progress.progress_hook({
            "status": "downloading",
            "total_bytes": 1000,
            "downloaded_bytes": 100,
            "speed": 512 * 1024,  # 512 KiB/s
        })
        assert "KiB/s" in progress.speed

    def test_progress_hook_speed_bytes(self):
        progress = DownloadProgress("test-123")
        progress.progress_hook({
            "status": "downloading",
            "total_bytes": 1000,
            "downloaded_bytes": 100,
            "speed": 500,  # 500 B/s
        })
        assert "B/s" in progress.speed

    def test_progress_hook_fragment_fallback(self):
        progress = DownloadProgress("test-123")
        progress.progress_hook({
            "status": "downloading",
            "fragment_index": 5,
            "fragment_count": 10,
        })
        assert progress.progress == 50.0

    def test_progress_hook_finished(self):
        progress = DownloadProgress("test-123")
        progress.progress_hook({"status": "finished"})
        assert progress.progress == 88
        assert "conversion" in progress.current_stage.lower() or "preparing" in progress.current_stage.lower()

    def test_progress_hook_error(self):
        progress = DownloadProgress("test-123")
        progress.progress_hook({"status": "error", "error": "Network error"})
        assert progress.status == JobStatus.FAILED

    def test_postprocessor_hook_copystream(self):
        progress = DownloadProgress("test-123")
        progress.postprocessor_hook({"status": "started", "postprocessor": "FFmpegCopyStream"})
        assert progress.status == JobStatus.CONVERTING
        assert progress.progress == 90

    def test_postprocessor_hook_extract_audio(self):
        progress = DownloadProgress("test-123")
        progress.postprocessor_hook({"status": "started", "postprocessor": "FFmpegExtractAudio"})
        assert progress.status == JobStatus.CONVERTING
        assert "audio" in progress.current_stage.lower()

    def test_postprocessor_hook_finished(self):
        progress = DownloadProgress("test-123")
        progress.postprocessor_hook({"status": "finished"})
        assert progress.progress == 98
        assert "finalizing" in progress.current_stage.lower()

    def test_callback_invoked(self):
        updates = []
        progress = DownloadProgress("test-123", callback=lambda u: updates.append(u))
        progress.progress_hook({
            "status": "downloading",
            "total_bytes": 100,
            "downloaded_bytes": 50,
        })
        assert len(updates) > 0
        assert updates[0].job_id == "test-123"

    def test_eta_with_hours(self):
        progress = DownloadProgress("test-123")
        progress.progress_hook({
            "status": "downloading",
            "total_bytes": 1000,
            "downloaded_bytes": 100,
            "eta": 3661,
        })
        assert progress.eta == "01:01:01"

    def test_eta_without_hours(self):
        progress = DownloadProgress("test-123")
        progress.progress_hook({
            "status": "downloading",
            "total_bytes": 1000,
            "downloaded_bytes": 100,
            "eta": 125,
        })
        assert progress.eta == "02:05"


class TestDownloadService:
    def test_initial_state(self):
        service = DownloadService()
        assert service.active_count == 0

    def test_get_yt_dlp_options_video(self):
        service = DownloadService()
        progress = DownloadProgress("test-123")
        opts = service.get_yt_dlp_options("test-123", OutputFormat.VIDEO, progress)
        assert opts["merge_output_format"] == "mp4"
        assert "-preset" in opts["postprocessor_args"]["copystream"]
        assert "fast" in opts["postprocessor_args"]["copystream"]
        assert "-threads" in opts["postprocessor_args"]["copystream"]

    def test_get_yt_dlp_options_video_webm(self):
        service = DownloadService()
        progress = DownloadProgress("test-123")
        opts = service.get_yt_dlp_options("test-123", OutputFormat.VIDEO_WEBM, progress)
        assert opts["merge_output_format"] == "webm"

    def test_get_yt_dlp_options_mp3(self):
        service = DownloadService()
        progress = DownloadProgress("test-123")
        opts = service.get_yt_dlp_options("test-123", OutputFormat.AUDIO_MP3, progress)
        assert opts["postprocessors"][0]["key"] == "FFmpegExtractAudio"
        assert opts["postprocessors"][0]["preferredcodec"] == "mp3"

    def test_get_yt_dlp_options_m4a(self):
        service = DownloadService()
        progress = DownloadProgress("test-123")
        opts = service.get_yt_dlp_options("test-123", OutputFormat.AUDIO_M4A, progress)
        assert opts["postprocessors"][0]["preferredcodec"] == "m4a"

    def test_get_yt_dlp_options_wav(self):
        service = DownloadService()
        progress = DownloadProgress("test-123")
        opts = service.get_yt_dlp_options("test-123", OutputFormat.AUDIO_WAV, progress)
        assert opts["postprocessors"][0]["preferredcodec"] == "wav"

    def test_get_yt_dlp_options_flac(self):
        service = DownloadService()
        progress = DownloadProgress("test-123")
        opts = service.get_yt_dlp_options("test-123", OutputFormat.AUDIO_FLAC, progress)
        assert opts["postprocessors"][0]["preferredcodec"] == "flac"

    def test_get_yt_dlp_options_ogg(self):
        service = DownloadService()
        progress = DownloadProgress("test-123")
        opts = service.get_yt_dlp_options("test-123", OutputFormat.AUDIO_OGG, progress)
        assert opts["postprocessors"][0]["preferredcodec"] == "vorbis"

    def test_get_yt_dlp_options_common_settings(self):
        service = DownloadService()
        progress = DownloadProgress("test-123")
        opts = service.get_yt_dlp_options("test-123", OutputFormat.VIDEO, progress)
        assert opts["noplaylist"] is True
        assert opts["socket_timeout"] == 30
        assert opts["retries"] == 3

    def test_register_and_unregister_callback(self):
        service = DownloadService()
        cb = lambda u: None
        service.register_callback("test-123", cb)
        assert "test-123" in service.progress_callbacks
        service.unregister_callback("test-123")
        assert "test-123" not in service.progress_callbacks
