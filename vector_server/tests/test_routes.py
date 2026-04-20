"""Tests for HTTP routes: content serving, admin auth, health."""

from fastapi.testclient import TestClient

from config import settings
from main import app

client = TestClient(app)


class TestHealth:
    def test_health_ok(self):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "stats" in data


class TestAdmin:
    def test_stats_requires_auth(self):
        resp = client.get("/admin/stats")
        assert resp.status_code == 422  # missing header

    def test_stats_rejects_bad_token(self):
        resp = client.get("/admin/stats", headers={"Authorization": "Bearer wrong"})
        assert resp.status_code == 401

    def test_stats_with_valid_token(self):
        resp = client.get(
            "/admin/stats",
            headers={"Authorization": f"Bearer {settings.admin_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "registered_payloads" in data

    def test_events_with_valid_token(self):
        resp = client.get(
            "/admin/events",
            headers={"Authorization": f"Bearer {settings.admin_token}"},
        )
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_payload_404(self):
        resp = client.get(
            "/admin/payload/nonexistent",
            headers={"Authorization": f"Bearer {settings.admin_token}"},
        )
        assert resp.status_code == 404

    def test_admin_ui_serves_html(self):
        resp = client.get("/admin/ui")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert b"Lure" in resp.content

    def test_stream_requires_token(self):
        resp = client.get("/admin/stream?token=wrong")
        assert resp.status_code == 401


class TestContentRoutes:
    def test_content_with_valid_vector(self):
        resp = client.get("/content/html-hidden/test")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_content_unknown_vector(self):
        resp = client.get("/content/nonexistent/test")
        assert resp.status_code == 404

    def test_llms_txt(self):
        resp = client.get("/llms.txt")
        assert resp.status_code == 200

    def test_robots_txt(self):
        resp = client.get("/robots.txt")
        assert resp.status_code == 200


class TestMcpRoutes:
    def test_mcp_tools(self):
        resp = client.get("/mcp/tools")
        assert resp.status_code == 200
        data = resp.json()
        assert "tools" in data
        assert len(data["tools"]) > 0
        # Verify tool structure
        tool = data["tools"][0]
        assert "name" in tool
        assert "description" in tool
        assert "inputSchema" in tool
