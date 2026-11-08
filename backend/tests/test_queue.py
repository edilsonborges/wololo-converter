"""Bounded server queue and admission regression tests."""
import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import download_service as download_service_module, routes
from app.config import settings
from app.download_service import DownloadQueueFull, DownloadService
from app.models import DownloadJob, JobStatus, VideoQuality


VIDEO_URL = "https://www.youtube.com/watch?v=test123"


async def wait_until(predicate):
    async def poll():
        while not predicate():
            await asyncio.sleep(0.005)

    await asyncio.wait_for(poll(), timeout=5)


class ControlledDownloads:
    """Keep real executor threads blocked until the test releases them."""

    def __init__(self):
        self.service = DownloadService()
        self.started = []
        self.releases = {}
        self.tasks = []
        self.running = 0
        self.peak_running = 0
        self.lock = threading.Lock()

    def run(self, url, job_id, quality, progress):
        release = self.releases.setdefault(job_id, threading.Event())
        with self.lock:
            self.started.append(job_id)
            self.running += 1
            self.peak_running = max(self.running, self.peak_running)
        try:
            if not release.wait(timeout=10):
                raise RuntimeError("Test worker was not released")
            return {"success": True, "filename": "video.mp4", "title": "Video"}
        finally:
            with self.lock:
                self.running -= 1

    async def start(self, job_id, **kwargs):
        self.releases[job_id] = threading.Event()
        _, task, _ = await self.service.start_download(
            VIDEO_URL, VideoQuality.Q_720P, job_id=job_id, **kwargs,
        )
        self.tasks.append(task)
        return task


@pytest.fixture
async def downloads(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "max_concurrent_downloads", 3)
    monkeypatch.setattr(settings, "max_queued_downloads", 20)
    monkeypatch.setattr(settings, "temp_dir", tmp_path)
    controlled = ControlledDownloads()
    monkeypatch.setattr(controlled.service, "_run_download", controlled.run)
    yield controlled
    for job_id in list(controlled.service.active_jobs):
        controlled.service.cancel_job(job_id)
    for release in controlled.releases.values():
        release.set()
    await asyncio.wait_for(asyncio.gather(*controlled.tasks), timeout=5)


async def test_three_running_and_twenty_waiting_rejects_twenty_fourth(downloads):
    for index in range(23):
        await downloads.start(f"job-{index}")
    await wait_until(lambda: len(downloads.started) == 3)

    with pytest.raises(DownloadQueueFull):
        await downloads.start("overflow")

    assert downloads.service.active_count == 3
    assert downloads.service.queued_count == 20
    assert downloads.peak_running == 3
    assert set(downloads.started) == {"job-0", "job-1", "job-2"}
    assert "overflow" not in downloads.service.active_jobs


async def test_waiting_jobs_start_in_fifo_order(downloads, monkeypatch):
    monkeypatch.setattr(settings, "max_concurrent_downloads", 1)
    tasks = [await downloads.start(f"job-{index}") for index in range(4)]
    for index, task in enumerate(tasks):
        await wait_until(lambda: len(downloads.started) == index + 1)
        assert downloads.started == [f"job-{number}" for number in range(index + 1)]
        downloads.releases[f"job-{index}"].set()
        await task
    assert downloads.peak_running == 1


async def test_timeout_starts_when_job_leaves_queue(downloads, monkeypatch):
    monkeypatch.setattr(settings, "max_concurrent_downloads", 1)
    monkeypatch.setattr(settings, "download_timeout_seconds", 0.1)
    first = await downloads.start("first")
    waiting = await downloads.start("waiting")
    await wait_until(lambda: downloads.started == ["first"])
    await asyncio.sleep(0.2)

    progress = downloads.service.get_job_progress("waiting")
    assert progress.status == JobStatus.QUEUED
    assert progress.started_at is None
    assert progress.timed_out is False
    assert downloads.service.get_job_progress("first").timed_out is True

    downloads.releases["first"].set()
    await first
    await wait_until(lambda: downloads.started == ["first", "waiting"])
    downloads.releases["waiting"].set()
    assert (await waiting)["success"] is True


async def test_executor_wait_does_not_consume_download_timeout(downloads, monkeypatch):
    monkeypatch.setattr(settings, "download_timeout_seconds", 0.1)
    pool = ThreadPoolExecutor(max_workers=1)
    monkeypatch.setattr(download_service_module, "executor", pool)
    auxiliary_started = threading.Event()
    auxiliary_release = threading.Event()

    def auxiliary_work():
        auxiliary_started.set()
        auxiliary_release.wait(timeout=5)

    auxiliary = asyncio.get_running_loop().run_in_executor(pool, auxiliary_work)
    try:
        await wait_until(auxiliary_started.is_set)
        task = await downloads.start("waiting-for-executor")
        await asyncio.sleep(0.2)

        progress = downloads.service.get_job_progress("waiting-for-executor")
        assert progress.status == JobStatus.QUEUED
        assert progress.started_at is None
        assert progress.timed_out is False
        assert downloads.started == []

        auxiliary_release.set()
        await auxiliary
        await wait_until(lambda: downloads.started == ["waiting-for-executor"])
        downloads.releases["waiting-for-executor"].set()
        assert (await task)["success"] is True
    finally:
        auxiliary_release.set()
        for release in downloads.releases.values():
            release.set()
        await auxiliary
        await asyncio.wait_for(asyncio.gather(*downloads.tasks), timeout=5)
        pool.shutdown(wait=True)


async def test_cancel_waiting_job_frees_capacity_without_starting_worker(downloads, monkeypatch):
    monkeypatch.setattr(settings, "max_concurrent_downloads", 1)
    monkeypatch.setattr(settings, "max_queued_downloads", 1)
    terminal_states = []

    async def persist_result(progress, result):
        terminal_states.append((progress.job_id, progress.status, result["cancelled"]))

    await downloads.start("running")
    cancelled = await downloads.start("cancelled", on_finish=persist_result)
    await wait_until(lambda: downloads.started == ["running"])
    assert downloads.service.cancel_job("cancelled") is True
    assert downloads.service.queued_count == 0

    await downloads.start("replacement")
    assert (await cancelled)["cancelled"] is True
    assert terminal_states == [("cancelled", JobStatus.CANCELLED, True)]
    assert downloads.started == ["running"]
    assert downloads.service.queued_count == 1
    assert downloads.service.completed_jobs["cancelled"].started_at is None


async def test_cancel_running_job_keeps_slot_until_thread_exits(downloads, monkeypatch):
    monkeypatch.setattr(settings, "max_concurrent_downloads", 1)
    running = await downloads.start("running")
    await downloads.start("waiting")
    await wait_until(lambda: downloads.started == ["running"])
    assert downloads.service.cancel_job("running") is True
    await asyncio.sleep(0.02)

    assert downloads.service.active_count == 1
    assert downloads.service.queued_count == 1
    assert downloads.started == ["running"]
    downloads.releases["running"].set()
    assert (await running)["cancelled"] is True
    await wait_until(lambda: downloads.started == ["running", "waiting"])
    assert downloads.peak_running == 1


async def test_cancel_before_task_starts_replays_terminal_state(downloads):
    task = await downloads.start("cancelled-before-start")
    assert downloads.service.cancel_job("cancelled-before-start") is True
    assert (await task)["cancelled"] is True

    updates = []
    downloads.service.register_callback("cancelled-before-start", updates.append)
    assert downloads.started == []
    assert len(updates) == 1
    assert updates[0].status == JobStatus.CANCELLED
    assert downloads.service.active_count == 0


async def test_failed_enqueue_releases_reserved_capacity(downloads, monkeypatch):
    monkeypatch.setattr(settings, "max_concurrent_downloads", 1)
    monkeypatch.setattr(settings, "max_queued_downloads", 0)

    async def fail_to_persist():
        raise RuntimeError("Database unavailable")

    with pytest.raises(RuntimeError, match="Database unavailable"):
        await downloads.start("failed", on_enqueue=fail_to_persist)

    assert downloads.service.active_jobs == {}
    assert downloads.service.active_count == 0
    assert downloads.service.queued_count == 0
    await downloads.start("accepted")
    await wait_until(lambda: downloads.started == ["accepted"])


async def test_concurrent_submissions_reserve_capacity_before_persistence(downloads, monkeypatch):
    monkeypatch.setattr(settings, "max_concurrent_downloads", 1)
    monkeypatch.setattr(settings, "max_queued_downloads", 2)
    persist_gate = asyncio.Event()
    submissions = [
        asyncio.create_task(downloads.start(f"job-{index}", on_enqueue=persist_gate.wait))
        for index in range(10)
    ]
    try:
        await wait_until(lambda: sum(task.done() for task in submissions) == 7)
        assert len(downloads.service.active_jobs) == 3
        assert downloads.started == []
    finally:
        persist_gate.set()
        results = await asyncio.gather(*submissions, return_exceptions=True)

    assert sum(isinstance(result, DownloadQueueFull) for result in results) == 7
    assert sum(isinstance(result, asyncio.Task) for result in results) == 3
    assert downloads.service.active_count == 1
    assert downloads.service.queued_count == 2


@pytest.fixture
async def queued_api(downloads, monkeypatch, db_session):
    monkeypatch.setattr(routes, "download_service", downloads.service)
    tasks = {}
    monkeypatch.setattr(routes, "download_tasks", tasks)
    persistence_lock = asyncio.Lock()

    @asynccontextmanager
    async def test_db_context():
        async with persistence_lock:
            async with AsyncSession(bind=db_session.bind, expire_on_commit=False) as session:
                yield session
                await session.commit()

    monkeypatch.setattr(routes, "get_db_context", test_db_context)
    routes.limiter.reset()
    yield downloads
    downloads.tasks.extend(tasks.values())
    routes.limiter.reset()


async def test_fourth_request_queues_and_cancel_is_persisted(client, queued_api, db_session):
    responses = [
        await client.post("/api/download", json={"url": VIDEO_URL, "quality": "720p"})
        for _ in range(4)
    ]
    assert [response.status_code for response in responses] == [200, 200, 200, 200]
    await wait_until(lambda: len(queued_api.started) == 3)
    queued_id = responses[3].json()["job_id"]
    assert responses[3].json()["status"] == "queued"
    polling = await client.get(f"/api/jobs/{queued_id}")
    assert polling.json()["status"] == "queued"
    assert polling.json()["started_at"] is None

    queued_task = routes.download_tasks[queued_id]
    cancelled = await client.delete(f"/api/jobs/{queued_id}")
    assert cancelled.status_code == 200
    await queued_task
    db_session.expire_all()
    job = await db_session.get(DownloadJob, queued_id)
    assert job.status == JobStatus.CANCELLED.value
    assert job.started_at is None
    assert job.completed_at is not None
    assert queued_id not in queued_api.started


async def test_full_queue_returns_429_without_persisting_rejected_job(
    client, queued_api, db_session, monkeypatch,
):
    monkeypatch.setattr(settings, "max_concurrent_downloads", 1)
    monkeypatch.setattr(settings, "max_queued_downloads", 1)
    responses = [
        await client.post("/api/download", json={"url": VIDEO_URL})
        for _ in range(3)
    ]
    assert [response.status_code for response in responses] == [200, 200, 429]
    assert responses[2].json()["detail"] == "Download queue is full. Please try again later."
    assert await db_session.scalar(select(func.count()).select_from(DownloadJob)) == 2
    assert len(queued_api.service.active_jobs) == 2


async def test_polling_overlays_progress_without_dirtying_database_job(client, queued_api, db_session):
    response = await client.post("/api/download", json={"url": VIDEO_URL})
    assert response.status_code == 200
    job_id = response.json()["job_id"]
    await wait_until(lambda: queued_api.started == [job_id])
    job = await db_session.get(DownloadJob, job_id)

    polling = await client.get(f"/api/jobs/{job_id}")
    assert polling.status_code == 200
    assert polling.json()["status"] == "validating"
    assert polling.json()["started_at"] is not None
    assert not db_session.dirty
    await db_session.commit()
    await db_session.refresh(job)
    assert job.status == JobStatus.QUEUED.value
    assert job.started_at is None

    task = routes.download_tasks[job_id]
    queued_api.releases[job_id].set()
    await task
    await db_session.commit()
    await db_session.refresh(job)
    assert job.status == JobStatus.COMPLETED.value
