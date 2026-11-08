"""Recovery of interrupted downloads when the server starts again."""
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app import database
from app.models import DownloadJob, JobStatus, utcnow


async def test_restart_fails_interrupted_jobs_and_preserves_terminal_jobs(monkeypatch):
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
    )
    monkeypatch.setattr(database, "engine", engine)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    terminal_statuses = {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED}
    previous_timestamp = datetime(2026, 1, 1)

    try:
        await database.init_db()
        async with sessions() as session:
            for status in JobStatus:
                session.add(DownloadJob(
                    id=status.value,
                    url="https://www.youtube.com/watch?v=test123",
                    platform="youtube",
                    output_format="video",
                    quality="720p",
                    status=status.value,
                    progress=42,
                    current_stage="Previous stage",
                    speed="1 MiB/s",
                    eta="00:10",
                    error_message="Previous message",
                    created_at=previous_timestamp,
                    started_at=None if status == JobStatus.QUEUED else previous_timestamp,
                    completed_at=previous_timestamp if status in terminal_statuses else None,
                ))
            await session.commit()

        before_restart = utcnow()
        await database.init_db()
        after_restart = utcnow()

        async with sessions() as session:
            jobs = (await session.execute(select(DownloadJob))).scalars().all()

        assert len(jobs) == len(JobStatus)
        for job in jobs:
            original_status = JobStatus(job.id)
            assert job.created_at == previous_timestamp
            expected_start = None if original_status == JobStatus.QUEUED else previous_timestamp
            assert job.started_at == expected_start
            if original_status in terminal_statuses:
                assert job.status == original_status.value
                assert job.completed_at == previous_timestamp
                assert job.current_stage == "Previous stage"
                assert job.error_message == "Previous message"
                assert job.speed == "1 MiB/s"
                assert job.eta == "00:10"
            else:
                assert job.status == JobStatus.FAILED.value
                assert before_restart <= job.completed_at <= after_restart
                assert job.current_stage == "Interrupted"
                assert job.error_message == (
                    "Server restarted before the download completed. Please try again."
                )
                assert job.speed is None
                assert job.eta is None
    finally:
        await engine.dispose()
