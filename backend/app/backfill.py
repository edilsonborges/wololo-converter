"""Estimate status-page history for the days before the monitor existed.

Evidence, from strongest to weakest:

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

Usage (inside the backend container, the log piped from the host):

    docker exec -i wololo-backend python -m app.backfill --tunnel-log - \\
        < ~/Library/Logs/edilson-cloudflared-tunnel.log

Rows are replaced on every run, and days the monitor already covers are
never touched.
"""
import argparse
import asyncio
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


def estimate_days(
    days: list[date],
    tunnel: Optional[TunnelEvidence],
    requests_per_day: dict[date, int],
) -> dict[date, tuple[str, Optional[float], str]]:
    """(status, uptime, note) per day that has some evidence."""
    result = {}
    for day in days:
        downloads = requests_per_day.get(day, 0)
        if tunnel and tunnel.covers(day):
            minutes, reasons = tunnel.downtime(day)
            uptime = round(100 - minutes * 100 / 1440, 2)
            note = "Estimated from the Cloudflare tunnel log: " + (
                "; ".join(reasons) if reasons else "no unanswered requests"
            )
            if downloads:
                note += f"; {_requests(downloads)}"
            result[day] = (uptime_status(uptime), uptime, note)
        elif downloads:
            result[day] = (
                "operational",
                None,
                f"Before monitoring: {_requests(downloads)} this day",
            )
    return result


async def run(tunnel_lines: Optional[Iterable[str]], dry_run: bool = False) -> list[tuple]:
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
        estimates = estimate_days(days, tunnel, requests)

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
    parser.add_argument("--dry-run", action="store_true", help="print the estimate without saving it")
    args = parser.parse_args()

    lines = None
    if args.tunnel_log == "-":
        lines = sys.stdin.read().splitlines()
    elif args.tunnel_log:
        with open(args.tunnel_log, errors="ignore") as handle:
            lines = handle.read().splitlines()

    output = asyncio.run(run(lines, dry_run=args.dry_run))
    for day, component, status, uptime, note in output:
        if component == "api":
            continue  # same evidence for both components; print once
        print(f"{day}  {status:<11} {'' if uptime is None else f'{uptime:6.2f}%'}  {note}")
    print(f"{len(output) // len(PROBED_COMPONENTS)} days {'estimated (dry run)' if args.dry_run else 'saved'}")


if __name__ == "__main__":
    main()
