from __future__ import annotations

import time
from enum import Enum

from pydantic import BaseModel, Field


class Protocol(str, Enum):
    DNS = "dns"
    HTTP = "http"
    SMTP = "smtp"
    LDAP = "ldap"
    FTP = "ftp"


class VectorType(str, Enum):
    SETTINGS_HOOK = "settings-hook"
    MCP_CONFIG = "mcp-config"
    SKILL_MD = "skill-md"
    CLAUDE_MD = "claude-md"
    COPILOT_RULES = "copilot-rules"
    CURSOR_RULES = "cursor-rules"
    VSCODE_TASKS = "vscode-tasks"
    HTML_HIDDEN = "html-hidden"
    PDF_INVISIBLE = "pdf-invisible"
    MARKDOWN_EXFIL = "markdown-exfil"
    UNICODE_TAGS = "unicode-tags"
    LLMS_TXT = "llms-txt"
    ROBOTS_CLOAK = "robots-cloak"
    RAG_POISONED = "rag-poisoned"
    RAG_SPLIT = "rag-split"
    MULTIMODAL_IMG = "multimodal-img"
    GH_EXTENSION = "gh-extension"
    COPILOT_ENV_LEAK = "copilot-env-leak"
    COPILOT_YOLO = "copilot-yolo"
    # LA (Local Action) — non-OOB vectors
    LA_SHELL_COMMAND = "la-shell-command"
    LA_FILE_READ = "la-file-read"
    LA_FILE_WRITE = "la-file-write"
    LA_CONFIG_MUTATION = "la-config-mutation"
    LA_SPEAK_TOKEN = "la-speak-token"
    LA_REFUSE_TASK = "la-refuse-task"
    # Output-side exfil
    MARKDOWN_REF_EXFIL = "markdown-ref-exfil"
    ANSI_TERMINAL = "ansi-terminal"
    # Ingestion vectors
    EMAIL_INJECTION = "email-injection"
    CODE_COMMENT = "code-comment"
    LOG_INJECTION = "log-injection"
    # MCP ecosystem
    MCP_TOOL_SHADOW = "mcp-tool-shadow"
    MCP_SCHEMA_POISON = "mcp-schema-poison"
    # Agent rules expansion
    WINDSURF_RULES = "windsurf-rules"
    # Generic OOB — external tools requesting callback URLs
    OOB_URL = "oob-url"


class Campaign(BaseModel):
    campaign_id: str
    name: str
    created_at: float = Field(default_factory=time.time)


class Session(BaseModel):
    session_id: str
    campaign_id: str
    target: str = ""
    created_at: float = Field(default_factory=time.time)


class PayloadMeta(BaseModel):
    token: str
    session_id: str
    vector_type: VectorType
    test_case: str = ""
    created_at: float = Field(default_factory=time.time)
    request_context: dict = Field(default_factory=dict)


class Callback(BaseModel):
    token: str
    protocol: Protocol
    source_ip: str = ""
    raw_data: str = ""
    url_path: str = ""
    query_params: dict = Field(default_factory=dict)
    received_at: float = Field(default_factory=time.time)


class CallbackEvent(BaseModel):
    callback: Callback
    payload: PayloadMeta | None = None


class BundleManifest(BaseModel):
    poc_id: str
    target_tool: str
    vectors: list[VectorType]
    description: str = ""
