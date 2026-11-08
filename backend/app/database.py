"""Database setup and session management"""
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy import update

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


async def init_db() -> None:
    """Initialize tables and finish jobs interrupted by a server restart."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
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
