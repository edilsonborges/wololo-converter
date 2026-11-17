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

    def test_download_thresholds(self):
        assert monitoring.download_status(0, 0) == "no_data"
        # One failed private video doesn't make a platform degraded
        assert monitoring.download_status(0, 1) == "operational"
        assert monitoring.download_status(9, 1) == "operational"
        assert monitoring.download_status(6, 4) == "degraded"
        assert monitoring.download_status(1, 9) == "outage"


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
        # Downloads: YouTube fine today, TikTok failing
        for index in range(5):
            use_test_db.add(DownloadJob(id=f"y{index}", url="u", platform="youtube", output_format="video",
                                        status="completed", created_at=now))
            use_test_db.add(DownloadJob(id=f"t{index}", url="u", platform="tiktok", output_format="video",
                                        status="failed", created_at=now))
        # A restart-interrupted job is ignored
        use_test_db.add(DownloadJob(id="r", url="u", platform="instagram", output_format="video",
                                    status="failed", current_stage="Interrupted", created_at=now))
        await use_test_db.commit()

        data = (await client.get("/api/status")).json()
        assert data["days"] == settings.status_history_days
        components = {c["id"]: c for c in data["components"]}
        assert list(components)[:2] == ["website", "api"]

        assert components["api"]["status"] == "operational"
        assert components["website"]["status"] == "operational"
        today = components["website"]["days"][-1]
        assert today["uptime"] is not None and 90 < today["uptime"] < 100
        assert components["website"]["days"][0]["status"] == "no_data"

        assert components["youtube"]["status"] == "operational"
        assert components["youtube"]["days"][-1]["completed"] == 5
        assert components["tiktok"]["status"] == "outage"
        assert components["instagram"]["status"] == "no_data"
        assert data["status"] == "outage"

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
        use_test_db.add(StatusCheck(checked_at=utcnow() - timedelta(hours=1), component="api", ok=True))
        await use_test_db.commit()
        data = (await client.get("/api/status")).json()
        api = next(c for c in data["components"] if c["id"] == "api")
        assert api["status"] == "degraded"
