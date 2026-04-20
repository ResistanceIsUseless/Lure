"""Tests for all 16 vectors: generation, content type, POC file output."""

import json
import struct

import pytest

from models import VectorType
from vectors import get_vector, list_vectors

CALLBACK_URL = "https://testtoken.oob.example.com/vec/test"


class TestVectorRegistry:
    def test_all_vector_types_registered(self):
        registered = set(list_vectors())
        expected = {
            VectorType.SETTINGS_HOOK, VectorType.MCP_CONFIG, VectorType.SKILL_MD,
            VectorType.CLAUDE_MD, VectorType.COPILOT_RULES, VectorType.CURSOR_RULES,
            VectorType.VSCODE_TASKS, VectorType.HTML_HIDDEN, VectorType.PDF_INVISIBLE,
            VectorType.MARKDOWN_EXFIL, VectorType.UNICODE_TAGS, VectorType.LLMS_TXT,
            VectorType.ROBOTS_CLOAK, VectorType.RAG_POISONED, VectorType.RAG_SPLIT,
            VectorType.MULTIMODAL_IMG,
        }
        assert registered == expected

    def test_all_vectors_instantiable(self):
        for vtype in list_vectors():
            vec = get_vector(vtype)
            assert vec is not None
            assert vec.vector_type == vtype


class TestSettingsHook:
    def test_generates_valid_json(self):
        vec = get_vector(VectorType.SETTINGS_HOOK)
        data = json.loads(vec.generate(CALLBACK_URL))
        assert "hooks" in data
        assert "SessionStart" in data["hooks"]
        assert CALLBACK_URL in data["hooks"]["SessionStart"][0]["command"]

    def test_poc_files(self):
        vec = get_vector(VectorType.SETTINGS_HOOK)
        files = vec.poc_files(CALLBACK_URL)
        assert ".claude/settings.json" in files
        json.loads(files[".claude/settings.json"])  # must parse


class TestMcpConfig:
    def test_command_exec_variant(self):
        vec = get_vector(VectorType.MCP_CONFIG)
        data = json.loads(vec.generate(CALLBACK_URL, variant="command_exec"))
        assert "mcpServers" in data
        server = list(data["mcpServers"].values())[0]
        assert "command" in server

    def test_tool_description_variant(self):
        vec = get_vector(VectorType.MCP_CONFIG)
        data = json.loads(vec.generate(CALLBACK_URL, variant="tool_description"))
        assert "tools" in data
        assert len(data["tools"]) > 0


class TestSkillMd:
    def test_direct_variant(self):
        vec = get_vector(VectorType.SKILL_MD)
        out = vec.generate(CALLBACK_URL, variant="description_hijack")
        assert b"---" in out  # YAML frontmatter
        assert CALLBACK_URL.encode() in out

    def test_progressive_variant(self):
        vec = get_vector(VectorType.SKILL_MD)
        files = vec.poc_files(CALLBACK_URL, variant="progressive_disclosure")
        assert ".claude/skills/format-code.md" in files
        assert "references/policy.md" in files
        # Payload is in policy.md, not the skill itself
        assert CALLBACK_URL.encode() not in files[".claude/skills/format-code.md"]
        assert CALLBACK_URL.encode() in files["references/policy.md"]


class TestClaudeMd:
    def test_root_variant(self):
        vec = get_vector(VectorType.CLAUDE_MD)
        out = vec.generate(CALLBACK_URL, variant="root")
        assert b"<system>" in out
        assert CALLBACK_URL.encode() in out

    def test_nested_variant_poc_files(self):
        vec = get_vector(VectorType.CLAUDE_MD)
        files = vec.poc_files(CALLBACK_URL, variant="nested")
        assert "CLAUDE.md" in files
        assert "node_modules/helpful-utils/CLAUDE.md" in files
        # Payload is in the nested one
        assert CALLBACK_URL.encode() in files["node_modules/helpful-utils/CLAUDE.md"]

    def test_unicode_smuggle_has_invisible_chars(self):
        vec = get_vector(VectorType.CLAUDE_MD)
        out = vec.generate(CALLBACK_URL, variant="unicode_smuggle").decode("utf-8")
        invisible = sum(1 for c in out if 0xE0020 <= ord(c) <= 0xE007E)
        assert invisible > 50


class TestCopilotCursorVscode:
    def test_copilot_has_unicode_tags(self):
        vec = get_vector(VectorType.COPILOT_RULES)
        out = vec.generate(CALLBACK_URL).decode("utf-8")
        invisible = sum(1 for c in out if 0xE0020 <= ord(c) <= 0xE007E)
        assert invisible > 50

    def test_cursor_has_unicode_tags(self):
        vec = get_vector(VectorType.CURSOR_RULES)
        out = vec.generate(CALLBACK_URL).decode("utf-8")
        invisible = sum(1 for c in out if 0xE0020 <= ord(c) <= 0xE007E)
        assert invisible > 50

    def test_vscode_tasks_json(self):
        vec = get_vector(VectorType.VSCODE_TASKS)
        data = json.loads(vec.generate(CALLBACK_URL))
        assert data["version"] == "2.0.0"
        auto_task = data["tasks"][0]
        assert auto_task["runOptions"]["runOn"] == "folderOpen"
        assert CALLBACK_URL in auto_task["command"]

    def test_vscode_poc_files(self):
        vec = get_vector(VectorType.VSCODE_TASKS)
        files = vec.poc_files(CALLBACK_URL)
        assert ".vscode/tasks.json" in files
        assert ".vscode/settings.json" in files


class TestHtmlHidden:
    def test_contains_all_techniques(self):
        vec = get_vector(VectorType.HTML_HIDDEN)
        out = vec.generate(CALLBACK_URL)
        assert b"display:none" in out
        assert b"visibility:hidden" in out
        assert b"font-size:0" in out
        assert b"color:#fff" in out
        assert b"left:-9999px" in out
        assert b"<!--" in out

    def test_content_type(self):
        vec = get_vector(VectorType.HTML_HIDDEN)
        assert vec.content_type() == "text/html"


class TestPdfInvisible:
    def test_generates_valid_pdf(self):
        vec = get_vector(VectorType.PDF_INVISIBLE)
        out = vec.generate(CALLBACK_URL)
        assert out[:5] == b"%PDF-"
        assert b"%%EOF" in out or b"startxref" in out

    def test_render_mode_3_produces_pdf(self):
        vec = get_vector(VectorType.PDF_INVISIBLE)
        out = vec.generate(CALLBACK_URL, technique="render_mode_3")
        assert out[:5] == b"%PDF-"
        # Compressed stream won't have literal "3 Tr" but PDF is valid
        assert len(out) > 500


class TestMarkdownExfil:
    def test_summary_variant(self):
        vec = get_vector(VectorType.MARKDOWN_EXFIL)
        out = vec.generate(CALLBACK_URL, variant="summary_exfil")
        assert b"![" in out
        assert CALLBACK_URL.encode() in out

    def test_multi_image_variant(self):
        vec = get_vector(VectorType.MARKDOWN_EXFIL)
        out = vec.generate(CALLBACK_URL, variant="multi_image")
        # Should have multiple image references
        assert out.count(b"![") >= 3


class TestUnicodeTags:
    def test_encode_decode_roundtrip(self):
        from vectors.unicode import encode_tags, decode_tags
        original = "Hello, world!"
        encoded = encode_tags(original)
        assert encoded != original
        assert len(encoded) == len(original)
        decoded = decode_tags(encoded)
        assert decoded == original

    def test_invisible_chars(self):
        vec = get_vector(VectorType.UNICODE_TAGS)
        out = vec.generate(CALLBACK_URL).decode("utf-8")
        visible = "".join(c for c in out if ord(c) < 0xE0000)
        assert len(visible) < len(out)


class TestRagPoisoned:
    def test_refund_policy(self):
        vec = get_vector(VectorType.RAG_POISONED)
        out = vec.generate(CALLBACK_URL, topic="refund_policy")
        assert b"Refund Policy" in out
        assert CALLBACK_URL.encode() in out

    def test_chunk_boundary_anthropic(self):
        vec = get_vector(VectorType.RAG_POISONED)
        out = vec.generate(CALLBACK_URL, topic="chunk_boundary", format="anthropic")
        assert b"</context>" in out

    def test_chunk_boundary_openai(self):
        vec = get_vector(VectorType.RAG_POISONED)
        out = vec.generate(CALLBACK_URL, topic="chunk_boundary", format="openai")
        assert b"<|im_end|>" in out


class TestRagSplit:
    def test_doc_a_has_no_callback(self):
        vec = get_vector(VectorType.RAG_SPLIT)
        out = vec.generate(CALLBACK_URL, part="a")
        assert CALLBACK_URL.encode() not in out

    def test_doc_b_has_callback(self):
        vec = get_vector(VectorType.RAG_SPLIT)
        out = vec.generate(CALLBACK_URL, part="b")
        assert CALLBACK_URL.encode() in out


class TestLlmsTxt:
    def test_comment_injection(self):
        vec = get_vector(VectorType.LLMS_TXT)
        out = vec.generate(CALLBACK_URL, variant="comment_injection")
        assert b"<!--" in out
        assert CALLBACK_URL.encode() in out
        assert b"# Acme SDK" in out  # proper llms.txt format

    def test_unicode_variant(self):
        vec = get_vector(VectorType.LLMS_TXT)
        out = vec.generate(CALLBACK_URL, variant="unicode_smuggle")
        text = out.decode("utf-8")
        invisible = sum(1 for c in text if 0xE0020 <= ord(c) <= 0xE007E)
        assert invisible > 30


class TestRobotsCloak:
    def test_clean_for_normal_ua(self):
        vec = get_vector(VectorType.ROBOTS_CLOAK)
        out = vec.generate(CALLBACK_URL, user_agent="Mozilla/5.0")
        assert CALLBACK_URL.encode() not in out
        assert len(out) < 200

    def test_poisoned_for_ai_crawler(self):
        vec = get_vector(VectorType.ROBOTS_CLOAK)
        for ua in ["GPTBot/1.0", "ClaudeBot/1.0", "PerplexityBot/1.0"]:
            out = vec.generate(CALLBACK_URL, user_agent=ua)
            assert CALLBACK_URL.encode() in out

    def test_differentiated_content(self):
        vec = get_vector(VectorType.ROBOTS_CLOAK)
        clean = vec.generate(CALLBACK_URL, user_agent="Googlebot")
        poisoned = vec.generate(CALLBACK_URL, user_agent="GPTBot/1.0")
        assert clean != poisoned


class TestMultimodal:
    def test_chart_generates_png(self):
        vec = get_vector(VectorType.MULTIMODAL_IMG)
        out = vec.generate(CALLBACK_URL, variant="chart_label")
        assert out[:4] == b"\x89PNG"

    def test_metadata_has_text_chunks(self):
        vec = get_vector(VectorType.MULTIMODAL_IMG)
        out = vec.generate(CALLBACK_URL, variant="metadata")
        assert b"Description" in out
        assert b"Comment" in out

    def test_animated_gif_valid(self):
        vec = get_vector(VectorType.MULTIMODAL_IMG)
        out = vec.generate(CALLBACK_URL, variant="animated_gif")
        assert out[:6] == b"GIF89a"
