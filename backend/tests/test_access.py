"""Mobile credentials, compatibility settings and rate-limit regression tests."""
import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr, ValidationError
from starlette.requests import Request

from app.access import rate_limit_identity
from app.config import Settings, settings
from app.main import app
from app.routes import limiter


@pytest.fixture(autouse=True)
def access_settings(monkeypatch):
    monkeypatch.setattr(settings, "api_keys", SecretStr("alice:alice-test-key,bob:bob-test-key"))
    limiter.reset()
    yield
    limiter.reset()


class TestAccessConfiguration:
    def test_loads_mobile_settings_from_environment(self, monkeypatch):
        monkeypatch.setenv("API_KEYS", "alice:environment-key")
        monkeypatch.setenv("MAX_QUEUED_DOWNLOADS", "12")
        monkeypatch.setenv("MIN_APP_VERSION", "1.2.3")
        config = Settings(_env_file=None)
        assert config.named_api_keys == {"alice": "environment-key"}
        assert config.max_queued_downloads == 12
        assert config.min_app_version == "1.2.3"
        assert "environment-key" not in repr(config)
        assert "environment-key" not in config.model_dump_json()

    @pytest.mark.parametrize("value", [
        "missing-secret",
        "alice:",
        ":private-secret",
        "alice:private-secret,",
        "alice:private-secret,alice:second-secret",
        "alice:private-secret,bob:private-secret",
    ])
    def test_rejects_malformed_or_duplicate_keys_without_exposing_them(self, value):
        with pytest.raises(ValidationError) as error:
            Settings(_env_file=None, api_keys=value)
        assert "private-secret" not in str(error.value)
        assert "API_KEYS" in str(error.value)

    @pytest.mark.parametrize("overrides", [
        {"max_concurrent_downloads": 0},
        {"max_queued_downloads": -1},
        {"min_app_version": ""},
    ])
    def test_rejects_invalid_mobile_configuration(self, overrides):
        with pytest.raises(ValidationError):
            Settings(_env_file=None, **overrides)


class TestAccessEndpoints:
    async def test_anonymous_site_and_valid_key_are_accepted(self, client):
        for headers in ({}, {"X-Wololo-Key": "alice-test-key"}):
            response = await client.get("/api/health", headers=headers)
            assert response.status_code == 200

    @pytest.mark.parametrize("method,path,payload", [
        ("GET", "/api/health", None),
        ("GET", "/api/jobs", None),
        ("GET", "/api/jobs/unknown", None),
        ("GET", "/api/jobs/unknown/download", None),
        ("GET", "/api/jobs/unknown/progress", None),
        ("DELETE", "/api/jobs/unknown", None),
        ("POST", "/api/download", {"url": "https://youtube.com/watch?v=test123"}),
        ("POST", "/api/validate", {"url": "https://youtube.com/watch?v=test123"}),
        ("POST", "/api/preview", {"url": "https://youtube.com/watch?v=test123"}),
        ("POST", "/api/resolve", {"url": "https://example.com/test"}),
    ])
    async def test_invalid_key_is_rejected_on_api_routes(self, client, method, path, payload):
        response = await client.request(
            method, path, json=payload, headers={"X-Wololo-Key": "unknown-secret"},
        )
        assert response.status_code == 401
        assert response.json() == {"detail": "Invalid access key"}

    async def test_empty_or_revoked_keys_are_rejected(self, client, monkeypatch):
        response = await client.get("/api/health", headers={"X-Wololo-Key": ""})
        assert response.status_code == 401
        monkeypatch.setattr(settings, "api_keys", SecretStr(""))
        response = await client.get("/api/health", headers={"X-Wololo-Key": "alice-test-key"})
        assert response.status_code == 401
        assert (await client.get("/api/health")).status_code == 200

    async def test_health_reports_configured_minimum_version(self, client, monkeypatch):
        monkeypatch.setattr(settings, "min_app_version", "2.3.4")
        response = await client.get("/api/health")
        assert response.json()["min_app_version"] == "2.3.4"


class TestAccessRateLimits:
    async def _exhaust_download_limit(self, client, headers):
        # An unsupported URL exercises the real limiter without launching work.
        for _ in range(10):
            response = await client.post(
                "/api/download", json={"url": "https://example.com/video"}, headers=headers,
            )
            assert response.status_code == 400
        response = await client.post(
            "/api/download", json={"url": "https://example.com/video"}, headers=headers,
        )
        assert response.status_code == 429

    async def test_keys_on_same_ip_have_independent_limits(self, client):
        await self._exhaust_download_limit(client, {"X-Wololo-Key": "alice-test-key"})
        for headers in ({"X-Wololo-Key": "bob-test-key"}, {}):
            response = await client.post(
                "/api/download", json={"url": "https://example.com/video"}, headers=headers,
            )
            assert response.status_code == 400

    async def test_key_limit_follows_key_across_ips(self, client):
        headers = {"X-Wololo-Key": "alice-test-key"}
        await self._exhaust_download_limit(client, headers)
        transport = ASGITransport(app=app, client=("192.0.2.10", 1234))
        async with AsyncClient(transport=transport, base_url="http://test") as other_client:
            response = await other_client.post(
                "/api/download", json={"url": "https://example.com/video"}, headers=headers,
            )
        assert response.status_code == 429

    async def test_anonymous_limit_remains_per_ip(self, client):
        await self._exhaust_download_limit(client, {})
        transport = ASGITransport(app=app, client=("192.0.2.10", 1234))
        async with AsyncClient(transport=transport, base_url="http://test") as other_client:
            response = await other_client.post(
                "/api/download", json={"url": "https://example.com/video"},
            )
        assert response.status_code == 400

    def test_limit_identity_does_not_contain_secret(self):
        request = Request({
            "type": "http",
            "headers": [(b"x-wololo-key", b"alice-test-key")],
            "client": ("127.0.0.1", 1234),
        })
        identity = rate_limit_identity(request)
        assert identity.startswith("key:")
        assert "alice-test-key" not in identity
