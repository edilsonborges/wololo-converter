"""Database setup and session management"""
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy import text, update

from .config import settings
from .models import Base, DownloadJob, JobStatus, utcnow

def _engine_options(url: str) -> dict:
    """SQLite file: one connection per session, waiting on locks instead of
    failing. Sharing a single connection (StaticPool) let one session's
    rollback discard another's uncommitted rows when requests overlapped.
    Only an in-memory database needs the shared connection."""
    if "sqlite" not in url:
        return {}
    if ":memory:" in url or "mode=memory" in url:
        return {"connect_args": {"check_same_thread": False}, "poolclass": StaticPool}
    return {"connect_args": {"check_same_thread": False, "timeout": 30}}


# Create async engine
engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    **_engine_options(settings.database_url),
)

# Session factory
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# Columns added after the first release. create_all doesn't alter existing
# tables, so they are added here (SQLite only supports ADD COLUMN).
ADDED_JOB_COLUMNS = {
    "client_ip": "VARCHAR(64)",
    "client_name": "VARCHAR(100)",
    "source": "VARCHAR(20)",
    "user_agent": "VARCHAR(500)",
    "media_key": "VARCHAR(300)",
    "estimated_size": "INTEGER",
    "request_count": "INTEGER",
    "reused_from": "VARCHAR(36)",
}


async def add_missing_job_columns(conn) -> None:
    rows = await conn.execute(text("PRAGMA table_info(download_jobs)"))
    existing = {row[1] for row in rows}
    for name, column_type in ADDED_JOB_COLUMNS.items():
        if name not in existing:
            await conn.execute(text(f"ALTER TABLE download_jobs ADD COLUMN {name} {column_type}"))
    await conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_download_jobs_media_key ON download_jobs (media_key, quality)"
    ))


async def init_db() -> None:
    """Initialize tables and finish jobs interrupted by a server restart."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        if "sqlite" in settings.database_url:
            await add_missing_job_columns(conn)
        await conn.execute(
            update(DownloadJob)
            .where(DownloadJob.status.in_([
                JobStatus.QUEUED.value, JobStatus.VALIDATING.value,
                JobStatus.DOWNLOADING.value, JobStatus.CONVERTING.value,
                JobStatus.FINALIZING.value,
            ]))
            .values(
                status=JobStatus.FAILED.value,
                error_message="Server restarted before the download completed. Please try again.",
                current_stage="Interrupted",
                speed=None,
                eta=None,
                completed_at=utcnow(),
            )
        )


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency to get database session"""
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def get_db_context() -> AsyncGenerator[AsyncSession, None]:
    """Context manager to get database session"""
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
