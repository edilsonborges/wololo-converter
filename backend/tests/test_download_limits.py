"""Download limits (#11): size estimates, shared and cached downloads,
per-visitor limit and storage cleanup."""
import os
import threading
import time
from contextlib import asynccontextmanager

import pytest
from sqlalchemy import select

from app import routes, sizing
from app.config import settings
from app.download_service import DownloadProgress, DownloadService, download_service
from app.models import DownloadJob, JobStatus, VideoQuality
from app.utils import enforce_storage, media_key

GB = 1_000_000_000


def fmt(fid, height=None, vcodec="none", acodec="none", size=None, tbr=None):
    return {"format_id": fid, "height": height, "width": height and height * 16 // 9,
            "vcodec": vcodec, "acodec": acodec, "filesize": size, "tbr": tbr}


# Shaped like the 10-hour video from the issue (sizes from YouTube)
TEN_HOURS = {
    "duration": 36000,
    "formats": [
        fmt("140", acodec="mp4a.40.2", size=int(0.58 * GB)),
        fmt("251", acodec="opus", size=int(0.6 * GB)),
        fmt("134", 360, "avc1.4d401e", size=int(0.72 * GB)),
        fmt("135", 480, "avc1.4d401f", size=int(1.11 * GB)),
        fmt("136", 720, "avc1.4d401f", size=int(1.72 * GB)),
        fmt("137", 1080, "avc1.640028", size=int(6.33 * GB)),
        fmt("313", 2160, "vp9", size=int(31.5 * GB)),
        fmt("sb0", vcodec="none", acodec="none"),  # storyboard
    ],
}


class TestSizing:
    def test_quality_sizes_follow_the_format_choice(self):
        sizes = sizing.estimate_quality_sizes(TEN_HOURS)
        assert sizes["1080p"] == int(6.33 * GB) + int(0.58 * GB)
        assert sizes["720p"] == int(1.72 * GB) + int(0.58 * GB)
        assert sizes["mp3"] == 36000 * 40_000  # 320 kbps

    def test_bitrate_fills_in_a_missing_size(self):
        info = {"duration": 100, "formats": [fmt("18", 360, "avc1", "mp4a", tbr=800)]}
        assert sizing.estimate_quality_sizes(info)["360p"] == 800 * 1000 // 8 * 100

    def test_too_large_is_refused_with_a_quality_that_fits(self, monkeypatch):
        monkeypatch.setattr(settings, "max_file_size_mb", 4000)
        info = {**TEN_HOURS, "requested_formats": [TEN_HOURS["formats"][5], TEN_HOURS["formats"][0]]}
        with pytest.raises(sizing.DownloadRejected) as refused:
            sizing.check_download(info, VideoQuality.Q_1080P)
        assert str(refused.value) == (
            "This video is too large: ~6.9 GB at 1080p (limit 4 GB). Try 720p (~2.3 GB)."
        )
        assert refused.value.suggested_quality == "720p"

    def test_within_the_limit_returns_the_estimate(self):
        info = {**TEN_HOURS, "requested_formats": [TEN_HOURS["formats"][4], TEN_HOURS["formats"][0]]}
        assert sizing.check_download(info, VideoQuality.Q_720P) == int(2.3 * GB)

    def test_unknown_size_falls_back_to_the_duration_limit(self, monkeypatch):
        monkeypatch.setattr(settings, "max_duration_minutes", 180)
        long_unknown = {"duration": 4 * 3600, "format_id": "x"}
        with pytest.raises(sizing.DownloadRejected, match="too long"):
            sizing.check_download(long_unknown, VideoQuality.Q_720P)
        assert sizing.check_download({"duration": 600, "format_id": "x"}, VideoQuality.Q_720P) is None

    def test_guard_runs_before_the_download(self, monkeypatch, tmp_path):
        """The before_dl hook refuses the job before any byte is fetched."""
        from app.download_service import _CaptureRequestedFormats

        monkeypatch.setattr(settings, "temp_dir", tmp_path)
        progress = DownloadProgress("guard")
        progress.quality = VideoQuality.Q_1080P
        hook = _CaptureRequestedFormats(progress)
        info = {**TEN_HOURS, "requested_formats": [TEN_HOURS["formats"][5], TEN_HOURS["formats"][0]]}
        with pytest.raises(sizing.DownloadRejected):
            hook.run(info)
        assert progress.requested_formats


class TestAudioOnlyResult:
    def test_video_job_that_only_produced_audio_fails(self, monkeypatch, tmp_path):
        """yt-dlp drops a stream over max_filesize silently; the m4a left over
        must not be reported as the finished video."""
        import yt_dlp
        from app import download_service as module

        monkeypatch.setattr(settings, "temp_dir", tmp_path)
        job_dir = tmp_path / "audio-only"
        job_dir.mkdir()
        (job_dir / "Long video.f140.m4a").write_bytes(b"aac")

        class FakeYDL:
            def __init__(self, opts):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def add_post_processor(self, *args, **kwargs):
                pass

            def extract_info(self, url, download):
                return {"title": "Long video", "duration": 36000}

        monkeypatch.setattr(yt_dlp, "YoutubeDL", FakeYDL)
        progress = DownloadProgress("audio-only")
        result = module.DownloadService()._run_download(
            "https://youtu.be/AKeUssuu3Is", "audio-only", VideoQuality.Q_1080P, progress,
        )
        assert result["success"] is False
        assert "larger than the" in result["error"]


class TestMediaKey:
    @pytest.mark.parametrize("url", [
        "https://youtu.be/XIhEPwTMjWk",
        "https://www.youtube.com/watch?v=XIhEPwTMjWk&t=30",
        "https://m.youtube.com/watch?feature=share&v=XIhEPwTMjWk",
        "https://youtube.com/shorts/XIhEPwTMjWk?si=abc",
        "https://www.youtube.com/live/XIhEPwTMjWk",
    ])
    def test_youtube_links_share_a_key(self, url):
        assert media_key(url) == "youtube:XIhEPwTMjWk"

    def test_other_platforms(self):
        assert media_key("https://www.instagram.com/reels/Abc_1/?igsh=x") == media_key("https://instagram.com/p/Abc_1")
        assert media_key("https://x.com/a/status/123?s=20") == media_key("https://twitter.com/b/status/123")
        assert media_key("https://vt.tiktok.com/ZSabc/") == "tiktok:vt.tiktok.com/ZSabc"


def make_job_dir(root, name, size, age_seconds, partial=False):
    job_dir = root / name
    job_dir.mkdir()
    (job_dir / ("video.mp4.part" if partial else "video.mp4")).write_bytes(b"x" * size)
    past = time.time() - age_seconds
    os.utime(job_dir, (past, past))
    return job_dir


class TestStorage:
    @pytest.fixture
    def storage(self, monkeypatch, tmp_path):
        monkeypatch.setattr(settings, "temp_dir", tmp_path)
        monkeypatch.setattr(settings, "max_file_age_hours", 1)
        monkeypatch.setattr(settings, "cache_max_age_hours", 72)
        monkeypatch.setattr(settings, "min_free_disk_mb", 0)
        return tmp_path

    def test_partial_leftovers_go_after_an_hour_finished_files_stay(self, storage):
        old_partial = make_job_dir(storage, "partial", 10, 2 * 3600, partial=True)
        recent_partial = make_job_dir(storage, "running-elsewhere", 10, 60, partial=True)
        finished = make_job_dir(storage, "finished", 10, 2 * 3600)
        assert enforce_storage(set()) == 1
        assert not old_partial.exists()
        assert recent_partial.exists() and finished.exists()

    def test_cache_drops_least_recently_used_over_the_limit(self, storage, monkeypatch):
        monkeypatch.setattr(settings, "cache_max_gb", 250 / 1024 ** 3)  # 250 bytes
        oldest = make_job_dir(storage, "oldest", 100, 300)
        middle = make_job_dir(storage, "middle", 100, 200)
        newest = make_job_dir(storage, "newest", 100, 100)
        enforce_storage(set())
        assert not oldest.exists()
        assert middle.exists() and newest.exists()

    def test_hard_linked_cache_hits_count_once(self, storage, monkeypatch):
        from app.utils import link_job_files

        monkeypatch.setattr(settings, "cache_max_gb", 150 / 1024 ** 3)
        original = make_job_dir(storage, "original", 100, 300)
        link_job_files([original / "video.mp4"], storage / "reuse")
        enforce_storage(set())
        assert original.exists() and (storage / "reuse" / "video.mp4").exists()

    def test_expired_cache_and_active_jobs(self, storage):
        expired = make_job_dir(storage, "expired", 10, 73 * 3600)
        active = make_job_dir(storage, "active", 10, 73 * 3600, partial=True)
        enforce_storage({"active"})
        assert not expired.exists()
        assert active.exists()


@pytest.fixture
def api(monkeypatch, tmp_path, db_session):
    """Real routes and queue with a fake yt-dlp run that waits for release."""
    monkeypatch.setattr(settings, "temp_dir", tmp_path)
    service = DownloadService()
    monkeypatch.setattr(routes, "download_service", service)
    monkeypatch.setattr(routes, "download_tasks", {})
    release = threading.Event()
    runs = []

    def run(url, job_id, quality, progress):
        runs.append(job_id)
        release.wait(timeout=5)
        job_dir = tmp_path / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        (job_dir / "Clip.mp4").write_bytes(b"mp4-bytes")
        return {"success": True, "filename": "Clip.mp4", "title": "Clip"}

    monkeypatch.setattr(service, "_run_download", run)

    @asynccontextmanager
    async def same_session():
        yield db_session
        await db_session.commit()

    async def no_start(progress):
        return None

    monkeypatch.setattr(routes, "get_db_context", same_session)
    monkeypatch.setattr(routes, "persist_job_started", no_start)
    routes.limiter.reset()
    yield service, release, runs
    release.set()
    routes.limiter.reset()


URL = "https://www.youtube.com/watch?v=XIhEPwTMjWk"


class TestSharedAndCached:
    async def test_repeated_requests_share_one_download(self, client, api, db_session):
        service, release, runs = api
        first = await client.post("/api/download", json={"url": URL, "quality": "1080p"})
        again = await client.post("/api/download", json={"url": "https://youtu.be/XIhEPwTMjWk?t=3", "quality": "1080p"})
        other_quality = await client.post("/api/download", json={"url": URL, "quality": "mp3"})

        assert again.json()["job_id"] == first.json()["job_id"]
        assert "joined" in again.json()["message"]
        assert other_quality.json()["job_id"] != first.json()["job_id"]
        job = await db_session.get(DownloadJob, first.json()["job_id"])
        await db_session.refresh(job)
        assert job.request_count == 2

        # One of the two requests gives up: the download goes on for the other
        await client.delete(f"/api/jobs/{first.json()['job_id']}")
        assert not service.active_jobs[first.json()["job_id"]].cancelled
        release.set()
        await routes.download_tasks[first.json()["job_id"]]

    async def test_simultaneous_requests_share_one_download(self, api, monkeypatch, tmp_path):
        """Five requests at the same time, each with its own database session
        (as in production), start a single download."""
        import asyncio

        from httpx import ASGITransport, AsyncClient
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

        from app import database
        from app.database import get_session
        from app.main import app
        from app.models import Base

        url = f"sqlite+aiosqlite:///{tmp_path}/jobs.db"
        engine = create_async_engine(url, **database._engine_options(url))
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async def own_session():
            async with sessions() as session:
                yield session
                await session.commit()

        @asynccontextmanager
        async def own_context():
            async with sessions() as session:
                yield session
                await session.commit()

        monkeypatch.setattr(routes, "get_db_context", own_context)
        app.dependency_overrides[get_session] = own_session
        service, release, runs = api
        links = [URL, "https://youtu.be/XIhEPwTMjWk", "https://m.youtube.com/watch?v=XIhEPwTMjWk",
                 "https://youtube.com/shorts/XIhEPwTMjWk", "https://youtu.be/XIhEPwTMjWk?si=x"]
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                responses = await asyncio.gather(*[
                    client.post("/api/download", json={"url": link, "quality": "720p"}) for link in links
                ])
                assert [r.status_code for r in responses] == [200] * 5
                job_ids = {r.json()["job_id"] for r in responses}
                assert len(job_ids) == 1
                release.set()
                await routes.download_tasks[job_ids.pop()]
            assert len(runs) == 1
            async with sessions() as session:
                rows = (await session.execute(select(DownloadJob))).scalars().all()
            # Every request is accounted for on the one stored job
            assert [(r.status, r.request_count) for r in rows] == [("completed", 5)]
        finally:
            app.dependency_overrides.pop(get_session, None)
            await engine.dispose()

    async def test_finished_file_is_served_from_cache(self, client, api, db_session):
        service, release, runs = api
        release.set()
        first = await client.post("/api/download", json={"url": URL, "quality": "720p"})
        await routes.download_tasks[first.json()["job_id"]]
        assert len(runs) == 1

        cached = await client.post("/api/download", json={"url": "https://youtu.be/XIhEPwTMjWk", "quality": "720p"})
        assert cached.json()["status"] == "completed"
        new_id = cached.json()["job_id"]
        assert new_id != first.json()["job_id"]
        assert len(runs) == 1  # no second download

        job = await db_session.get(DownloadJob, new_id)
        assert job.reused_from == first.json()["job_id"]
        file = await client.get(f"/api/jobs/{new_id}/download")
        assert file.content == b"mp4-bytes"
        # Linked, not copied
        a = settings.temp_dir / first.json()["job_id"] / "Clip.mp4"
        b = settings.temp_dir / new_id / "Clip.mp4"
        assert os.stat(a).st_ino == os.stat(b).st_ino

        # The progress stream of a cached job ends right away
        async with client.stream("GET", f"/api/jobs/{new_id}/progress") as stream:
            body = ""
            async for chunk in stream.aiter_text():
                body += chunk
                if "event: complete" in body:
                    break
        assert '"download_ready":true' in body

        # The link form answers with the file immediately
        link = await client.get("/api/download", params={"url": URL, "quality": "720p"})
        assert link.status_code == 200 and link.content == b"mp4-bytes"
        assert len(runs) == 1

    async def test_visitor_limit(self, client, api, monkeypatch):
        monkeypatch.setattr(settings, "max_active_downloads_per_client", 2)
        codes = []
        for n in range(3):
            response = await client.post("/api/download", json={"url": f"https://youtu.be/vid{n}xxxxx", "quality": "720p"})
            codes.append(response.status_code)
        assert codes == [200, 200, 429]
        assert "2 downloads in progress" in response.json()["detail"]

    async def test_low_disk_refuses_new_downloads(self, client, api, monkeypatch):
        monkeypatch.setattr(routes, "free_disk_bytes", lambda: 0)
        response = await client.post("/api/download", json={"url": URL, "quality": "720p"})
        assert response.status_code == 503

    async def test_too_large_link_returns_422_with_suggestion(self, client, api):
        service, release, runs = api

        def refuse(url, job_id, quality, progress):
            progress.suggested_quality = "720p"
            return {"success": False, "error": "This video is too large", "rejected": True,
                    "suggested_quality": "720p"}

        service._run_download = refuse
        response = await client.get("/api/download", params={"url": URL, "quality": "1080p"})
        assert response.status_code == 422
        assert response.json()["suggested_quality"] == "720p"
