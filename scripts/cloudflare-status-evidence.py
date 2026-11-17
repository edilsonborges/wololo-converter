#!/usr/bin/env python3
"""Print Cloudflare's view of wololo.edilson.dev for the status backfill.

Reads a read-only API token (Zone > Analytics > Read) from
~/.config/cloudflare/analytics-token, or the CLOUDFLARE_API_TOKEN variable,
and prints JSON for `python -m app.backfill --cloudflare`:

    {"days": {"2026-10-18": {"ok": 110, "client_errors": 0, "server_errors": 0}},
     "error_minutes": ["2026-10-20T03:10:00Z"], "since": "...", "until": "..."}

Per-hostname analytics only go back about 30 days on the free plan, and the
counts are sampled. curl is used for HTTPS so the system certificates apply.
"""
import json
import os
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone

HOST = os.environ.get("WOLOLO_HOST", "wololo.edilson.dev")
ZONE_NAME = os.environ.get("CLOUDFLARE_ZONE", "edilson.dev")
TOKEN_FILE = os.path.expanduser("~/.config/cloudflare/analytics-token")


def token() -> str:
    value = os.environ.get("CLOUDFLARE_API_TOKEN")
    if not value:
        with open(TOKEN_FILE) as handle:
            value = handle.read()
    return value.strip()


def api(path: str, body=None) -> dict:
    cmd = ["curl", "-sS", "-H", f"Authorization: Bearer {token()}", "-H", "Content-Type: application/json"]
    if body is not None:
        cmd += ["-X", "POST", "--data-binary", json.dumps(body)]
    cmd.append("https://api.cloudflare.com/client/v4" + path)
    result = json.loads(subprocess.run(cmd, capture_output=True, text=True, check=True).stdout)
    if result.get("errors"):
        sys.exit(f"Cloudflare API error: {result['errors']}")
    return result


def groups(zone: str, since: datetime, until: datetime, fields: str, extra_filter: str = "") -> list:
    query = f"""query($z:String!,$a:Time!,$b:Time!){{viewer{{zones(filter:{{zoneTag:$z}}){{
      httpRequestsAdaptiveGroups(limit:10000, filter:{{datetime_geq:$a, datetime_lt:$b,
        clientRequestHTTPHost:"{HOST}" {extra_filter}}}){{ count dimensions{{ {fields} }} }}}}}}}}"""
    stamp = lambda t: t.strftime("%Y-%m-%dT%H:%M:%SZ")
    data = api("/graphql", {"query": query, "variables": {"z": zone, "a": stamp(since), "b": stamp(until)}})
    return data["data"]["viewer"]["zones"][0]["httpRequestsAdaptiveGroups"]


def main() -> None:
    zone = api(f"/zones?name={ZONE_NAME}")["result"][0]["id"]
    until = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    since = until - timedelta(days=30) + timedelta(minutes=5)  # the API allows at most 30 days

    days = defaultdict(lambda: {"ok": 0, "client_errors": 0, "server_errors": 0})
    for group in groups(zone, since, until, "date edgeResponseStatus"):
        status = group["dimensions"]["edgeResponseStatus"]
        key = "server_errors" if status >= 500 else "client_errors" if status >= 400 else "ok"
        days[group["dimensions"]["date"]][key] += group["count"]

    error_minutes = sorted({
        group["dimensions"]["datetimeMinute"]
        for group in groups(zone, since, until, "datetimeMinute", "edgeResponseStatus_geq:500")
    })
    json.dump({
        "host": HOST,
        "since": since.isoformat(),
        "until": until.isoformat(),
        "days": dict(sorted(days.items())),
        "error_minutes": error_minutes,
    }, sys.stdout, indent=2)
    print()


if __name__ == "__main__":
    main()
