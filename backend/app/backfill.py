"""Estimate status-page history for the days before the monitor existed.

Evidence, from strongest to weakest:

0. Cloudflare analytics (last ~30 days, sampled counts) from
   scripts/cloudflare-status-evidence.py: requests answered per day and the
   minutes with 5xx errors, which count as downtime.
1. Cloudflare tunnel log (cloudflared). The tunnel logs every request it
   could not deliver ("Unable to reach the origin service") and its own
   restarts. A day it covers with no failed request to Wololo means the site
   answered every request that day; tunnel restarts count as downtime (from
   the last line before the restart to the first registered connection).
2. Download history. Every stored job is a request the API accepted and
   answered (the row is written while answering it), so a day with jobs
   proves the site and the API were up at those moments. It says nothing
   about the rest of the day: those days are marked operational without an
   uptime figure.

Usage: scripts/backfill-status.sh (gathers the evidence on the host and runs
this inside the backend container), or directly:

    python -m app.backfill --tunnel-log cloudflared.log --cloudflare cf.json

Rows are replaced on every run, and days the monitor already covers are
never touched.
"""
import argparse
import asyncio
import json
import re
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Iterable, Optional

from sqlalchemy import delete, func, select

from .database import get_db_context, init_db
from .models import DownloadJob, StatusBackfill, StatusCheck
from .monitoring import PROBED_COMPONENTS, uptime_status

HOST = "wololo.edilson.dev"
LINE_TIME = re.compile(r"^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)Z")


def _time(line: str) -> Optional[datetime]:
    match = LINE_TIME.match(line)
    return datetime.strptime(match.group(1), "%Y-%m-%dT%H:%M:%S") if match else None


class TunnelEvidence:
    """Outage windows and coverage read from a cloudflared log."""

    def __init__(self, lines: Iterable[str], host: str = HOST):
        self.first: Optional[datetime] = None
        self.last: Optional[datetime] = None
        self.outages: list[tuple[datetime, datetime, str]] = []
        self.failed_requests: list[datetime] = []
        self.requests_seen: dict[date, int] = defaultdict(int)

        previous: Optional[datetime] = None
        restart_from: Optional[datetime] = None
        for line in lines:
            at = _time(line)
            if at is None:
                continue
            self.first = self.first or at
            self.last = at
            if "Starting tunnel" in line:
                # Down from the last sign of life before the restart. The
                # first start of the log has no "before" to measure from.
                restart_from = previous
            elif restart_from and "Registered tunnel connection" in line:
                # Restarts of a few seconds (a config reload) aren't outages
                if (at - restart_from).total_seconds() >= 60:
                    self.outages.append((restart_from, at, "tunnel restart, up to"))
                restart_from = None
            if f"dest=https://{host}" in line or f"dest=http://{host}" in line:
                self.requests_seen[at.date()] += 1
                if "Unable to reach the origin" in line:
                    self.failed_requests.append(at)
            previous = at

    def covers(self, day: date) -> bool:
        return bool(self.first and self.last and self.first.date() <= day <= self.last.date())

    def downtime(self, day: date) -> tuple[float, list[str]]:
        """Minutes down on a day (UTC) and why."""
        start = datetime.combine(day, datetime.min.time())
        end = start + timedelta(days=1)
        minutes = 0.0
        reasons = []
        for down_from, down_to, why in self.outages:
            overlap = (min(end, down_to) - max(start, down_from)).total_seconds() / 60
            if overlap > 0:
                minutes += overlap
                reasons.append(f"{why} {round(overlap)} min down")
        failed_minutes = {
            at.replace(second=0) for at in self.failed_requests if start <= at < end
        }
        if failed_minutes:
            minutes += len(failed_minutes)
            reasons.append(f"{len(failed_minutes)} min with requests the server didn't answer")
        return min(minutes, 1440.0), reasons


def _requests(count: int) -> str:
    return f"{count} download request{'s' if count != 1 else ''} answered"


class CloudflareEvidence:
    """Per-day request counts and 5xx minutes from Cloudflare analytics."""

    def __init__(self, data: dict):
        self.days: dict[date, dict] = {date.fromisoformat(k): v for k, v in data.get("days", {}).items()}
        self.error_minutes = [
            datetime.fromisoformat(m.replace("Z", "+00:00")).replace(tzinfo=None)
            for m in data.get("error_minutes", [])
        ]
        since = data.get("since")
        self.since = datetime.fromisoformat(since).replace(tzinfo=None).date() if since else None
        until = data.get("until")
        self.until = datetime.fromisoformat(until).replace(tzinfo=None).date() if until else None

    def covers(self, day: date) -> bool:
        return bool(self.since and self.until and self.since <= day <= self.until)

    def down_minutes(self, day: date) -> set[datetime]:
        return {m for m in self.error_minutes if m.date() == day}


def estimate_days(
    days: list[date],
    tunnel: Optional[TunnelEvidence],
    requests_per_day: dict[date, int],
    cloudflare: Optional[CloudflareEvidence] = None,
) -> dict[date, tuple[str, Optional[float], str]]:
    """(status, uptime, note) per day that has some evidence."""
    result = {}
    for day in days:
        downloads = requests_per_day.get(day, 0)
        tunnel_covers = bool(tunnel and tunnel.covers(day))
        cloudflare_covers = bool(cloudflare and cloudflare.covers(day))
        if tunnel_covers or cloudflare_covers:
            minutes = 0.0
            notes = []
            if cloudflare_covers:
                counts = cloudflare.days.get(day, {})
                errors = cloudflare.down_minutes(day)
                minutes += len(errors)
                answered = counts.get("ok", 0)
                notes.append(
                    "Cloudflare: "
                    # Counts are sampled: a quiet day can show none
                    + (f"~{answered} requests answered" if answered else "no sampled requests")
                    + (f", 5xx errors in {len(errors)} min" if errors else ", no server errors")
                )
            if tunnel_covers:
                tunnel_minutes, reasons = tunnel.downtime(day)
                minutes += tunnel_minutes
                notes.append("tunnel log: " + ("; ".join(reasons) if reasons else "no unanswered requests"))
            if downloads:
                notes.append(_requests(downloads))
            uptime = round(100 - min(minutes, 1440.0) * 100 / 1440, 2)
            result[day] = (uptime_status(uptime), uptime, "Estimated from " + "; ".join(notes))
        elif downloads:
            result[day] = (
                "operational",
                None,
                f"Before monitoring: {_requests(downloads)} this day",
            )
    return result


async def run(
    tunnel_lines: Optional[Iterable[str]],
    dry_run: bool = False,
    cloudflare: Optional[CloudflareEvidence] = None,
) -> list[tuple]:
    await init_db()
    tunnel = TunnelEvidence(tunnel_lines) if tunnel_lines is not None else None
    async with get_db_context() as db:
        first_check = (await db.execute(select(func.min(StatusCheck.checked_at)))).scalar()
        last_day = (first_check.date() if first_check else date.today()) - timedelta(days=1)
        rows = (await db.execute(
            select(func.date(DownloadJob.created_at), func.count())
            .group_by(func.date(DownloadJob.created_at))
        )).all()
        requests = {date.fromisoformat(str(day)): count for day, count in rows if day}

        starts = [d for d in requests] + ([tunnel.first.date()] if tunnel and tunnel.first else [])
        if not starts:
            return []
        first_day = min(starts)
        days = [first_day + timedelta(days=n) for n in range((last_day - first_day).days + 1)]
        estimates = estimate_days(days, tunnel, requests, cloudflare)

        output = []
        for day, (status, uptime, note) in sorted(estimates.items()):
            for component in PROBED_COMPONENTS:
                output.append((day.isoformat(), component, status, uptime, note))
        if dry_run:
            return output

        await db.execute(delete(StatusBackfill))
        for day, component, status, uptime, note in output:
            db.add(StatusBackfill(day=day, component=component, status=status, uptime=uptime, note=note))
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tunnel-log", help="cloudflared log file, or - for stdin")
    parser.add_argument("--cloudflare", help="JSON from scripts/cloudflare-status-evidence.py")
    parser.add_argument("--dry-run", action="store_true", help="print the estimate without saving it")
    args = parser.parse_args()

    lines = None
    if args.tunnel_log == "-":
        lines = sys.stdin.read().splitlines()
    elif args.tunnel_log:
        with open(args.tunnel_log, errors="ignore") as handle:
            lines = handle.read().splitlines()

    cloudflare = None
    if args.cloudflare:
        with open(args.cloudflare) as handle:
            cloudflare = CloudflareEvidence(json.load(handle))

    output = asyncio.run(run(lines, dry_run=args.dry_run, cloudflare=cloudflare))
    for day, component, status, uptime, note in output:
        if component == "api":
            continue  # same evidence for both components; print once
        print(f"{day}  {status:<11} {'' if uptime is None else f'{uptime:6.2f}%'}  {note}")
    print(f"{len(output) // len(PROBED_COMPONENTS)} days {'estimated (dry run)' if args.dry_run else 'saved'}")


if __name__ == "__main__":
    main()
