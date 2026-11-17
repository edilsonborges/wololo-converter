"""Application configuration"""
from pathlib import Path
from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings"""

    # Server settings
    app_name: str = "Wololo Converter"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 47652
    min_app_version: str = Field(default="1.0.0", min_length=1)

    # File storage
    temp_dir: Path = Path("/tmp/wololo")
    max_file_age_hours: int = 1  # partial downloads and leftovers
    cleanup_interval_minutes: int = 15
    # Finished files are kept as a cache: a repeated request (same video and
    # quality) is answered from it without downloading again. Least recently
    # used files go first once the cache passes its size.
    cache_max_gb: float = Field(default=10, ge=0)
    cache_max_age_hours: int = Field(default=72, ge=1)
    # New downloads are refused while the disk has less free space than this
    min_free_disk_mb: int = Field(default=2048, ge=0)

    # Download settings
    max_concurrent_downloads: int = Field(default=3, ge=1)
    max_queued_downloads: int = Field(default=20, ge=0)
    download_timeout_seconds: int = 3600  # 1 hour
    # GET /api/download waits this long for the file before answering 202
    # (kept well under proxy limits such as Cloudflare's 100 s)
    link_download_wait_seconds: float = Field(default=25, ge=0)
    # Largest download allowed, checked against the size the platform reports
    # before downloading (and enforced per file while downloading)
    max_file_size_mb: int = Field(default=4000, ge=1)
    # Applies when the size can't be estimated
    max_duration_minutes: int = Field(default=180, ge=1)
    # Downloads one visitor (IP) may have running or queued at once; requests
    # with an access key are exempt
    max_active_downloads_per_client: int = Field(default=3, ge=1)

    # Browser cookies for platforms that require auth
    # Options: "chrome", "firefox", "safari", "edge", "brave", "opera", "chromium", "" to disable
    cookies_from_browser: str = ""
    # Path to a Netscape-format cookies.txt file (for Docker/server deployments)
    # Export from incognito session with a throwaway account to avoid bans
    cookies_file: str = ""

    # Admin view at /login. Empty password disables it.
    admin_password: SecretStr = Field(default=SecretStr(""), repr=False)
    admin_session_hours: int = Field(default=168, ge=1)  # 7 days

    # Status page monitor
    status_check_interval_seconds: int = Field(default=60, ge=5)
    status_site_url: str = "http://frontend:47651/"  # the website, inside compose
    status_history_days: int = Field(default=90, ge=1)
    system_sample_days: int = Field(default=7, ge=1)

    # Rate limiting
    rate_limit_downloads: str = "10/minute"
    api_keys: SecretStr = Field(default=SecretStr(""), repr=False)

    @field_validator("api_keys")
    @classmethod
    def validate_api_keys(cls, value: SecretStr) -> SecretStr:
        """Reject ambiguous credentials without including them in errors."""
        if not value.get_secret_value().strip():
            return value
        names = set()
        secrets = set()
        for entry in value.get_secret_value().split(","):
            parts = entry.split(":")
            if len(parts) != 2 or not all(part.strip() for part in parts):
                raise ValueError("API_KEYS must contain comma-separated name:key pairs")
            name, secret = (part.strip() for part in parts)
            if name in names or secret in secrets:
                raise ValueError("API_KEYS must contain unique names and keys")
            names.add(name)
            secrets.add(secret)
        return value

    @property
    def named_api_keys(self) -> dict[str, str]:
        """Return credentials that have already passed configuration validation."""
        return dict(
            tuple(part.strip() for part in entry.split(":"))
            for entry in self.api_keys.get_secret_value().split(",")
            if entry.strip()
        )

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
        "threads.net",
        "www.threads.net",
        "threads.com",
        "www.threads.com",
        "tiktok.com",
        "www.tiktok.com",
        "vm.tiktok.com",
    ]

    # Database
    database_url: str = "sqlite+aiosqlite:///./wololo.db"

    # CORS origins (for development)
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:47651",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:47651",
    ]

    class Config:
        env_file = ".env"
        extra = "ignore"
        hide_input_in_errors = True


settings = Settings()

# Ensure temp directory exists
settings.temp_dir.mkdir(parents=True, exist_ok=True)
