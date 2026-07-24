"""Tests for download service."""

from app.download_service import DownloadProgress, DownloadService
from app.models import JobStatus, VideoQuality


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
            "speed": 1024 * 1024 * 2,
            "eta": 65,
        })

        assert progress.status == JobStatus.DOWNLOADING

        # Downloads occupy the 0-70% range.
        # 50% of the download corresponds to 35% overall.
        assert progress.progress == 35.0
        assert "MiB/s" in progress.speed
        assert progress.eta == "01:05"

    def test_progress_hook_speed_kib(self):
        progress = DownloadProgress("test-123")

        progress.progress_hook({
            "status": "downloading",
            "total_bytes": 1000,
            "downloaded_bytes": 100,
            "speed": 512 * 1024,
        })

        assert "KiB/s" in progress.speed

    def test_progress_hook_speed_bytes(self):
        progress = DownloadProgress("test-123")

        progress.progress_hook({
            "status": "downloading",
            "total_bytes": 1000,
            "downloaded_bytes": 100,
            "speed": 500,
        })

        assert "B/s" in progress.speed

    def test_progress_hook_fragment_fallback(self):
        progress = DownloadProgress("test-123")

        progress.progress_hook({
            "status": "downloading",
            "fragment_index": 5,
            "fragment_count": 10,
        })

        # 5 of 10 fragments = 50% of the download phase.
        # The download phase occupies 70% of total progress.
        assert progress.progress == 35.0

    def test_progress_hook_finished(self):
        progress = DownloadProgress("test-123")

        progress.progress_hook({"status": "finished"})

        assert progress.progress == DownloadProgress.DOWNLOAD_MAX
        assert (
            "conversion" in progress.current_stage.lower()
            or "preparing" in progress.current_stage.lower()
        )

    def test_progress_hook_error(self):
        progress = DownloadProgress("test-123")

        progress.progress_hook({
            "status": "error",
            "error": "Network error",
        })

        assert progress.status == JobStatus.FAILED

    def test_postprocessor_hook_copystream(self):
        progress = DownloadProgress("test-123")

        progress.postprocessor_hook({
            "status": "started",
            "postprocessor": "FFmpegCopyStream",
        })

        assert progress.status == JobStatus.CONVERTING
        assert progress.progress == DownloadProgress.CONVERSION_MIN

    def test_postprocessor_hook_extract_audio(self):
        progress = DownloadProgress("test-123")

        progress.postprocessor_hook({
            "status": "started",
            "postprocessor": "FFmpegExtractAudio",
        })

        assert progress.status == JobStatus.CONVERTING
        assert progress.progress == DownloadProgress.CONVERSION_MIN
        assert "audio" in progress.current_stage.lower()

    def test_postprocessor_hook_finished(self):
        progress = DownloadProgress("test-123")

        progress.postprocessor_hook({"status": "finished"})

        assert progress.progress == DownloadProgress.CONVERSION_MAX
        assert "finalizing" in progress.current_stage.lower()

    def test_callback_invoked(self):
        updates = []
        progress = DownloadProgress(
            "test-123",
            callback=lambda update: updates.append(update),
        )

        progress.progress_hook({
            "status": "downloading",
            "total_bytes": 100,
            "downloaded_bytes": 50,
        })

        assert updates
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

        opts = service.get_yt_dlp_options(
            "test-123",
            VideoQuality.Q_480P,
            progress,
        )

        assert opts["merge_output_format"] == "mp4"
        assert "height<=480" in opts["format"]
        assert opts["postprocessors"][0]["key"] == "FFmpegCopyStream"
        assert opts["postprocessor_args"]["copystream"] == [
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            "-threads",
            "0",
        ]

    def test_get_yt_dlp_options_video_quality_1080p(self):
        service = DownloadService()
        progress = DownloadProgress("test-123")

        opts = service.get_yt_dlp_options(
            "test-123",
            VideoQuality.Q_1080P,
            progress,
        )

        assert "height<=1080" in opts["format"]
        assert opts["merge_output_format"] == "mp4"

    def test_get_yt_dlp_options_mp3(self):
        service = DownloadService()
        progress = DownloadProgress("test-123")

        opts = service.get_yt_dlp_options(
            "test-123",
            VideoQuality.MP3,
            progress,
        )

        postprocessor = opts["postprocessors"][0]

        assert opts["format"] == "bestaudio/best"
        assert postprocessor["key"] == "FFmpegExtractAudio"
        assert postprocessor["preferredcodec"] == "mp3"
        assert postprocessor["preferredquality"] == "320"

    def test_get_yt_dlp_options_common_settings(self):
        service = DownloadService()
        progress = DownloadProgress("test-123")

        opts = service.get_yt_dlp_options(
            "test-123",
            VideoQuality.Q_480P,
            progress,
        )

        assert opts["noplaylist"] is True
        assert opts["socket_timeout"] == 30
        assert opts["retries"] == 3
        assert opts["fragment_retries"] == 3
        assert opts["max_filesize"] > 0
        assert opts["prefer_insecure"] is False

    def test_register_and_unregister_callback(self):
        service = DownloadService()
        callback = lambda update: None

        service.register_callback("test-123", callback)

        assert "test-123" in service.progress_callbacks

        service.unregister_callback("test-123")

        assert "test-123" not in service.progress_callbacks
