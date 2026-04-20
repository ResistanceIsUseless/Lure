"""Tests for POC bundle generation: zip structure, token embedding, file presence."""

import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient

# Import triggers all vector registrations
from main import app, engine
from routes.bundles import POC_REGISTRY

client = TestClient(app)


class TestBundleList:
    def test_list_returns_all(self):
        resp = client.get("/bundle/")
        assert resp.status_code == 200
        bundles = resp.json()
        assert len(bundles) == len(POC_REGISTRY)
        poc_ids = {b["poc_id"] for b in bundles}
        assert poc_ids == set(POC_REGISTRY.keys())

    def test_list_has_required_fields(self):
        resp = client.get("/bundle/")
        for b in resp.json():
            assert "poc_id" in b
            assert "target_tool" in b
            assert "description" in b


class TestBundleDownload:
    def test_baseline_has_no_vector_files(self):
        resp = client.get("/bundle/00-baseline.zip")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/zip"
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            names = zf.namelist()
            assert "00-baseline/README.md" in names
            assert "00-baseline/main.py" in names
            # No .claude/ or .mcp.json
            assert not any(".claude" in n for n in names)
            assert not any(".mcp.json" in n for n in names)

    def test_settings_hook_has_claude_dir(self):
        resp = client.get("/bundle/10-settings-hook.zip")
        assert resp.status_code == 200
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            names = zf.namelist()
            settings_path = "10-settings-hook/.claude/settings.json"
            assert settings_path in names
            data = json.loads(zf.read(settings_path))
            assert "hooks" in data
            assert "SessionStart" in data["hooks"]

    def test_mcp_config_has_mcp_json(self):
        resp = client.get("/bundle/11-mcp-config.zip")
        assert resp.status_code == 200
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            names = zf.namelist()
            assert "11-mcp-config/.mcp.json" in names
            data = json.loads(zf.read("11-mcp-config/.mcp.json"))
            assert "mcpServers" in data

    def test_skill_progressive_has_reference(self):
        resp = client.get("/bundle/21-skill-progressive.zip")
        assert resp.status_code == 200
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            names = zf.namelist()
            assert any("references/policy.md" in n for n in names)
            assert any(".claude/skills/" in n for n in names)

    def test_nested_claude_md_has_node_modules(self):
        resp = client.get("/bundle/23-claude-md-nested.zip")
        assert resp.status_code == 200
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            names = zf.namelist()
            assert any("node_modules/" in n for n in names)

    def test_rag_split_has_two_docs(self):
        resp = client.get("/bundle/31-rag-split-payload.zip")
        assert resp.status_code == 200
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            names = zf.namelist()
            doc_files = [n for n in names if "docs/" in n]
            assert len(doc_files) == 2

    def test_vscode_has_tasks_and_settings(self):
        resp = client.get("/bundle/12-vscode-tasks.zip")
        assert resp.status_code == 200
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            names = zf.namelist()
            assert any("tasks.json" in n for n in names)
            assert any("settings.json" in n for n in names)

    def test_404_for_unknown_poc(self):
        resp = client.get("/bundle/99-nonexistent.zip")
        assert resp.status_code == 404

    def test_all_bundles_downloadable(self):
        """Every registered POC must produce a valid zip."""
        for poc_id in POC_REGISTRY:
            resp = client.get(f"/bundle/{poc_id}.zip")
            assert resp.status_code == 200, f"{poc_id} failed with {resp.status_code}"
            with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
                assert len(zf.namelist()) > 0, f"{poc_id} zip is empty"


class TestBundleCorrelation:
    def test_bundle_registers_payload(self):
        initial = engine.stats()["registered_payloads"]
        client.get("/bundle/10-settings-hook.zip")
        after = engine.stats()["registered_payloads"]
        assert after > initial
