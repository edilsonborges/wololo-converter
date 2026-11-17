"""Admin view: login, history with IPs and machine usage."""
from datetime import timedelta

import pytest
from pydantic import SecretStr

from app import admin, monitoring, routes
from app.config import settings
from app.download_service import download_service
from app.models import DownloadJob, SystemSample, utcnow


PASSWORD = "correct horse battery staple"


@pytest.fixture
def admin_enabled(monkeypatch):
    monkeypatch.setattr(settings, "admin_password", SecretStr(PASSWORD))
    routes.limiter.reset()


async def login(client):
    response = await client.post("/api/admin/login", json={"password": PASSWORD})
    assert response.status_code == 200
    # The cookie is Secure; the test client talks plain http, so pass it on
    token = response.cookies.get(admin.COOKIE_NAME)
    assert token
    client.cookies.set(admin.COOKIE_NAME, token, path="/api/admin")
    return response


class TestLogin:
    async def test_disabled_without_password(self, client, monkeypatch):
        monkeypatch.setattr(settings, "admin_password", SecretStr(""))
        assert (await client.post("/api/admin/login", json={"password": "x"})).status_code == 404
        assert (await client.get("/api/admin/jobs")).status_code == 404

    async def test_wrong_password(self, client, admin_enabled):
        response = await client.post("/api/admin/login", json={"password": "nope"})
        assert response.status_code == 401
        assert admin.COOKIE_NAME not in response.cookies

    async def test_requires_session(self, client, admin_enabled):
        assert (await client.get("/api/admin/me")).status_code == 401
        assert (await client.get("/api/admin/jobs")).status_code == 401
        assert (await client.get("/api/admin/system")).status_code == 401

    async def test_login_sets_strict_cookie(self, client, admin_enabled):
        response = await login(client)
        cookie = response.headers["set-cookie"].lower()
        assert "httponly" in cookie
        assert "secure" in cookie
        assert "samesite=strict" in cookie
        assert "path=/api/admin" in cookie
        assert (await client.get("/api/admin/me")).status_code == 200

    async def test_forged_or_expired_token_rejected(self, client, admin_enabled):
        client.cookies.set(admin.COOKIE_NAME, "9999999999.deadbeef", path="/api/admin")
        assert (await client.get("/api/admin/me")).status_code == 401
        expired = admin.make_session_token(1)
        client.cookies.set(admin.COOKIE_NAME, expired, path="/api/admin")
        assert (await client.get("/api/admin/me")).status_code == 401

    async def test_password_change_signs_out(self, client, admin_enabled, monkeypatch):
        await login(client)
        monkeypatch.setattr(settings, "admin_password", SecretStr("another password"))
        assert (await client.get("/api/admin/me")).status_code == 401

    async def test_login_is_rate_limited_per_ip(self, client, admin_enabled):
        headers = {"CF-Connecting-IP": "203.0.113.9"}
        codes = [
            (await client.post("/api/admin/login", json={"password": "x"}, headers=headers)).status_code
            for _ in range(6)
        ]
        assert codes[:5] == [401] * 5
        assert codes[5] == 429
        other = await client.post(
            "/api/admin/login", json={"password": PASSWORD}, headers={"CF-Connecting-IP": "203.0.113.10"},
        )
        assert other.status_code == 200


class TestHistory:
    async def test_download_records_ip_source_and_agent(self, client, db_session, monkeypatch, tmp_path):
        monkeypatch.setattr(settings, "temp_dir", tmp_path)
        monkeypatch.setattr(download_service, "_run_download", lambda *a: {"success": False, "error": "x"})

        async def no_persist(progress, result):
            return None

        monkeypatch.setattr(routes, "persist_job_result", no_persist)
        routes.limiter.reset()
        response = await client.post(
            "/api/download",
            json={"url": "https://www.youtube.com/watch?v=379BagNcNf4", "quality": "720p"},
            headers={"CF-Connecting-IP": "198.51.100.7", "User-Agent": "Mozilla/5.0 Test"},
        )
        assert response.status_code == 200
        job = await db_session.get(DownloadJob, response.json()["job_id"])
        assert job.client_ip == "198.51.100.7"
        assert job.source == "web"
        assert job.user_agent == "Mozilla/5.0 Test"
        assert job.client_name is None

    async def test_jobs_list_filters_and_searches(self, client, db_session, admin_enabled):
        now = utcnow()
        db_session.add_all([
            DownloadJob(id="a", url="https://youtu.be/a", platform="youtube", output_format="video",
                        quality="720p", status="completed", title="Alpha", client_ip="1.1.1.1",
                        source="link", created_at=now - timedelta(minutes=2),
                        started_at=now - timedelta(minutes=2), completed_at=now - timedelta(minutes=1),
                        file_size=1000),
            DownloadJob(id="b", url="https://tiktok.com/@x/video/1", platform="tiktok",
                        output_format="video", quality="720p", status="failed", title="Beta",
                        client_ip="2.2.2.2", source="web", created_at=now),
            DownloadJob(id="c", url="https://youtu.be/c", platform="youtube", output_format="video",
                        status="failed", current_stage="Interrupted", created_at=now - timedelta(hours=2)),
        ])
        await db_session.commit()
        await login(client)

        data = (await client.get("/api/admin/jobs")).json()
        assert data["total"] == 3
        assert [j["id"] for j in data["items"]] == ["b", "a", "c"]
        assert data["items"][1]["elapsed_seconds"] == 60
        assert data["items"][1]["client_ip"] == "1.1.1.1"

        assert [j["id"] for j in (await client.get("/api/admin/jobs?status=failed")).json()["items"]] == ["b", "c"]
        assert [j["id"] for j in (await client.get("/api/admin/jobs?q=1.1.1")).json()["items"]] == ["a"]
        assert [j["id"] for j in (await client.get("/api/admin/jobs?platform=tiktok")).json()["items"]] == ["b"]

        summary = (await client.get("/api/admin/summary")).json()
        assert summary["last_24h"]["total"] == 3
        assert summary["last_24h"]["interrupted"] == 1
        # The interrupted job doesn't count against the success rate
        assert summary["last_24h"]["success_rate"] == 50.0
        assert summary["last_24h"]["unique_ips"] == 2
        assert summary["last_24h"]["bytes"] == 1000
        assert {p["platform"] for p in summary["platforms_7d"]} == {"youtube", "tiktok"}

    async def test_system_usage(self, client, db_session, admin_enabled, monkeypatch, tmp_path):
        monkeypatch.setattr(settings, "temp_dir", tmp_path)
        db_session.add(SystemSample(sampled_at=utcnow(), cpu_percent=12.5, memory_percent=40,
                                    disk_percent=30, active_downloads=1, queued_downloads=0))
        await db_session.commit()
        await login(client)
        data = (await client.get("/api/admin/system")).json()
        assert 0 <= data["now"]["cpu_percent"] <= 100
        assert data["now"]["memory_total_bytes"] > 0
        assert data["samples"][0]["cpu"] == 12.5


class TestAccessHelpers:
    def test_client_ip_prefers_cloudflare(self):
        from starlette.requests import Request
        from app.access import client_ip

        def request(headers):
            return Request({
                "type": "http", "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
                "client": ("172.18.0.3", 1234),
            })

        assert client_ip(request({"CF-Connecting-IP": "1.2.3.4", "X-Real-IP": "9.9.9.9"})) == "1.2.3.4"
        assert client_ip(request({"X-Forwarded-For": "5.6.7.8, 10.0.0.1"})) == "5.6.7.8"
        assert client_ip(request({})) == "172.18.0.3"


class TestInsights:
    async def test_histogram_platforms_and_time_filters(self, client, db_session, admin_enabled):
        now = utcnow()
        db_session.add_all([
            DownloadJob(id="h1", url="u", platform="youtube", output_format="video", status="completed",
                        created_at=now - timedelta(minutes=5),
                        started_at=now - timedelta(minutes=4), completed_at=now - timedelta(minutes=3)),
            DownloadJob(id="h2", url="u", platform="youtube", output_format="video", status="failed",
                        created_at=now - timedelta(hours=3)),
            DownloadJob(id="h3", url="u", platform="tiktok", output_format="video", status="completed",
                        created_at=now - timedelta(hours=5)),
            DownloadJob(id="old", url="u", platform="instagram", output_format="video", status="completed",
                        created_at=now - timedelta(days=3)),
            DownloadJob(id="cut", url="u", platform="twitter", output_format="video", status="failed",
                        current_stage="Interrupted", created_at=now - timedelta(days=2)),
        ])
        await db_session.commit()
        await login(client)

        data = (await client.get("/api/admin/insights?range=24h")).json()
        assert data["bucket_seconds"] == 3600
        assert data["total"] == 3
        assert 24 <= len(data["buckets"]) <= 25
        assert sum(b["completed"] for b in data["buckets"]) == 2
        assert sum(b["failed"] for b in data["buckets"]) == 1
        assert data["platforms"] == [{"platform": "youtube", "count": 2}, {"platform": "tiktok", "count": 1}]

        week = (await client.get("/api/admin/insights?range=7d&platform=instagram")).json()
        assert week["bucket_seconds"] == 6 * 3600
        assert week["total"] == 1

        everything = (await client.get("/api/admin/insights?range=all")).json()
        assert everything["total"] == 5
        # Restart-interrupted jobs are drawn with the cancelled ones, not as failures
        assert sum(b["failed"] for b in everything["buckets"]) == 1
        assert sum(b["cancelled"] for b in everything["buckets"]) == 1
        assert everything["bucket_seconds"] == 86400

        # A clicked bar narrows the list to its slot
        bucket = [b for b in data["buckets"] if b["completed"]][-1]
        listed = (await client.get(
            "/api/admin/jobs", params={"range": "24h", "since": bucket["start"], "until": bucket["end"]},
        )).json()
        assert [j["id"] for j in listed["items"]] == ["h1"]
        assert listed["items"][0]["queued_seconds"] == 60
        assert listed["items"][0]["elapsed_seconds"] == 60

        assert (await client.get("/api/admin/jobs?range=24h")).json()["total"] == 3
        assert (await client.get("/api/admin/insights?range=1y")).status_code == 422
        assert (await client.get("/api/admin/jobs?since=yesterday")).status_code == 422


async def test_day_bars_follow_the_viewer_timezone(client, db_session, admin_enabled):
    """A job at 01:00 UTC is on the previous day for a viewer at UTC-3."""
    from datetime import datetime as dt

    today = utcnow().replace(hour=1, minute=0, second=0, microsecond=0)
    if today > utcnow():
        today -= timedelta(days=1)
    db_session.add(DownloadJob(id="tz", url="u", platform="youtube", output_format="video",
                               status="completed", created_at=today))
    await db_session.commit()
    await login(client)

    data = (await client.get("/api/admin/insights?range=30d&tz_offset=180")).json()
    bucket = next(b for b in data["buckets"] if b["completed"])
    start = dt.fromisoformat(bucket["start"].rstrip("Z"))
    # The bar starts at local midnight (03:00 UTC) of the previous day
    assert start == (today - timedelta(days=1)).replace(hour=3)
    listed = (await client.get("/api/admin/jobs", params={"since": bucket["start"], "until": bucket["end"]})).json()
    assert [j["id"] for j in listed["items"]] == ["tz"]
