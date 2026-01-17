"""Database models for Wololo Converter"""
from datetime import datetime
from enum import Enum
from typing import Optional
from sqlalchemy import Column, String, DateTime, Integer, Float, Text
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class JobStatus(str, Enum):
    """Possible job statuses"""
    QUEUED = "queued"
    VALIDATING = "validating"
    DOWNLOADING = "downloading"
    CONVERTING = "converting"
    FINALIZING = "finalizing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class OutputFormat(str, Enum):
    """Output format options"""
    VIDEO = "video"
    AUDIO_MP3 = "audio_mp3"
    AUDIO_M4A = "audio_m4a"


class DownloadJob(Base):
    """Model to track download jobs"""
    __tablename__ = "download_jobs"

    id = Column(String(36), primary_key=True)
    url = Column(String(2048), nullable=False)
    platform = Column(String(50), nullable=False)
    output_format = Column(String(20), nullable=False)
    status = Column(String(20), nullable=False, default=JobStatus.QUEUED.value)

    # Progress tracking
    progress = Column(Float, default=0.0)  # 0-100
    speed = Column(String(50), nullable=True)  # e.g., "1.5 MiB/s"
    eta = Column(String(50), nullable=True)  # e.g., "00:05:30"
    current_stage = Column(String(100), nullable=True)

    # File info
    title = Column(String(500), nullable=True)
    filename = Column(String(500), nullable=True)
    file_size = Column(Integer, nullable=True)  # in bytes
    duration = Column(Integer, nullable=True)  # in seconds
    thumbnail_url = Column(String(2048), nullable=True)

    # Error handling
    error_message = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)


class JobStats(Base):
    """Model for simple analytics (optional)"""
    __tablename__ = "job_stats"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(String(10), unique=True)  # YYYY-MM-DD
    total_jobs = Column(Integer, default=0)
    successful_jobs = Column(Integer, default=0)
    failed_jobs = Column(Integer, default=0)
    total_bytes_downloaded = Column(Integer, default=0)
