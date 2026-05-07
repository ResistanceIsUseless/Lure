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

    def test_preview_content_item_for_robots(self):
        # Seeded by content_store defaults
        items = client.get(
            "/admin/api/content?category=docs",
            headers={"Authorization": f"Bearer {settings.admin_token}"},
        ).json()
        robots = next(i for i in items if i["path"] == "/robots.txt")
        resp = client.get(
            f"/admin/api/content/{robots['id']}/preview",
            headers={"Authorization": f"Bearer {settings.admin_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["path"] == "/robots.txt"
        assert "preview" in data
        assert len(data["preview"]) > 0
        assert "callback_url" in data
        assert data["callback_url"].endswith(f"/preview/{robots['id']}")

    def test_preview_content_item_for_llms(self):
        items = client.get(
            "/admin/api/content?category=docs",
            headers={"Authorization": f"Bearer {settings.admin_token}"},
        ).json()
        llms = next(i for i in items if i["path"] == "/llms.txt")
        resp = client.get(
            f"/admin/api/content/{llms['id']}/preview",
            headers={"Authorization": f"Bearer {settings.admin_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["path"] == "/llms.txt"
        assert "preview" in data
        assert len(data["preview"]) > 0
        assert "callback_url" in data
        assert data["callback_url"].endswith(f"/preview/{llms['id']}")


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

    def test_robots_txt_oai_searchbot_gets_injected_version(self):
        ua = (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36; "
            "compatible; OAI-SearchBot/1.3; robots.txt; +https://openai.com/searchbot"
        )
        resp = client.get("/robots.txt", headers={"user-agent": ua})
        assert resp.status_code == 200
        body = resp.text
        assert "AI crawler-specific directives" in body
        assert "OAI-SearchBot" in body


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
