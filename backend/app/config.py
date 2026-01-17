"""Application configuration"""
import os
from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings"""

    # Server settings
    app_name: str = "Wololo Converter"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8000

    # File storage
    temp_dir: Path = Path("/tmp/wololo")
    max_file_age_hours: int = 1
    cleanup_interval_minutes: int = 15

    # Download settings
    max_concurrent_downloads: int = 3
    download_timeout_seconds: int = 3600  # 1 hour
    max_file_size_mb: int = 10000  # 10GB for 4K videos

    # Rate limiting
    rate_limit_downloads: str = "10/minute"

    # Allowed domains for downloads
    allowed_domains: list[str] = [
        "youtube.com",
        "youtu.be",
        "www.youtube.com",
        "instagram.com",
        "www.instagram.com",
        "facebook.com",
        "www.facebook.com",
        "fb.watch",
        "twitter.com",
        "www.twitter.com",
        "x.com",
        "www.x.com",
    ]

    # Database
    database_url: str = "sqlite+aiosqlite:///./wololo.db"

    # CORS origins (for development)
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ]

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()

# Ensure temp directory exists
settings.temp_dir.mkdir(parents=True, exist_ok=True)
