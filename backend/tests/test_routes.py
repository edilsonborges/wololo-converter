"""Tests for API routes"""
import pytest

from app.download_service import DownloadProgress, download_service
from app.models import JobStatus
from app.version import APP_VERSION


class TestHealthEndpoint:
    async def test_health_returns_ok(self, client):
        response = await client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "yt_dlp_version" in data
        assert "active_downloads" in data

    async def test_health_has_version(self, client):
        response = await client.get("/api/health")
        data = response.json()
        assert data["version"] == APP_VERSION


class TestValidateEndpoint:
    async def test_validate_threads_share_link(self, client):
        response = await client.post("/api/validate", json={
            "url": "https://www.threads.com/share/BAR2SGFo1r/",
        })
        assert response.status_code == 200
        assert response.json() == {"valid": True, "platform": "threads", "error": None}

    async def test_validate_valid_youtube(self, client):
        response = await client.post("/api/validate", json={
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert data["platform"] == "youtube"

    async def test_validate_valid_instagram(self, client):
        response = await client.post("/api/validate", json={
            "url": "https://www.instagram.com/reel/ABC123/"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert data["platform"] == "instagram"

    async def test_validate_invalid_domain(self, client):
        response = await client.post("/api/validate", json={
            "url": "https://evil.com/video"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert data["error"] is not None

    async def test_validate_invalid_url_format(self, client):
        response = await client.post("/api/validate", json={
            "url": "not-a-url"
        })
        assert response.status_code == 422


class TestDownloadEndpoint:
    async def test_download_invalid_url(self, client):
        response = await client.post("/api/download", json={
            "url": "https://evil.com/video",
            "output_format": "video"
        })
        assert response.status_code == 400

    async def test_download_missing_url(self, client):
        response = await client.post("/api/download", json={})
        assert response.status_code == 422

    async def test_download_all_formats_accepted(self, client):
        formats = ["video", "video_webm", "audio_mp3", "audio_m4a", "audio_wav", "audio_flac", "audio_ogg"]
        for fmt in formats:
            response = await client.post("/api/validate", json={
                "url": "https://www.youtube.com/watch?v=test123",
                "output_format": fmt,
            })
            assert response.status_code == 200, f"Format {fmt} should be accepted"


class TestJobEndpoints:
    async def test_get_nonexistent_job(self, client):
        response = await client.get("/api/jobs/nonexistent-id")
        assert response.status_code == 404

    async def test_download_nonexistent_job(self, client):
        response = await client.get("/api/jobs/nonexistent-id/download")
        assert response.status_code == 404

    async def test_list_jobs_empty(self, client):
        response = await client.get("/api/jobs")
        assert response.status_code == 200
        assert response.json() == []

    async def test_list_jobs_with_limit(self, client):
        response = await client.get("/api/jobs?limit=5&offset=0")
        assert response.status_code == 200

    async def test_progress_replays_completion_for_fast_mp3(self, client):
        job_id = "fast-mp3-job"
        progress = DownloadProgress(job_id)
        progress.status = JobStatus.COMPLETED
        progress.progress = 100
        progress.filename = "short-audio.mp3"
        download_service._remember_completed(progress)

        response = await client.get(f"/api/jobs/{job_id}/progress")

        assert response.status_code == 200
        assert "event: complete" in response.text
        assert '"download_ready":true' in response.text


class TestRootEndpoint:
    async def test_root_returns_info(self, client):
        response = await client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "version" in data


class TestJobPersistenceAndFiles:
    async def _add_job(self, db_session, job_id, quality="720p", filename=None):
        from datetime import datetime
        from app.models import DownloadJob

        db_session.add(DownloadJob(
            id=job_id,
            url="https://www.youtube.com/watch?v=test123",
            platform="youtube",
            output_format="video" if quality != "mp3" else "audio_mp3",
            quality=quality,
            status=JobStatus.QUEUED.value,
            filename=filename,
            created_at=datetime(2026, 1, 1),
        ))
        await db_session.commit()

    async def test_persist_job_result_stores_completed_state(self, db_session, monkeypatch):
        from contextlib import asynccontextmanager
        from app import routes
        from app.models import DownloadJob

        await self._add_job(db_session, "persist-job")

        @asynccontextmanager
        async def fake_ctx():
            yield db_session
            await db_session.commit()

        monkeypatch.setattr(routes, "get_db_context", fake_ctx)

        progress = DownloadProgress("persist-job")
        progress.status = JobStatus.COMPLETED
        progress.progress = 100
        progress.title = "My video"
        await routes.persist_job_result(progress, {
            "success": True,
            "title": "My video",
            "filename": "My video.mp4",
            "file_size": 1234,
            "duration": 42,
        })

        job = await db_session.get(DownloadJob, "persist-job")
        await db_session.refresh(job)
        assert job.status == JobStatus.COMPLETED.value
        assert job.filename == "My video.mp4"
        assert job.file_size == 1234
        assert job.completed_at is not None

    async def test_download_returns_video_after_audio_extraction(
        self, client, db_session, monkeypatch, tmp_path
    ):
        import os
        from app import routes

        monkeypatch.setattr(routes.settings, "temp_dir", tmp_path)
        await self._add_job(db_session, "video-job")
        job_dir = tmp_path / "video-job"
        job_dir.mkdir()
        video = job_dir / "clip.mp4"
        video.write_bytes(b"video")
        audio = job_dir / "clip.mp3"
        audio.write_bytes(b"audio")
        # The extracted MP3 is newer than the video
        os.utime(video, (1000, 1000))
        os.utime(audio, (2000, 2000))

        response = await client.get("/api/jobs/video-job/download")

        assert response.status_code == 200
        assert response.content == b"video"
        assert "clip.mp4" in response.headers["content-disposition"]

    async def test_download_prefers_recorded_filename(
        self, client, db_session, monkeypatch, tmp_path
    ):
        from app import routes

        monkeypatch.setattr(routes.settings, "temp_dir", tmp_path)
        await self._add_job(db_session, "mp3-job", quality="mp3", filename="song.mp3")
        job_dir = tmp_path / "mp3-job"
        job_dir.mkdir()
        (job_dir / "song.mp3").write_bytes(b"song")
        (job_dir / "song.mp3.part").write_bytes(b"partial")

        response = await client.get("/api/jobs/mp3-job/download")

        assert response.status_code == 200
        assert response.content == b"song"

    async def test_cancel_does_not_overwrite_completed_job(self, client, db_session):
        from app.models import DownloadJob

        await self._add_job(db_session, "done-job")
        job = await db_session.get(DownloadJob, "done-job")
        job.status = JobStatus.COMPLETED.value
        await db_session.commit()

        response = await client.delete("/api/jobs/done-job")

        assert response.status_code == 200
        await db_session.refresh(job)
        assert job.status == JobStatus.COMPLETED.value

    async def test_cancel_marks_queued_job_cancelled(self, client, db_session):
        from app.models import DownloadJob

        await self._add_job(db_session, "queued-job")

        response = await client.delete("/api/jobs/queued-job")

        assert response.status_code == 200
        job = await db_session.get(DownloadJob, "queued-job")
        await db_session.refresh(job)
        assert job.status == JobStatus.CANCELLED.value


class TestDurationsAndRestart:
    async def test_list_jobs_tolerates_fractional_durations(self, client, db_session):
        from datetime import datetime
        from app.models import DownloadJob

        db_session.add(DownloadJob(
            id="frac", url="https://x.com/u/status/1", platform="twitter", output_format="video",
            quality="720p", status="completed", duration=26.391, created_at=datetime(2026, 1, 1),
        ))
        await db_session.commit()

        response = await client.get("/api/jobs")

        assert response.status_code == 200
        assert response.json()[0]["duration"] == 26
