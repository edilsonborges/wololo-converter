"""Status page: probes, daily uptime and per-platform download health."""
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

import httpx
import pytest

from app import monitoring
from app.config import settings
from app.models import DownloadJob, StatusCheck, SystemSample, utcnow


class TestClassification:
    def test_uptime_thresholds(self):
        assert monitoring.uptime_status(None) == "no_data"
        assert monitoring.uptime_status(100) == "operational"
        assert monitoring.uptime_status(99.0) == "operational"
        assert monitoring.uptime_status(97) == "degraded"
        assert monitoring.uptime_status(50) == "outage"



@pytest.fixture
def use_test_db(db_session, monkeypatch):
    @asynccontextmanager
    async def ctx():
        yield db_session
        await db_session.commit()

    monkeypatch.setattr(monitoring, "get_db_context", ctx)
    monitoring._status_cache.update(at=0.0, value=None)
    return db_session


class TestChecks:
    async def test_run_checks_stores_probes_and_sample(self, use_test_db, monkeypatch, tmp_path):
        monkeypatch.setattr(settings, "temp_dir", tmp_path)

        def handler(request):
            return httpx.Response(200, text='<html><div id="root"></div></html>')

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await monitoring.run_checks(client)

        from sqlalchemy import select
        checks = (await use_test_db.execute(select(StatusCheck))).scalars().all()
        assert {(c.component, c.ok) for c in checks} == {("website", True), ("api", True)}
        samples = (await use_test_db.execute(select(SystemSample))).scalars().all()
        assert len(samples) == 1

    async def test_website_down(self, monkeypatch):
        def handler(request):
            return httpx.Response(502, text="Bad gateway")

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            ok, _, detail = await monitoring.probe_website(client)
        assert ok is False
        assert detail == "HTTP 502"


class TestStatus:
    async def test_status_endpoint_with_history(self, client, use_test_db):
        now = utcnow()
        # Probes every minute for the last 30 minutes, two of them failed
        for minute in range(30):
            at = now - timedelta(minutes=minute)
            use_test_db.add(StatusCheck(checked_at=at, component="website", ok=minute not in (5, 6)))
            use_test_db.add(StatusCheck(checked_at=at, component="api", ok=True))
        use_test_db.add(DownloadJob(id="t1", url="u", platform="tiktok", output_format="video",
                                    status="failed", created_at=now))
        await use_test_db.commit()

        data = (await client.get("/api/status")).json()
        assert data["days"] == settings.status_history_days
        # Only the website is public: no API or per-platform components
        assert [c["id"] for c in data["components"]] == ["website"]
        website = data["components"][0]
        assert website["status"] == "operational"
        today = website["days"][-1]
        assert today["uptime"] is not None and 90 < today["uptime"] < 100
        assert website["days"][0]["status"] == "no_data"
        assert data["status"] == "operational"

    async def test_missing_probe_counts_as_down(self, use_test_db):
        now = utcnow().replace(hour=12, minute=0, second=0, microsecond=0)
        # Monitoring started 10 minutes before "now" but only 5 probes arrived
        for minute in range(0, 10, 2):
            use_test_db.add(StatusCheck(checked_at=now - timedelta(minutes=10 - minute), component="api", ok=True))
        await use_test_db.commit()
        days = [now.date()]
        result = await monitoring.probe_component_days(use_test_db, days, now)
        assert result["api"][0]["uptime"] == 50.0
        assert result["api"][0]["status"] == "outage"

    async def test_stale_probe_is_degraded(self, client, use_test_db):
        use_test_db.add(StatusCheck(checked_at=utcnow() - timedelta(hours=1), component="website", ok=True))
        await use_test_db.commit()
        data = (await client.get("/api/status")).json()
        assert data["components"][0]["status"] == "degraded"


class TestBackfill:
    LOG = [
        "2026-10-16T12:09:54Z INF Starting tunnel tunnelID=x",
        "2026-10-16T12:09:56Z INF Registered tunnel connection connIndex=0",
        "2026-10-16T13:00:00Z ERR Request failed error=\"Unable to reach the origin service.\" dest=https://api.edilson.dev/x",
        "2026-10-17T10:00:00Z ERR Request failed error=\"stream 1 canceled by remote\" dest=https://wololo.edilson.dev/api/jobs/1/download",
        "2026-10-18T03:04:32Z INF Retrying connection",
        "2026-10-18T04:30:59Z INF Starting tunnel tunnelID=x",
        "2026-10-18T04:31:04Z INF Registered tunnel connection connIndex=0",
        "2026-10-19T08:00:10Z ERR Request failed error=\"Unable to reach the origin service.\" dest=https://wololo.edilson.dev/",
        "2026-10-19T08:00:40Z ERR Request failed error=\"Unable to reach the origin service.\" dest=https://wololo.edilson.dev/api",
        "2026-10-20T09:00:00Z INF Registered tunnel connection connIndex=1",
    ]

    def test_tunnel_evidence(self):
        from datetime import date
        from app.backfill import TunnelEvidence

        evidence = TunnelEvidence(self.LOG)
        assert evidence.covers(date(2026, 10, 16)) and not evidence.covers(date(2026, 10, 21))
        # Other services' failures don't count against Wololo
        assert evidence.downtime(date(2026, 10, 16)) == (0.0, [])
        minutes, reasons = evidence.downtime(date(2026, 10, 18))
        assert round(minutes) == 87  # 03:04:32 -> 04:31:04
        assert "tunnel restart" in reasons[0]
        minutes, reasons = evidence.downtime(date(2026, 10, 19))
        assert minutes == 1  # two failures in the same minute
        assert evidence.requests_seen[date(2026, 10, 17)] == 1

    def test_estimates(self):
        from datetime import date, timedelta
        from app.backfill import TunnelEvidence, estimate_days

        evidence = TunnelEvidence(self.LOG)
        days = [date(2026, 10, 10) + timedelta(days=n) for n in range(10)]
        result = estimate_days(days, evidence, {date(2026, 10, 12): 3, date(2026, 10, 17): 2})
        # Before the tunnel log: only days with downloads, without an uptime figure
        assert result[date(2026, 10, 12)] == (
            "operational", None, "Before monitoring: 3 download requests answered this day",
        )
        assert date(2026, 10, 11) not in result
        assert result[date(2026, 10, 17)][:2] == ("operational", 100.0)
        assert result[date(2026, 10, 17)][2].startswith("Estimated from tunnel log: no unanswered requests")
        assert "2 download requests answered" in result[date(2026, 10, 17)][2]
        assert result[date(2026, 10, 18)][0] == "outage"  # 94% < 95%
        assert result[date(2026, 10, 18)][1] == round(100 - (86 + 32 / 60) * 100 / 1440, 2)

    async def test_status_uses_estimates_before_monitoring(self, client, use_test_db):
        from app.models import StatusBackfill

        now = utcnow()
        yesterday = (now - timedelta(days=1)).date().isoformat()
        use_test_db.add(StatusCheck(checked_at=now - timedelta(minutes=1), component="website", ok=True))
        use_test_db.add(StatusBackfill(day=yesterday, component="website", status="operational",
                                       uptime=None, note="Before monitoring: 2 download requests answered this day"))
        await use_test_db.commit()
        data = (await client.get("/api/status")).json()
        day = data["components"][0]["days"][-2]
        assert day["estimated"] is True
        assert day["status"] == "operational"
        assert day["note"].startswith("Before monitoring")


def test_cloudflare_evidence_counts_5xx_minutes():
    from datetime import date
    from app.backfill import CloudflareEvidence, TunnelEvidence, estimate_days

    cloudflare = CloudflareEvidence({
        "since": "2026-10-18T04:28:00+00:00",
        "until": "2026-11-17T04:23:00+00:00",
        "days": {"2026-10-18": {"ok": 110, "client_errors": 0, "server_errors": 0},
                 "2026-10-19": {"ok": 20, "client_errors": 10, "server_errors": 30}},
        "error_minutes": ["2026-10-19T08:00:00Z", "2026-10-19T08:01:00Z", "2026-10-19T08:02:00Z"],
    })
    tunnel = TunnelEvidence(["2026-10-16T12:09:54Z INF Starting tunnel", "2026-10-25T00:00:00Z INF x"])
    result = estimate_days(
        [date(2026, 10, 17), date(2026, 10, 18), date(2026, 10, 19), date(2026, 12, 1)],
        tunnel, {date(2026, 10, 18): 4}, cloudflare,
    )
    assert result[date(2026, 10, 17)][2] == "Estimated from tunnel log: no unanswered requests"
    assert result[date(2026, 10, 18)] == (
        "operational", 100.0,
        "Estimated from Cloudflare: ~110 requests answered, no server errors; "
        "tunnel log: no unanswered requests; 4 download requests answered",
    )
    status, uptime, note = result[date(2026, 10, 19)]
    assert uptime == round(100 - 3 * 100 / 1440, 2)
    assert "5xx errors in 3 min" in note
    assert date(2026, 12, 1) not in result
