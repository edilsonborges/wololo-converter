"""Database setup and session management"""
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy import text, update

from .config import settings
from .models import Base, DownloadJob, JobStatus, utcnow

# Create async engine
engine = create_async_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {},
    poolclass=StaticPool if "sqlite" in settings.database_url else None,
    echo=settings.debug,
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
}


async def add_missing_job_columns(conn) -> None:
    rows = await conn.execute(text("PRAGMA table_info(download_jobs)"))
    existing = {row[1] for row in rows}
    for name, column_type in ADDED_JOB_COLUMNS.items():
        if name not in existing:
            await conn.execute(text(f"ALTER TABLE download_jobs ADD COLUMN {name} {column_type}"))


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
