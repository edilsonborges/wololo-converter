"""Admin view: login with the ADMIN_PASSWORD, download history and machine usage.

The session is a signed cookie (expiry + HMAC) scoped to /api/admin, so no
session table is needed and changing the password signs everyone out.
"""
import hashlib
import hmac
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .access import client_ip
from .config import settings
from .database import get_session
from .models import DownloadJob, JobStatus, SystemSample, utcnow
from . import monitoring
from .routes import limiter

COOKIE_NAME = "wololo_admin"
COOKIE_PATH = "/api/admin"

router = APIRouter(prefix="/admin", tags=["admin"], include_in_schema=False)


class LoginRequest(BaseModel):
    password: str = Field(..., min_length=1, max_length=200)


def _password() -> str:
    return settings.admin_password.get_secret_value()


def _signing_key() -> bytes:
    return hashlib.sha256(b"wololo-admin-session:" + _password().encode("utf-8")).digest()


def make_session_token(expires_at: int) -> str:
    signature = hmac.new(_signing_key(), f"admin.{expires_at}".encode(), hashlib.sha256).hexdigest()
    return f"{expires_at}.{signature}"


def valid_session_token(token: Optional[str]) -> bool:
    if not token or not _password():
        return False
    expires, _, signature = token.partition(".")
    if not expires.isdigit() or int(expires) < time.time():
        return False
    expected = make_session_token(int(expires)).partition(".")[2]
    return hmac.compare_digest(signature, expected)


def require_admin(request: Request) -> None:
    if not _password():
        raise HTTPException(status_code=404, detail="Not Found")
    if not valid_session_token(request.cookies.get(COOKIE_NAME)):
        raise HTTPException(status_code=401, detail="Not signed in")


@router.post("/login")
# Limited by the visitor's real IP, not the proxy's
@limiter.limit("5/minute", key_func=client_ip)
async def login(request: Request, response: Response, body: LoginRequest):
    password = _password()
    if not password:
        raise HTTPException(status_code=404, detail="Not Found")
    if not hmac.compare_digest(body.password.encode("utf-8"), password.encode("utf-8")):
        raise HTTPException(status_code=401, detail="Wrong password")
    max_age = settings.admin_session_hours * 3600
    response.set_cookie(
        COOKIE_NAME,
        make_session_token(int(time.time()) + max_age),
        max_age=max_age,
        path=COOKIE_PATH,
        httponly=True,
        secure=True,
        samesite="strict",
    )
    return {"ok": True}


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie(COOKIE_NAME, path=COOKIE_PATH, secure=True, httponly=True, samesite="strict")
    return {"ok": True}


@router.get("/me", dependencies=[Depends(require_admin)])
async def me():
    return {"ok": True}


def _job_row(job: DownloadJob) -> dict:
    elapsed = queued = None
    if job.started_at and job.completed_at:
        elapsed = round((job.completed_at - job.started_at).total_seconds())
    if job.created_at and job.started_at:
        queued = max(0, round((job.started_at - job.created_at).total_seconds()))
    return {
        "id": job.id,
        "created_at": job.created_at.isoformat() + "Z" if job.created_at else None,
        "started_at": job.started_at.isoformat() + "Z" if job.started_at else None,
        "completed_at": job.completed_at.isoformat() + "Z" if job.completed_at else None,
        "elapsed_seconds": elapsed,
        "queued_seconds": queued,
        "status": job.status,
        "platform": job.platform,
        "quality": job.quality,
        "url": job.url,
        "title": job.title,
        "filename": job.filename,
        "file_size": job.file_size,
        "duration": job.duration,
        "error_message": job.error_message,
        "client_ip": job.client_ip,
        "client_name": job.client_name,
        "source": job.source,
        "user_agent": job.user_agent,
        "estimated_size": job.estimated_size,
        "request_count": job.request_count or 1,
        "reused_from": job.reused_from,
    }


# Time ranges of the history view and the width of each histogram bar
RANGES = {
    "24h": (timedelta(hours=24), timedelta(hours=1)),
    "7d": (timedelta(days=7), timedelta(hours=6)),
    "30d": (timedelta(days=30), timedelta(days=1)),
    "90d": (timedelta(days=90), timedelta(days=1)),
    "all": (None, None),
}
RangeName = Query("all", pattern="^(24h|7d|30d|90d|all)$")


def _parse_time(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid time: {value}")
    if parsed.tzinfo:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _job_filters(
    status: Optional[str],
    platform: Optional[str],
    q: Optional[str],
    since: Optional[datetime],
    until: Optional[datetime],
) -> list:
    filters = []
    if status:
        filters.append(DownloadJob.status == status)
    if platform:
        filters.append(DownloadJob.platform == platform)
    if q:
        like = f"%{q}%"
        filters.append(or_(
            DownloadJob.title.ilike(like),
            DownloadJob.url.ilike(like),
            DownloadJob.client_ip.ilike(like),
            DownloadJob.client_name.ilike(like),
            DownloadJob.user_agent.ilike(like),
        ))
    if since:
        filters.append(DownloadJob.created_at >= since)
    if until:
        filters.append(DownloadJob.created_at < until)
    return filters


def _range_window(range_name: str, since: Optional[str], until: Optional[str]):
    """Explicit since/until (a clicked bar) win over the named range."""
    span, _ = RANGES[range_name]
    start = _parse_time(since) or (utcnow() - span if span else None)
    return start, _parse_time(until)


@router.get("/jobs", dependencies=[Depends(require_admin)])
async def jobs(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    status: Optional[str] = None,
    platform: Optional[str] = None,
    q: Optional[str] = Query(None, max_length=200, description="Search title, URL, IP, key or user agent"),
    range: str = RangeName,
    since: Optional[str] = None,
    until: Optional[str] = None,
    db: AsyncSession = Depends(get_session),
):
    start, end = _range_window(range, since, until)
    filters = _job_filters(status, platform, q, start, end)
    total = (await db.execute(select(func.count()).select_from(DownloadJob).where(*filters))).scalar()
    rows = (await db.execute(
        select(DownloadJob).where(*filters)
        .order_by(desc(DownloadJob.created_at)).limit(limit).offset(offset)
    )).scalars().all()
    return {"total": total, "items": [_job_row(job) for job in rows]}


def _bucket_start(at: datetime, width: timedelta) -> datetime:
    if width >= timedelta(days=1):
        return at.replace(hour=0, minute=0, second=0, microsecond=0)
    hours = int(width.total_seconds() // 3600)
    return at.replace(hour=at.hour - at.hour % hours, minute=0, second=0, microsecond=0)


@router.get("/insights", dependencies=[Depends(require_admin)])
async def insights(
    status: Optional[str] = None,
    platform: Optional[str] = None,
    q: Optional[str] = Query(None, max_length=200),
    range: str = RangeName,
    tz_offset: int = Query(0, ge=-840, le=840, description="Viewer's UTC offset as JS getTimezoneOffset()"),
    db: AsyncSession = Depends(get_session),
):
    """Histogram of downloads over time (by status) and the platform split,
    for the same filters as the history list. Bars follow the viewer's clock
    (a day bar is the viewer's day), so their labels match what they list."""
    span, width = RANGES[range]
    shift = timedelta(minutes=tz_offset)  # UTC - local
    now = utcnow()
    start = now - span if span else None
    filters = _job_filters(status, platform, q, start, None)
    rows = (await db.execute(
        select(DownloadJob.created_at, DownloadJob.status, DownloadJob.platform, DownloadJob.current_stage)
        .where(*filters)
    )).all()

    if start is None:
        # Whole history: one bar per day from the first download
        first = min((r[0] for r in rows if r[0]), default=now)
        width = timedelta(days=1)
        start = first
    # Buckets are computed on the viewer's local clock
    first_bucket = _bucket_start(start - shift, width)
    local_now = now - shift
    buckets: dict[datetime, dict] = {}
    cursor = first_bucket
    while cursor <= local_now:
        buckets[cursor] = {"completed": 0, "failed": 0, "cancelled": 0, "other": 0}
        cursor += width

    platforms: dict[str, int] = {}
    for created_at, job_status, job_platform, stage in rows:
        if created_at is None:
            continue
        key = _bucket_start(created_at - shift, width)
        bucket = buckets.get(key)
        if bucket is not None:
            if stage == "Interrupted":
                # Cut short by a server restart: not the platform's failure
                series = "cancelled"
            elif job_status in ("completed", "failed", "cancelled"):
                series = job_status
            else:
                series = "other"
            bucket[series] += 1
        platforms[job_platform] = platforms.get(job_platform, 0) + 1

    return {
        "range": range,
        "bucket_seconds": int(width.total_seconds()),
        "total": len(rows),
        "buckets": [
            {"start": (at + shift).isoformat() + "Z", "end": (at + width + shift).isoformat() + "Z", **counts}
            for at, counts in buckets.items()
        ],
        "platforms": [
            {"platform": name, "count": count}
            for name, count in sorted(platforms.items(), key=lambda item: -item[1])
        ],
    }


async def _period_summary(db: AsyncSession, since) -> dict:
    rows = (await db.execute(
        select(DownloadJob.status, func.count(), func.coalesce(func.sum(DownloadJob.file_size), 0))
        .where(DownloadJob.created_at >= since)
        .group_by(DownloadJob.status)
    )).all()
    by_status = {status: count for status, count, _ in rows}
    # Jobs cut short by a server restart aren't download failures
    interrupted = (await db.execute(
        select(func.count()).select_from(DownloadJob)
        .where(DownloadJob.created_at >= since, DownloadJob.current_stage == "Interrupted")
    )).scalar()
    completed = by_status.get(JobStatus.COMPLETED.value, 0)
    failed = by_status.get(JobStatus.FAILED.value, 0) - interrupted
    unique_ips = (await db.execute(
        select(func.count(func.distinct(DownloadJob.client_ip)))
        .where(DownloadJob.created_at >= since, DownloadJob.client_ip.is_not(None))
    )).scalar()
    return {
        "total": sum(by_status.values()),
        "completed": completed,
        "failed": failed,
        "cancelled": by_status.get(JobStatus.CANCELLED.value, 0),
        "interrupted": interrupted,
        "success_rate": round(completed * 100 / (completed + failed), 1) if completed + failed else None,
        "bytes": sum(size for status, _, size in rows if status == JobStatus.COMPLETED.value),
        "unique_ips": unique_ips,
    }


@router.get("/summary", dependencies=[Depends(require_admin)])
async def summary(db: AsyncSession = Depends(get_session)):
    now = utcnow()
    week = now - timedelta(days=7)
    platforms = (await db.execute(
        select(DownloadJob.platform, func.count())
        .where(DownloadJob.created_at >= week)
        .group_by(DownloadJob.platform).order_by(desc(func.count()))
    )).all()
    top_ips = (await db.execute(
        select(DownloadJob.client_ip, func.count(), func.max(DownloadJob.created_at))
        .where(DownloadJob.created_at >= week, DownloadJob.client_ip.is_not(None))
        .group_by(DownloadJob.client_ip).order_by(desc(func.count())).limit(10)
    )).all()
    return {
        "last_24h": await _period_summary(db, now - timedelta(days=1)),
        "last_7d": await _period_summary(db, week),
        "last_30d": await _period_summary(db, now - timedelta(days=30)),
        "platforms_7d": [{"platform": p, "count": c} for p, c in platforms],
        "top_ips_7d": [
            {"ip": ip, "count": c, "last_seen": last.isoformat() + "Z" if last else None}
            for ip, c, last in top_ips
        ],
    }


@router.get("/system", dependencies=[Depends(require_admin)])
async def system(
    hours: int = Query(24, ge=1, le=24 * 7),
    db: AsyncSession = Depends(get_session),
):
    samples = (await db.execute(
        select(SystemSample)
        .where(SystemSample.sampled_at >= utcnow() - timedelta(hours=hours))
        .order_by(SystemSample.sampled_at)
    )).scalars().all()
    # Keep the payload small: at most ~300 points
    step = max(1, len(samples) // 300)
    return {
        "now": monitoring.system_snapshot(),
        "samples": [
            {
                "at": s.sampled_at.isoformat() + "Z",
                "cpu": round(s.cpu_percent, 1),
                "memory": round(s.memory_percent, 1),
                "disk": round(s.disk_percent, 1),
                "active": s.active_downloads,
                "queued": s.queued_downloads,
            }
            for s in samples[::step]
        ],
    }
