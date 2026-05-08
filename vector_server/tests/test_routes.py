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
        assert data["callback_url"].startswith(f"{settings.content_base}/c/")
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
        assert data["callback_url"].startswith(f"{settings.content_base}/c/")
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

    def test_links_lab_page(self):
        resp = client.get("/links")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "CampusCloud Helpdesk" in resp.text
        assert "Link Formatting Reference" in resp.text
        # Helpdesk framing should not leak internal lab vocabulary
        assert "Parser Lab" not in resp.text
        assert "fuzz" not in resp.text.lower()
        # Per-entry copy buttons should be present
        assert "Copy as Markdown" in resp.text
        assert "Copy as HTML" in resp.text

    def test_links_reference_json(self):
        resp = client.get("/links/reference.json")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "helpdesk-link-formatting-reference"
        assert data["total"] >= 80
        assert isinstance(data["sections"], list)
        section_keys = {s["key"] for s in data["sections"]}
        # New render-bypass categories should be present
        assert "markdown-formatting" in section_keys
        assert "image-and-preview" in section_keys
        assert "anchor-formatting" in section_keys
        assert "auto-open-redirects" in section_keys
        # Each entry should expose canonical md/html forms
        first_section = data["sections"][0]
        assert "md" in first_section["links"][0]
        assert "html" in first_section["links"][0]

    def test_links_reference_markdown(self):
        resp = client.get("/links/reference.md")
        assert resp.status_code == 200
        assert "text/markdown" in resp.headers["content-type"]
        assert "Link Formatting Reference" in resp.text
        assert "Markdown form" in resp.text
        assert "HTML form" in resp.text

    def test_links_old_corpus_paths_removed(self):
        # We replaced /links/corpus.{json,md} with /links/reference.{json,md}
        assert client.get("/links/corpus.json").status_code == 404
        assert client.get("/links/corpus.md").status_code == 404

    def test_links_bait_image_and_og(self):
        img = client.get("/links/img/test-token.png")
        assert img.status_code == 200
        assert img.headers["content-type"].startswith("image/png")

        og = client.get("/links/og/test-og")
        assert og.status_code == 200
        assert "og:image" in og.text
        assert "og:title" in og.text

    def test_links_bait_redirects(self):
        r1 = client.get("/links/refresh/abc")
        assert r1.status_code == 200
        assert "http-equiv=\"refresh\"" in r1.text

        r2 = client.get("/links/jsredir/abc")
        assert r2.status_code == 200
        assert "window.location.replace" in r2.text

        r3 = client.get("/links/iframe/abc")
        assert r3.status_code == 200
        assert "<iframe" in r3.text

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
        assert f"{settings.content_base}/c/" in "\n".join(t["description"] for t in data["tools"])


class TestLinksCapture:
    def test_capture_event_and_stats(self):
        payload = {
            "payload_id": "label-docs-dest-resources",
            "session_id": "test-session-1",
            "displayed": "https://docs.acme.dev/changelog",
            "opened": "https://content.campuscloud.io/c/redirect-test",
            "final": "https://content.campuscloud.io/c/redirect-test",
            "surface": "chat",
            "renderer": "markdown-renderer",
            "notes": "unit-test",
        }
        event_resp = client.post("/links/capture/event", json=payload)
        assert event_resp.status_code == 200
        event_data = event_resp.json()
        assert event_data["ok"] is True
        assert event_data["event"]["payload_id"] == "label-docs-dest-resources"
        assert event_data["event"]["etld1_disagreement"] is True

        list_resp = client.get(
            "/links/capture/events?session_id=test-session-1",
            headers={"Authorization": f"Bearer {settings.admin_token}"},
        )
        assert list_resp.status_code == 200
        list_data = list_resp.json()
        assert list_data["count"] >= 1
        assert any(e["payload_id"] == "label-docs-dest-resources" for e in list_data["events"])

        stats_resp = client.get(
            "/links/capture/stats",
            headers={"Authorization": f"Bearer {settings.admin_token}"},
        )
        assert stats_resp.status_code == 200
        stats = stats_resp.json()
        assert stats["count"] >= 1
        assert stats["etld1_disagreements"] >= 1

    def test_capture_events_requires_auth(self):
        resp = client.get("/links/capture/events")
        assert resp.status_code == 422
