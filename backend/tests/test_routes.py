"""Tests for API routes"""
import pytest


class TestHealthEndpoint:
    async def test_health_returns_ok(self, client):
        response = await client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "yt_dlp_version" in data
        assert "active_downloads" in data

    async def test_health_has_version(self, client):
        response = await client.get("/api/health")
        data = response.json()
        assert data["version"] == "1.0.0"


class TestValidateEndpoint:
    async def test_validate_valid_youtube(self, client):
        response = await client.post("/api/validate", json={
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert data["platform"] == "youtube"

    async def test_validate_valid_instagram(self, client):
        response = await client.post("/api/validate", json={
            "url": "https://www.instagram.com/reel/ABC123/"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert data["platform"] == "instagram"

    async def test_validate_invalid_domain(self, client):
        response = await client.post("/api/validate", json={
            "url": "https://evil.com/video"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert data["error"] is not None

    async def test_validate_invalid_url_format(self, client):
        response = await client.post("/api/validate", json={
            "url": "not-a-url"
        })
        assert response.status_code == 422


class TestDownloadEndpoint:
    async def test_download_invalid_url(self, client):
        response = await client.post("/api/download", json={
            "url": "https://evil.com/video",
            "output_format": "video"
        })
        assert response.status_code == 400

    async def test_download_missing_url(self, client):
        response = await client.post("/api/download", json={})
        assert response.status_code == 422

    async def test_download_all_formats_accepted(self, client):
        formats = ["video", "video_webm", "audio_mp3", "audio_m4a", "audio_wav", "audio_flac", "audio_ogg"]
        for fmt in formats:
            response = await client.post("/api/validate", json={
                "url": "https://www.youtube.com/watch?v=test123",
                "output_format": fmt,
            })
            assert response.status_code == 200, f"Format {fmt} should be accepted"


class TestJobEndpoints:
    async def test_get_nonexistent_job(self, client):
        response = await client.get("/api/jobs/nonexistent-id")
        assert response.status_code == 404

    async def test_download_nonexistent_job(self, client):
        response = await client.get("/api/jobs/nonexistent-id/download")
        assert response.status_code == 404

    async def test_list_jobs_empty(self, client):
        response = await client.get("/api/jobs")
        assert response.status_code == 200
        assert response.json() == []

    async def test_list_jobs_with_limit(self, client):
        response = await client.get("/api/jobs?limit=5&offset=0")
        assert response.status_code == 200


class TestRootEndpoint:
    async def test_root_returns_info(self, client):
        response = await client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "version" in data
