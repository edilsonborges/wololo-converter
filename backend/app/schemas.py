"""Pydantic schemas for API request/response validation"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, HttpUrl, field_validator
from urllib.parse import urlparse

from .models import JobStatus, OutputFormat, VideoQuality


class PreviewRequest(BaseModel):
    """Request schema for video preview/metadata"""
    url: str = Field(..., min_length=10, max_length=2048, description="URL to preview")

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        """Validate URL format"""
        v = v.strip()
        if not v.startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")
        try:
            parsed = urlparse(v)
            if not parsed.netloc:
                raise ValueError("Invalid URL format")
        except Exception:
            raise ValueError("Invalid URL format")
        return v


class PreviewResponse(BaseModel):
    """Response schema for video preview/metadata"""
    title: str
    thumbnail_url: Optional[str] = None
    duration: Optional[int] = None
    available_qualities: list[int] = Field(default_factory=list)


class DownloadRequest(BaseModel):
    """Request schema for starting a download"""
    url: str = Field(..., min_length=10, max_length=2048, description="URL to download")
    quality: VideoQuality = Field(
        default=VideoQuality.Q_480P,
        description="Desired video quality or mp3"
    )
    output_format: Optional[OutputFormat] = Field(
        default=None,
        description="Deprecated: use 'quality' instead",
        deprecated=True,
    )

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        """Validate URL format"""
        v = v.strip()
        if not v.startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")
        try:
            parsed = urlparse(v)
            if not parsed.netloc:
                raise ValueError("Invalid URL format")
        except Exception:
            raise ValueError("Invalid URL format")
        return v


class URLValidationResponse(BaseModel):
    """Response schema for URL validation"""
    valid: bool
    platform: Optional[str] = None
    error: Optional[str] = None


class JobResponse(BaseModel):
    """Response schema for a download job"""
    id: str
    url: str
    platform: str
    output_format: OutputFormat
    quality: Optional[VideoQuality] = None
    status: JobStatus
    progress: float = 0.0
    speed: Optional[str] = None
    eta: Optional[str] = None
    current_stage: Optional[str] = None
    title: Optional[str] = None
    filename: Optional[str] = None
    file_size: Optional[int] = None
    duration: Optional[int] = None
    thumbnail_url: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class JobProgressUpdate(BaseModel):
    """WebSocket/SSE message for progress updates"""
    job_id: str
    status: JobStatus
    progress: float
    speed: Optional[str] = None
    eta: Optional[str] = None
    current_stage: Optional[str] = None
    title: Optional[str] = None
    error_message: Optional[str] = None
    download_ready: bool = False


class DownloadStartResponse(BaseModel):
    """Response when a download job is started"""
    job_id: str
    message: str
    status: JobStatus


class ErrorResponse(BaseModel):
    """Standard error response"""
    error: str
    detail: Optional[str] = None
    code: Optional[str] = None


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    version: str
    yt_dlp_version: str
    active_downloads: int
    temp_dir_size_mb: float
