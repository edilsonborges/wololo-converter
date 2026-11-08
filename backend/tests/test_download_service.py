"""Tests for download service."""

from types import SimpleNamespace

import httpx

from app import download_service as download_service_module
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

    def test_youtube_uses_supported_default_clients(self):
        service = DownloadService()
        progress = DownloadProgress("test-youtube")

        opts = service.get_yt_dlp_options(
            "test-youtube",
            VideoQuality.Q_480P,
            progress,
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        )

        assert "extractor_args" not in opts

    def test_register_and_unregister_callback(self):
        service = DownloadService()
        callback = lambda update: None

        service.register_callback("test-123", callback)

        assert "test-123" in service.progress_callbacks

        service.unregister_callback("test-123")

        assert "test-123" not in service.progress_callbacks

    async def test_late_progress_subscriber_receives_completed_mp3_update(
        self,
        monkeypatch,
    ):
        """A fast MP3 may finish before the browser opens its SSE stream."""
        service = DownloadService()

        def finish_immediately(url, job_id, quality, progress):
            assert quality == VideoQuality.MP3
            return {
                "success": True,
                "title": "Short audio",
                "filename": "short-audio.mp3",
            }

        monkeypatch.setattr(service, "_run_download", finish_immediately)

        job_id, task, _ = await service.start_download(
            "https://www.youtube.com/watch?v=test123",
            VideoQuality.MP3,
        )
        await task

        updates = []
        service.register_callback(job_id, updates.append)

        assert len(updates) == 1
        assert updates[0].status == JobStatus.COMPLETED
        assert updates[0].download_ready is True

    def test_threads_mp3_request_converts_custom_video_download(
        self,
        monkeypatch,
        tmp_path,
    ):
        class FakeResponse:
            headers = {"content-length": "5"}

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                return False

            def raise_for_status(self):
                return None

            def iter_bytes(self, chunk_size):
                yield b"video"

        monkeypatch.setattr(download_service_module.settings, "temp_dir", tmp_path)
        monkeypatch.setattr(
            download_service_module,
            "extract_threads_info",
            lambda url: {
                "title": "Thread audio",
                "video_url": "https://cdn.example.com/video.mp4",
                "duration": 10,
                "thumbnail_url": None,
            },
        )
        monkeypatch.setattr(httpx, "stream", lambda *args, **kwargs: FakeResponse())

        def fake_ffmpeg(args, **kwargs):
            assert "-vn" in args
            tmp_path.joinpath("job", "Thread audio.mp3").write_bytes(b"mp3")
            return SimpleNamespace(returncode=0, stderr=b"")

        monkeypatch.setattr("subprocess.run", fake_ffmpeg)

        result = DownloadService()._run_download(
            "https://www.threads.net/@user/post/123",
            "job",
            VideoQuality.MP3,
            DownloadProgress("job"),
        )

        assert result["success"] is True
        assert result["filename"] == "Thread audio.mp3"
        assert result["filepath"].endswith(".mp3")


class TestCancellation:
    def test_progress_hook_raises_after_cancel(self):
        import pytest
        import yt_dlp

        progress = DownloadProgress("job")
        progress.cancel_event.set()

        with pytest.raises(yt_dlp.utils.DownloadCancelled):
            progress.progress_hook({"status": "downloading", "downloaded_bytes": 1})
        with pytest.raises(yt_dlp.utils.DownloadCancelled):
            progress.postprocessor_hook({"status": "started", "postprocessor": "FFmpegCopyStream"})

    async def test_cancel_stops_worker_and_keeps_cancelled_state(self, monkeypatch, tmp_path):
        import asyncio
        import threading

        monkeypatch.setattr(download_service_module.settings, "temp_dir", tmp_path)
        service = DownloadService()
        started = threading.Event()
        finished_states = []

        def slow_download(url, job_id, quality, progress):
            # Simulate yt-dlp invoking the progress hook in a loop
            job_dir = tmp_path / job_id
            job_dir.mkdir()
            (job_dir / "video.mp4.part").write_bytes(b"partial")
            started.set()
            try:
                for _ in range(500):
                    progress.progress_hook({"status": "downloading", "downloaded_bytes": 1, "total_bytes": 10})
                    threading.Event().wait(0.01)
            except Exception as e:  # mirrors _run_download's handling
                return {"success": False, "error": str(e)}
            return {"success": True, "title": "t", "filename": "video.mp4"}

        monkeypatch.setattr(service, "_run_download", slow_download)

        async def on_finish(progress, result):
            finished_states.append((progress.status, result.get("cancelled")))

        job_id, task, _ = await service.start_download(
            "https://www.youtube.com/watch?v=test123",
            VideoQuality.Q_720P,
            on_finish=on_finish,
        )
        await asyncio.get_running_loop().run_in_executor(None, started.wait, 5)

        assert service.cancel_job(job_id) is True
        # Still counted as active until the worker thread really stops
        assert job_id in service.active_jobs

        await asyncio.wait_for(task, timeout=5)

        assert job_id not in service.active_jobs
        assert finished_states == [(JobStatus.CANCELLED, True)]
        assert not (tmp_path / job_id).exists()

    async def test_start_download_accepts_job_id_and_calls_on_finish(self, monkeypatch):
        service = DownloadService()
        monkeypatch.setattr(
            service,
            "_run_download",
            lambda url, job_id, quality, progress: {"success": True, "title": "T", "filename": "f.mp4"},
        )
        seen = []

        async def on_finish(progress, result):
            seen.append((progress.job_id, progress.status, result["filename"]))

        job_id, task, platform = await service.start_download(
            "https://www.youtube.com/watch?v=test123",
            VideoQuality.Q_720P,
            job_id="fixed-id",
            on_finish=on_finish,
        )
        await task

        assert job_id == "fixed-id"
        assert platform == "youtube"
        assert seen == [("fixed-id", JobStatus.COMPLETED, "f.mp4")]


class TestPreviewCookies:
    def test_preview_ignores_placeholder_cookies_file(self, monkeypatch, tmp_path):
        cookies = tmp_path / "cookies.txt"
        cookies.write_text("# Netscape HTTP Cookie File\n# placeholder\n")
        monkeypatch.setattr(download_service_module.settings, "cookies_file", str(cookies))
        monkeypatch.setattr(download_service_module.settings, "cookies_from_browser", "")
        captured = {}

        class FakeYDL:
            def __init__(self, opts):
                captured.update(opts)

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def extract_info(self, url, download=False):
                return {"title": "T", "formats": []}

        monkeypatch.setattr(download_service_module.yt_dlp, "YoutubeDL", FakeYDL)

        download_service_module.extract_video_preview("https://www.youtube.com/watch?v=test123")

        assert "cookiefile" not in captured

    def test_preview_uses_real_cookies_file(self, monkeypatch, tmp_path):
        cookies = tmp_path / "cookies.txt"
        cookies.write_text("# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t0\tSID\tabc\n")
        monkeypatch.setattr(download_service_module.settings, "cookies_file", str(cookies))
        captured = {}

        class FakeYDL:
            def __init__(self, opts):
                captured.update(opts)

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def extract_info(self, url, download=False):
                return {"title": "T", "formats": []}

        monkeypatch.setattr(download_service_module.yt_dlp, "YoutubeDL", FakeYDL)

        download_service_module.extract_video_preview("https://www.youtube.com/watch?v=test123")

        assert captured["cookiefile"] == str(cookies)


class TestSingleExtractCall:
    def test_run_download_extracts_and_downloads_in_one_call(self, monkeypatch, tmp_path):
        monkeypatch.setattr(download_service_module.settings, "temp_dir", tmp_path)
        calls = []

        class FakeYDL:
            def __init__(self, opts):
                self.opts = opts

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def extract_info(self, url, download=False):
                calls.append(("extract_info", download))
                job_dir = tmp_path / "job"
                job_dir.mkdir(exist_ok=True)
                out = job_dir / "Clip.mp4"
                out.write_bytes(b"video")
                (job_dir / "Clip.mp3").write_bytes(b"newer but not the output")
                return {
                    "title": "Clip",
                    "duration": 12,
                    "requested_downloads": [{"filepath": str(out)}],
                }

            def download(self, urls):
                calls.append(("download", urls))

        monkeypatch.setattr(download_service_module.yt_dlp, "YoutubeDL", FakeYDL)

        result = DownloadService()._run_download(
            "https://www.youtube.com/watch?v=test123", "job", VideoQuality.Q_720P, DownloadProgress("job")
        )

        assert calls == [("extract_info", True)]
        assert result["success"] is True
        assert result["filename"] == "Clip.mp4"
        assert result["title"] == "Clip"

    def test_progress_hook_takes_title_from_info_dict(self):
        progress = DownloadProgress("job")
        progress.progress_hook({
            "status": "downloading",
            "downloaded_bytes": 1,
            "total_bytes": 10,
            "info_dict": {"title": "From hook"},
        })
        assert progress.title == "From hook"


class TestFormatting:
    def test_format_speed(self):
        assert download_service_module.format_speed(None) is None
        assert download_service_module.format_speed(512) == "512 B/s"
        assert download_service_module.format_speed(2048) == "2.0 KiB/s"
        assert download_service_module.format_speed(3 * 1024 * 1024) == "3.0 MiB/s"

    def test_format_eta(self):
        assert download_service_module.format_eta(None) is None
        assert download_service_module.format_eta(65) == "01:05"
        assert download_service_module.format_eta(3725) == "01:02:05"


class TestThreadsStreaming:
    def _patch(self, monkeypatch, tmp_path, chunks, content_length):
        class FakeResponse:
            headers = {"content-length": str(content_length)}

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def raise_for_status(self):
                return None

            def iter_bytes(self, chunk_size):
                yield from chunks

        monkeypatch.setattr(download_service_module.settings, "temp_dir", tmp_path)
        monkeypatch.setattr(
            download_service_module,
            "extract_threads_info",
            lambda url: {"title": "Thread video", "video_url": "https://cdn.example.com/v.mp4"},
        )
        monkeypatch.setattr(httpx, "stream", lambda *args, **kwargs: FakeResponse())

    def test_threads_download_reports_speed(self, monkeypatch, tmp_path):
        self._patch(monkeypatch, tmp_path, [b"a" * 50, b"b" * 50], 100)
        speeds = []
        progress = DownloadProgress("job", callback=lambda u: speeds.append(u.speed))

        result = DownloadService()._run_download(
            "https://www.threads.net/@user/post/123", "job", VideoQuality.Q_720P, progress
        )

        assert result["success"] is True
        assert any(s and s.endswith("/s") for s in speeds)

    def test_threads_download_enforces_max_file_size(self, monkeypatch, tmp_path):
        monkeypatch.setattr(download_service_module.settings, "max_file_size_mb", 1)
        self._patch(monkeypatch, tmp_path, [b"x"], 2 * 1024 * 1024)

        result = DownloadService()._run_download(
            "https://www.threads.net/@user/post/123", "job", VideoQuality.Q_720P, DownloadProgress("job")
        )

        assert result["success"] is False
        assert "1 MB limit" in result["error"]
        assert not (tmp_path / "job").exists()

    def test_threads_download_enforces_size_without_content_length(self, monkeypatch, tmp_path):
        monkeypatch.setattr(download_service_module.settings, "max_file_size_mb", 1)
        chunk = b"x" * (512 * 1024)
        self._patch(monkeypatch, tmp_path, [chunk, chunk, chunk], 0)

        result = DownloadService()._run_download(
            "https://www.threads.net/@user/post/123", "job", VideoQuality.Q_720P, DownloadProgress("job")
        )

        assert result["success"] is False
        assert not (tmp_path / "job").exists()


class TestDownloadTimeout:
    async def test_timeout_stops_worker_and_fails_job(self, monkeypatch, tmp_path):
        import asyncio
        import threading

        monkeypatch.setattr(download_service_module.settings, "temp_dir", tmp_path)
        monkeypatch.setattr(download_service_module.settings, "download_timeout_seconds", 1)
        service = DownloadService()
        finished = []

        def stuck_download(url, job_id, quality, progress):
            (tmp_path / job_id).mkdir()
            try:
                for _ in range(1000):
                    progress.progress_hook({"status": "downloading", "downloaded_bytes": 1, "total_bytes": 10})
                    threading.Event().wait(0.01)
            except Exception as e:
                return {"success": False, "error": str(e)}
            return {"success": True, "title": "t", "filename": "never.mp4"}

        monkeypatch.setattr(service, "_run_download", stuck_download)

        async def on_finish(progress, result):
            finished.append((progress.status, result["error"]))

        job_id, task, _ = await service.start_download(
            "https://www.youtube.com/watch?v=test123",
            VideoQuality.Q_720P,
            on_finish=on_finish,
        )
        await asyncio.wait_for(task, timeout=8)

        assert finished == [(JobStatus.FAILED, "Download timed out after 1 seconds")]
        assert job_id not in service.active_jobs
        assert not (tmp_path / job_id).exists()
