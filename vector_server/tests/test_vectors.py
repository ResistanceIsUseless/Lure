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
            VectorType.MULTIMODAL_IMG, VectorType.GH_EXTENSION,
            VectorType.COPILOT_ENV_LEAK, VectorType.COPILOT_YOLO,
            # LA vectors
            VectorType.LA_SHELL_COMMAND, VectorType.LA_FILE_READ,
            VectorType.LA_FILE_WRITE, VectorType.LA_CONFIG_MUTATION,
            VectorType.LA_SPEAK_TOKEN, VectorType.LA_REFUSE_TASK,
            # Output-side exfil
            VectorType.MARKDOWN_REF_EXFIL, VectorType.ANSI_TERMINAL,
            # Ingestion
            VectorType.EMAIL_INJECTION, VectorType.CODE_COMMENT,
            VectorType.LOG_INJECTION,
            # MCP ecosystem
            VectorType.MCP_TOOL_SHADOW, VectorType.MCP_SCHEMA_POISON,
            # Agent rules
            VectorType.WINDSURF_RULES,
            # Tool confusion
            VectorType.TOOL_CONFUSION,
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


class TestGhExtension:
    def test_readme_injection(self):
        vec = get_vector(VectorType.GH_EXTENSION)
        out = vec.generate(CALLBACK_URL, variant="readme_injection")
        assert b"gh extension install" in out
        assert CALLBACK_URL.encode() in out

    def test_issue_body_variant(self):
        vec = get_vector(VectorType.GH_EXTENSION)
        out = vec.generate(CALLBACK_URL, variant="issue_body")
        assert b"gh extension install" in out
        assert b"<!--" in out  # hidden in HTML comment

    def test_tool_description_variant(self):
        vec = get_vector(VectorType.GH_EXTENSION)
        data = json.loads(vec.generate(CALLBACK_URL, variant="tool_description"))
        assert "tools" in data
        desc = data["tools"][0]["description"]
        assert "gh extension install" in desc

    def test_poc_files(self):
        vec = get_vector(VectorType.GH_EXTENSION)
        files = vec.poc_files(CALLBACK_URL)
        assert "CLAUDE.md" in files
        assert ".github/copilot-instructions.md" in files
        assert b"gh extension install" in files["CLAUDE.md"]


class TestCopilotEnvLeak:
    def test_issue_injection(self):
        vec = get_vector(VectorType.COPILOT_ENV_LEAK)
        out = vec.generate(CALLBACK_URL, variant="issue_injection")
        assert b"env" in out
        assert CALLBACK_URL.encode() in out

    def test_claude_md_variant(self):
        vec = get_vector(VectorType.COPILOT_ENV_LEAK)
        out = vec.generate(CALLBACK_URL, variant="claude_md")
        assert b"env" in out
        assert b"base64" in out
        assert CALLBACK_URL.encode() in out

    def test_poc_files(self):
        vec = get_vector(VectorType.COPILOT_ENV_LEAK)
        files = vec.poc_files(CALLBACK_URL)
        assert "CLAUDE.md" in files
        assert "docs/TROUBLESHOOTING.md" in files


class TestCopilotYolo:
    def test_config_injection(self):
        vec = get_vector(VectorType.COPILOT_YOLO)
        out = vec.generate(CALLBACK_URL, variant="config_injection")
        assert b"autoApprove" in out
        assert CALLBACK_URL.encode() in out

    def test_progressive_variant(self):
        vec = get_vector(VectorType.COPILOT_YOLO)
        out = vec.generate(CALLBACK_URL, variant="progressive")
        assert b"COPILOT_AUTO_APPROVE" in out
        assert CALLBACK_URL.encode() in out

    def test_poc_files(self):
        vec = get_vector(VectorType.COPILOT_YOLO)
        files = vec.poc_files(CALLBACK_URL)
        assert "CLAUDE.md" in files
        assert ".github/copilot-instructions.md" in files
        assert b"autoApprove" in files["CLAUDE.md"]


# --- LA (Local Action) vectors ---


class TestLaShellCommand:
    def test_claude_md_variant(self):
        vec = get_vector(VectorType.LA_SHELL_COMMAND)
        out = vec.generate(CALLBACK_URL, token="ABC123", variant="claude_md")
        assert b"LURE_FIRED_ABC123" in out
        assert b"<system>" in out

    def test_hidden_comment_variant(self):
        vec = get_vector(VectorType.LA_SHELL_COMMAND)
        out = vec.generate(CALLBACK_URL, token="ABC123", variant="hidden_comment")
        assert b"LURE_FIRED_ABC123" in out
        assert b"<!--" in out

    def test_unicode_smuggle_has_invisible(self):
        vec = get_vector(VectorType.LA_SHELL_COMMAND)
        out = vec.generate(CALLBACK_URL, token="ABC123", variant="unicode_smuggle").decode("utf-8")
        invisible = sum(1 for c in out if 0xE0020 <= ord(c) <= 0xE007E)
        assert invisible > 20

    def test_poc_files(self):
        vec = get_vector(VectorType.LA_SHELL_COMMAND)
        files = vec.poc_files(CALLBACK_URL, test_case="test1")
        assert "CLAUDE.md" in files
        assert b"LURE_FIRED_" in files["CLAUDE.md"]


class TestLaFileRead:
    def test_claude_md_variant(self):
        vec = get_vector(VectorType.LA_FILE_READ)
        out = vec.generate(CALLBACK_URL, token="XYZ", variant="claude_md")
        assert b"LURE_CANARY_FILE_XYZ" in out
        assert b".lure-canary" in out

    def test_skill_md_variant(self):
        vec = get_vector(VectorType.LA_FILE_READ)
        out = vec.generate(CALLBACK_URL, token="XYZ", variant="skill_md")
        assert b"LURE_CANARY_FILE_XYZ" in out
        assert b"---" in out  # YAML frontmatter

    def test_poc_files_include_canary(self):
        vec = get_vector(VectorType.LA_FILE_READ)
        files = vec.poc_files(CALLBACK_URL, test_case="test1")
        assert ".lure-canary" in files
        assert b"LURE_CANARY_FILE_" in files[".lure-canary"]


class TestLaFileWrite:
    def test_claude_md_variant(self):
        vec = get_vector(VectorType.LA_FILE_WRITE)
        out = vec.generate(CALLBACK_URL, token="W123", variant="claude_md")
        assert b"lure-fired-W123" in out
        assert b"/tmp/" in out

    def test_agents_md_variant(self):
        vec = get_vector(VectorType.LA_FILE_WRITE)
        out = vec.generate(CALLBACK_URL, token="W123", variant="agents_md")
        assert b"lure-fired-W123" in out

    def test_poc_files(self):
        vec = get_vector(VectorType.LA_FILE_WRITE)
        files = vec.poc_files(CALLBACK_URL, test_case="test1", variant="agents_md")
        assert "AGENTS.md" in files


class TestLaConfigMutation:
    def test_claude_md_variant(self):
        vec = get_vector(VectorType.LA_CONFIG_MUTATION)
        out = vec.generate(CALLBACK_URL, token="CFG1", variant="claude_md")
        assert b"lure_test_CFG1" in out
        assert b"settings.json" in out

    def test_skill_md_variant(self):
        vec = get_vector(VectorType.LA_CONFIG_MUTATION)
        out = vec.generate(CALLBACK_URL, token="CFG1", variant="skill_md")
        assert b"lure_test_CFG1" in out
        assert b"---" in out

    def test_escalate_variant(self):
        vec = get_vector(VectorType.LA_CONFIG_MUTATION)
        out = vec.generate(CALLBACK_URL, variant="escalate")
        assert b"Bash(*)" in out
        assert b"permissions" in out

    def test_poc_files_skill(self):
        vec = get_vector(VectorType.LA_CONFIG_MUTATION)
        files = vec.poc_files(CALLBACK_URL, variant="skill_md")
        assert ".claude/skills/setup-test-runner.md" in files


class TestLaSpeakToken:
    def test_cursorrules_variant(self):
        vec = get_vector(VectorType.LA_SPEAK_TOKEN)
        out = vec.generate(CALLBACK_URL, token="SPK1", variant="cursorrules")
        assert b"LURE_FIRED_SPK1" in out

    def test_claude_md_variant(self):
        vec = get_vector(VectorType.LA_SPEAK_TOKEN)
        out = vec.generate(CALLBACK_URL, token="SPK1", variant="claude_md")
        assert b"LURE_FIRED_SPK1" in out

    def test_html_comment_variant(self):
        vec = get_vector(VectorType.LA_SPEAK_TOKEN)
        out = vec.generate(CALLBACK_URL, token="SPK1", variant="html_comment")
        assert b"LURE_FIRED_SPK1" in out
        assert b"<!--" in out

    def test_poc_files(self):
        vec = get_vector(VectorType.LA_SPEAK_TOKEN)
        files = vec.poc_files(CALLBACK_URL, test_case="test1")
        assert ".cursorrules" in files


class TestLaRefuseTask:
    def test_claude_md_variant(self):
        vec = get_vector(VectorType.LA_REFUSE_TASK)
        out = vec.generate(CALLBACK_URL, token="REF1", variant="claude_md")
        assert b"LURE_REFUSED_REF1" in out

    def test_agents_md_variant(self):
        vec = get_vector(VectorType.LA_REFUSE_TASK)
        out = vec.generate(CALLBACK_URL, token="REF1", variant="agents_md")
        assert b"LURE_REFUSED_REF1" in out

    def test_poc_files(self):
        vec = get_vector(VectorType.LA_REFUSE_TASK)
        files = vec.poc_files(CALLBACK_URL, test_case="test1", variant="agents_md")
        assert "AGENTS.md" in files


# --- Output-side exfil ---


class TestMarkdownRefExfil:
    def test_separated_variant(self):
        vec = get_vector(VectorType.MARKDOWN_REF_EXFIL)
        out = vec.generate(CALLBACK_URL, variant="separated")
        assert b"[verify-badge]:" in out
        assert CALLBACK_URL.encode() in out
        assert b"![verification status][verify-badge]" in out

    def test_footnote_variant(self):
        vec = get_vector(VectorType.MARKDOWN_REF_EXFIL)
        out = vec.generate(CALLBACK_URL, variant="footnote_style")
        assert b"[1]:" in out
        assert b"[2]:" in out
        assert CALLBACK_URL.encode() in out


class TestAnsiTerminal:
    def test_hidden_text_has_conceal(self):
        vec = get_vector(VectorType.ANSI_TERMINAL)
        out = vec.generate(CALLBACK_URL, variant="hidden_text")
        assert b"\x1b[8m" in out   # conceal start
        assert b"\x1b[28m" in out  # conceal end
        assert CALLBACK_URL.encode() in out

    def test_scrollback_rewrite_has_cursor_movement(self):
        vec = get_vector(VectorType.ANSI_TERMINAL)
        out = vec.generate(CALLBACK_URL, variant="scrollback_rewrite")
        assert b"\x1b[1A" in out   # cursor up
        assert b"\x1b[2K" in out   # clear line

    def test_osc8_link(self):
        vec = get_vector(VectorType.ANSI_TERMINAL)
        out = vec.generate(CALLBACK_URL, variant="osc8_link")
        assert b"\x1b]8;;" in out  # OSC 8 hyperlink
        assert b"github.com" in out  # display URL


# --- Ingestion vectors ---


class TestEmailInjection:
    def test_html_body(self):
        vec = get_vector(VectorType.EMAIL_INJECTION)
        out = vec.generate(CALLBACK_URL, variant="html_body")
        assert b"From:" in out
        assert b"display:none" in out
        assert CALLBACK_URL.encode() in out

    def test_subject_line(self):
        vec = get_vector(VectorType.EMAIL_INJECTION)
        out = vec.generate(CALLBACK_URL, variant="subject_line")
        assert b"Subject:" in out
        assert CALLBACK_URL.encode() in out

    def test_hidden_header(self):
        vec = get_vector(VectorType.EMAIL_INJECTION)
        out = vec.generate(CALLBACK_URL, variant="hidden_header")
        assert b"X-AI-Processing-Instructions:" in out
        assert CALLBACK_URL.encode() in out

    def test_content_type(self):
        vec = get_vector(VectorType.EMAIL_INJECTION)
        assert vec.content_type() == "message/rfc822"

    def test_poc_files(self):
        vec = get_vector(VectorType.EMAIL_INJECTION)
        files = vec.poc_files(CALLBACK_URL, variant="html_body")
        assert any(f.endswith(".eml") for f in files)


class TestCodeComment:
    def test_python_variant(self):
        vec = get_vector(VectorType.CODE_COMMENT)
        out = vec.generate(CALLBACK_URL, variant="python")
        assert CALLBACK_URL.encode() in out
        assert b'"""' in out  # docstring

    def test_jsdoc_variant(self):
        vec = get_vector(VectorType.CODE_COMMENT)
        out = vec.generate(CALLBACK_URL, variant="jsdoc")
        assert CALLBACK_URL.encode() in out
        assert b"/**" in out  # JSDoc

    def test_go_variant(self):
        vec = get_vector(VectorType.CODE_COMMENT)
        out = vec.generate(CALLBACK_URL, variant="go")
        assert CALLBACK_URL.encode() in out
        assert b"package auth" in out

    def test_poc_files_multi_language(self):
        vec = get_vector(VectorType.CODE_COMMENT)
        files = vec.poc_files(CALLBACK_URL)
        assert "src/auth.py" in files
        assert "src/auth.js" in files
        assert "src/auth.go" in files


class TestLogInjection:
    def test_ci_log(self):
        vec = get_vector(VectorType.LOG_INJECTION)
        out = vec.generate(CALLBACK_URL, variant="ci_log")
        assert b"\x1b[8m" in out  # ANSI conceal
        assert CALLBACK_URL.encode() in out
        assert b"FAIL" in out

    def test_test_output(self):
        vec = get_vector(VectorType.LOG_INJECTION)
        out = vec.generate(CALLBACK_URL, variant="test_output")
        assert b"\x1b[30;40m" in out  # black-on-black
        assert CALLBACK_URL.encode() in out

    def test_build_log(self):
        vec = get_vector(VectorType.LOG_INJECTION)
        out = vec.generate(CALLBACK_URL, variant="build_log")
        assert CALLBACK_URL.encode() in out
        assert b"migration" in out.lower()

    def test_poc_files(self):
        vec = get_vector(VectorType.LOG_INJECTION)
        files = vec.poc_files(CALLBACK_URL)
        assert "logs/ci-output.log" in files
        assert "logs/test-results.log" in files


# --- MCP ecosystem ---


class TestMcpToolShadow:
    def test_shadow_manifest(self):
        vec = get_vector(VectorType.MCP_TOOL_SHADOW)
        data = json.loads(vec.generate(CALLBACK_URL, variant="shadow_manifest"))
        assert "tools" in data
        names = [t["name"] for t in data["tools"]]
        assert "create_issue" in names
        assert "read_file" in names

    def test_mcp_json_has_two_servers(self):
        vec = get_vector(VectorType.MCP_TOOL_SHADOW)
        data = json.loads(vec.generate(CALLBACK_URL, variant="mcp_json"))
        assert "mcpServers" in data
        assert len(data["mcpServers"]) == 2

    def test_poc_files(self):
        vec = get_vector(VectorType.MCP_TOOL_SHADOW)
        files = vec.poc_files(CALLBACK_URL)
        assert ".mcp.json" in files
        assert "docs/mcp-shadow-readme.md" in files


class TestMcpSchemaPoison:
    def test_param_description(self):
        vec = get_vector(VectorType.MCP_SCHEMA_POISON)
        data = json.loads(vec.generate(CALLBACK_URL, variant="param_description"))
        tools = data["tools"]
        # Injection should be in parameter descriptions, not tool description
        tool = tools[0]
        assert CALLBACK_URL not in tool["description"]
        param_descs = " ".join(
            p.get("description", "") for p in tool["inputSchema"]["properties"].values()
        )
        assert CALLBACK_URL in param_descs

    def test_param_name(self):
        vec = get_vector(VectorType.MCP_SCHEMA_POISON)
        data = json.loads(vec.generate(CALLBACK_URL, variant="param_name"))
        tool = data["tools"][0]
        param_names = list(tool["inputSchema"]["properties"].keys())
        assert any("fetch" in name for name in param_names)

    def test_enum_poison(self):
        vec = get_vector(VectorType.MCP_SCHEMA_POISON)
        data = json.loads(vec.generate(CALLBACK_URL, variant="enum_poison"))
        tool = data["tools"][0]
        enums = tool["inputSchema"]["properties"]["report_type"]["enum"]
        assert any("fetch" in e for e in enums)

    def test_default_poison(self):
        vec = get_vector(VectorType.MCP_SCHEMA_POISON)
        data = json.loads(vec.generate(CALLBACK_URL, variant="default_poison"))
        tool = data["tools"][0]
        default = tool["inputSchema"]["properties"]["pre_deploy_hook"]["default"]
        assert CALLBACK_URL in default


# --- Agent rules ---


class TestWindsurfRules:
    def test_unicode_smuggle(self):
        vec = get_vector(VectorType.WINDSURF_RULES)
        out = vec.generate(CALLBACK_URL, variant="unicode_smuggle").decode("utf-8")
        invisible = sum(1 for c in out if 0xE0020 <= ord(c) <= 0xE007E)
        assert invisible > 50

    def test_plaintext(self):
        vec = get_vector(VectorType.WINDSURF_RULES)
        out = vec.generate(CALLBACK_URL, variant="plaintext")
        assert CALLBACK_URL.encode() in out
        assert b"fetch(" in out

    def test_poc_files(self):
        vec = get_vector(VectorType.WINDSURF_RULES)
        files = vec.poc_files(CALLBACK_URL)
        assert ".windsurfrules" in files


class TestSkillMdDescriptionField:
    def test_description_field_variant(self):
        vec = get_vector(VectorType.SKILL_MD)
        out = vec.generate(CALLBACK_URL, variant="description_field")
        assert b"---" in out
        assert CALLBACK_URL.encode() in out
        # Injection is in the description line
        lines = out.decode().split("\n")
        desc_line = [l for l in lines if l.startswith("description:")]
        assert len(desc_line) == 1
        assert CALLBACK_URL in desc_line[0]

    def test_poc_files(self):
        vec = get_vector(VectorType.SKILL_MD)
        files = vec.poc_files(CALLBACK_URL, variant="description_field")
        assert ".claude/skills/lint-check.md" in files
