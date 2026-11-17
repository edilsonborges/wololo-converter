"""Availability checks for the status page and machine usage for the admin view.

Every ``status_check_interval_seconds`` the monitor probes the website and the
API, stores the results and samples CPU, memory and disk. The status page
turns the probes into daily uptime and the download history into per-platform
success rates.
"""
import asyncio
import logging
import time
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Optional

import httpx
import psutil
from sqlalchemy import Integer, cast, delete, func, select, text

from .config import settings
from .database import get_db_context
from .models import DownloadJob, JobStatus, StatusBackfill, StatusCheck, SystemSample, utcnow

logger = logging.getLogger(__name__)

# Components probed by the monitor, in display order
PROBED_COMPONENTS = {
    "website": "Website",
    "api": "API",
}

# Download platforms shown on the status page, in display order
PLATFORM_COMPONENTS = {
    "youtube": "YouTube",
    "instagram": "Instagram",
    "tiktok": "TikTok",
    "twitter": "Twitter/X",
    "threads": "Threads",
    "facebook": "Facebook",
}

OPERATIONAL = "operational"
DEGRADED = "degraded"
OUTAGE = "outage"
NO_DATA = "no_data"
SEVERITY = {NO_DATA: 0, OPERATIONAL: 0, DEGRADED: 1, OUTAGE: 2}

_status_cache: dict = {"at": 0.0, "value": None}
STATUS_CACHE_SECONDS = 30


# ------------------------------------------------------------------ probes

async def probe_website(client: httpx.AsyncClient) -> tuple[bool, Optional[int], Optional[str]]:
    started = time.perf_counter()
    try:
        response = await client.get(settings.status_site_url)
        latency = int((time.perf_counter() - started) * 1000)
        if response.status_code == 200 and "<div id=\"root\">" in response.text:
            return True, latency, None
        return False, latency, f"HTTP {response.status_code}"
    except Exception as e:
        return False, None, type(e).__name__


async def probe_api() -> tuple[bool, Optional[int], Optional[str]]:
    """The API is up when it can reach its database and write downloads."""
    started = time.perf_counter()
    try:
        async with get_db_context() as db:
            await db.execute(text("SELECT 1"))
        settings.temp_dir.mkdir(parents=True, exist_ok=True)
        probe = settings.temp_dir / ".status-probe"
        probe.write_text("ok")
        probe.unlink()
        return True, int((time.perf_counter() - started) * 1000), None
    except Exception as e:
        return False, None, type(e).__name__


def disk_usage_percent() -> float:
    try:
        return psutil.disk_usage(str(settings.temp_dir)).percent
    except OSError:
        return psutil.disk_usage("/").percent


def queue_counts() -> tuple[int, int]:
    from .download_service import download_service

    running = len(download_service._running_jobs)
    return running, max(0, len(download_service.active_jobs) - running)


async def run_checks(client: httpx.AsyncClient) -> None:
    now = utcnow()
    website = await probe_website(client)
    api = await probe_api()
    active, queued = queue_counts()
    async with get_db_context() as db:
        for component, (ok, latency, detail) in (("website", website), ("api", api)):
            db.add(StatusCheck(
                checked_at=now, component=component, ok=ok, latency_ms=latency, detail=detail,
            ))
        db.add(SystemSample(
            sampled_at=now,
            cpu_percent=psutil.cpu_percent(interval=None),
            memory_percent=psutil.virtual_memory().percent,
            disk_percent=disk_usage_percent(),
            active_downloads=active,
            queued_downloads=queued,
        ))


async def prune_history() -> None:
    now = utcnow()
    async with get_db_context() as db:
        await db.execute(delete(StatusCheck).where(
            StatusCheck.checked_at < now - timedelta(days=settings.status_history_days + 1)
        ))
        await db.execute(delete(SystemSample).where(
            SystemSample.sampled_at < now - timedelta(days=settings.system_sample_days)
        ))


async def run_monitor() -> None:
    """Background loop started with the app."""
    psutil.cpu_percent(interval=None)  # the first reading is always 0
    last_prune = 0.0
    async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
        while True:
            try:
                await run_checks(client)
                if time.monotonic() - last_prune > 3600:
                    await prune_history()
                    last_prune = time.monotonic()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Status check failed")
            await asyncio.sleep(settings.status_check_interval_seconds)


# ------------------------------------------------------------------ status page

def uptime_status(uptime: Optional[float]) -> str:
    if uptime is None:
        return NO_DATA
    if uptime >= 99.0:
        return OPERATIONAL
    if uptime >= 95.0:
        return DEGRADED
    return OUTAGE


def download_status(completed: int, failed: int) -> str:
    """Downloads fail for reasons of their own (private or deleted videos), so
    a couple of failures don't make a platform degraded."""
    total = completed + failed
    if total == 0:
        return NO_DATA
    rate = completed / total
    if failed < 2 or rate >= 0.8:
        return OPERATIONAL
    if rate >= 0.5:
        return DEGRADED
    return OUTAGE


def _days(today: date, count: int) -> list[date]:
    return [today - timedelta(days=offset) for offset in range(count - 1, -1, -1)]


async def probe_component_days(db, days: list[date], now: datetime) -> dict:
    """Daily uptime per probed component. A missing probe counts as down: the
    monitor runs on the same server, so silence means the server was down."""
    start = datetime.combine(days[0], datetime.min.time())
    rows = (await db.execute(
        select(
            StatusCheck.component,
            func.date(StatusCheck.checked_at),
            func.count(),
            func.sum(cast(StatusCheck.ok, Integer)),  # sum() would keep the Boolean type
            func.min(StatusCheck.checked_at),
        )
        .where(StatusCheck.checked_at >= start)
        .group_by(StatusCheck.component, func.date(StatusCheck.checked_at))
    )).all()
    first_check = (await db.execute(select(func.min(StatusCheck.checked_at)))).scalar()

    by_day: dict = defaultdict(dict)
    for component, day, total, ok, first in rows:
        by_day[component][str(day)] = (int(total), int(ok or 0), first)

    # Estimates for the days before the monitor existed (app/backfill.py)
    backfill: dict = defaultdict(dict)
    for row in (await db.execute(
        select(StatusBackfill).where(StatusBackfill.day >= days[0].isoformat())
    )).scalars():
        backfill[row.component][row.day] = row

    interval = settings.status_check_interval_seconds
    result = {}
    for component in PROBED_COMPONENTS:
        series = []
        for day in days:
            total, ok, _ = by_day[component].get(day.isoformat(), (0, 0, None))
            day_start = datetime.combine(day, datetime.min.time())
            window_start = max(day_start, first_check) if first_check else None
            window_end = min(day_start + timedelta(days=1), now)
            if window_start is None or window_end <= window_start:
                estimate = backfill[component].get(day.isoformat())
                if estimate:
                    series.append({
                        "date": day.isoformat(),
                        "status": estimate.status,
                        "uptime": estimate.uptime,
                        "note": estimate.note,
                        "estimated": True,
                    })
                else:
                    series.append({"date": day.isoformat(), "status": NO_DATA, "uptime": None})
                continue
            expected = max(1, int((window_end - window_start).total_seconds() // interval))
            uptime = round(min(100.0, ok * 100 / max(expected, total)), 2)
            series.append({"date": day.isoformat(), "status": uptime_status(uptime), "uptime": uptime})
        result[component] = series
    return result


async def platform_days(db, days: list[date]) -> dict:
    start = datetime.combine(days[0], datetime.min.time())
    rows = (await db.execute(
        select(
            DownloadJob.platform,
            func.date(DownloadJob.created_at),
            DownloadJob.status,
            func.count(),
        )
        .where(
            DownloadJob.created_at >= start,
            DownloadJob.status.in_([JobStatus.COMPLETED.value, JobStatus.FAILED.value]),
            # Jobs cut short by a server restart say nothing about the platform
            func.coalesce(DownloadJob.current_stage, "") != "Interrupted",
        )
        .group_by(DownloadJob.platform, func.date(DownloadJob.created_at), DownloadJob.status)
    )).all()

    counts: dict = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    for platform, day, status, count in rows:
        index = 0 if status == JobStatus.COMPLETED.value else 1
        counts[platform][str(day)][index] += count

    result = {}
    for platform in PLATFORM_COMPONENTS:
        series = []
        for day in days:
            completed, failed = counts[platform].get(day.isoformat(), (0, 0))
            total = completed + failed
            series.append({
                "date": day.isoformat(),
                "status": download_status(completed, failed),
                "uptime": round(completed * 100 / total, 2) if total else None,
                "completed": completed,
                "failed": failed,
            })
        result[platform] = series
    return result


def _summary(series: list[dict], weight_key: Optional[str] = None) -> Optional[float]:
    values = [d["uptime"] for d in series if d["uptime"] is not None]
    if not values:
        return None
    if weight_key is None:
        return round(sum(values) / len(values), 2)
    completed = sum(d["completed"] for d in series)
    total = completed + sum(d["failed"] for d in series)
    return round(completed * 100 / total, 2) if total else None


async def latest_probe(db, component: str) -> Optional[StatusCheck]:
    return (await db.execute(
        select(StatusCheck)
        .where(StatusCheck.component == component)
        .order_by(StatusCheck.checked_at.desc())
        .limit(1)
    )).scalar_one_or_none()


async def build_status(db, days_count: Optional[int] = None) -> dict:
    now = utcnow()
    days = _days(now.date(), days_count or settings.status_history_days)
    probes = await probe_component_days(db, days, now)
    platforms = await platform_days(db, days)

    components = []
    stale_after = timedelta(seconds=settings.status_check_interval_seconds * 3)
    for key, name in PROBED_COMPONENTS.items():
        latest = await latest_probe(db, key)
        if latest is None:
            current = NO_DATA
        elif not latest.ok:
            current = OUTAGE
        elif now - latest.checked_at > stale_after:
            current = DEGRADED
        else:
            current = OPERATIONAL
        components.append({
            "id": key,
            "name": name,
            "group": "Service",
            "status": current,
            "uptime": _summary(probes[key]),
            "latency_ms": latest.latency_ms if latest else None,
            "days": probes[key],
        })

    for key, name in PLATFORM_COMPONENTS.items():
        series = platforms[key]
        # Current state: the latest day with downloads in the last week
        recent = next((d for d in reversed(series[-7:]) if d["status"] != NO_DATA), None)
        components.append({
            "id": key,
            "name": name,
            "group": "Downloads",
            "status": recent["status"] if recent else NO_DATA,
            "uptime": _summary(series, weight_key="completed"),
            "latency_ms": None,
            "days": series,
        })

    worst = max((SEVERITY[c["status"]] for c in components), default=0)
    overall = {0: OPERATIONAL, 1: DEGRADED, 2: OUTAGE}[worst]
    return {
        "status": overall,
        "generated_at": now.isoformat() + "Z",
        "days": len(days),
        "components": components,
    }


async def cached_status(db) -> dict:
    if _status_cache["value"] is not None and time.monotonic() - _status_cache["at"] < STATUS_CACHE_SECONDS:
        return _status_cache["value"]
    value = await build_status(db)
    _status_cache.update(at=time.monotonic(), value=value)
    return value


# ------------------------------------------------------------------ admin

def system_snapshot() -> dict:
    from .utils import get_directory_size

    memory = psutil.virtual_memory()
    try:
        disk = psutil.disk_usage(str(settings.temp_dir))
    except OSError:
        disk = psutil.disk_usage("/")
    process = psutil.Process()
    active, queued = queue_counts()
    try:
        load = [round(v, 2) for v in psutil.getloadavg()]
    except (AttributeError, OSError):
        load = None
    return {
        "cpu_percent": psutil.cpu_percent(interval=None),
        "cpu_count": psutil.cpu_count(),
        "load_average": load,
        "memory_percent": memory.percent,
        "memory_used_bytes": memory.used,
        "memory_total_bytes": memory.total,
        "disk_percent": disk.percent,
        "disk_used_bytes": disk.used,
        "disk_total_bytes": disk.total,
        "temp_dir_bytes": get_directory_size(settings.temp_dir) if settings.temp_dir.exists() else 0,
        "process_memory_bytes": process.memory_info().rss,
        "process_started_at": datetime.utcfromtimestamp(process.create_time()).isoformat() + "Z",
        "active_downloads": active,
        "queued_downloads": queued,
        "max_concurrent_downloads": settings.max_concurrent_downloads,
    }
