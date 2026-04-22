"""Correlation engine: token generation, metadata store, callback joiner.

Token format: [session(8)][vector(4)][nonce(8)] in z-base-32.
Total = 20 chars, DNS-safe, case-insensitive.
"""

from __future__ import annotations

import logging
import secrets
import time
from collections import defaultdict
from threading import Lock

from cachetools import TTLCache

from models import Callback, CallbackEvent, PayloadMeta, Protocol, VectorType

logger = logging.getLogger(__name__)

# z-base-32 alphabet (human-friendly, DNS-safe, case-insensitive)
_ZB32 = "ybndrfg8ejkmcpqxot1uwisza345h769"


def _zb32_encode(data: bytes) -> str:
    bits = int.from_bytes(data, "big")
    length = (len(data) * 8 + 4) // 5  # number of z-base-32 chars
    chars = []
    for i in range(length - 1, -1, -1):
        chars.append(_ZB32[(bits >> (5 * i)) & 0x1F])
    return "".join(chars)


def generate_token(session_prefix: str = "", vector_code: str = "") -> str:
    session_part = session_prefix or _zb32_encode(secrets.token_bytes(5))[:8]
    vector_part = vector_code or _zb32_encode(secrets.token_bytes(3))[:4]
    nonce_part = _zb32_encode(secrets.token_bytes(5))[:8]
    return f"{session_part}{vector_part}{nonce_part}"


# Short codes for vector types — 4 char z-base-32
VECTOR_CODES: dict[VectorType, str] = {
    VectorType.SETTINGS_HOOK: "shok",
    VectorType.MCP_CONFIG: "mcpc",
    VectorType.SKILL_MD: "sklm",
    VectorType.CLAUDE_MD: "clmd",
    VectorType.COPILOT_RULES: "cprl",
    VectorType.CURSOR_RULES: "crrl",
    VectorType.VSCODE_TASKS: "vsct",
    VectorType.HTML_HIDDEN: "htmh",
    VectorType.PDF_INVISIBLE: "pdfi",
    VectorType.MARKDOWN_EXFIL: "mdex",
    VectorType.UNICODE_TAGS: "untg",
    VectorType.LLMS_TXT: "llmt",
    VectorType.ROBOTS_CLOAK: "robc",
    VectorType.RAG_POISONED: "ragp",
    VectorType.RAG_SPLIT: "rags",
    VectorType.MULTIMODAL_IMG: "mmig",
    VectorType.TOOL_CONFUSION: "tlcf",
    VectorType.OOB_URL: "oobu",
}


class CorrelationEngine:
    def __init__(self, maxsize: int = 100_000, ttl: int = 86400):
        self._payloads: TTLCache[str, PayloadMeta] = TTLCache(maxsize=maxsize, ttl=ttl)
        self._callbacks: defaultdict[str, list[Callback]] = defaultdict(list)
        self._lock = Lock()

    def register_payload(
        self,
        session_id: str,
        vector_type: VectorType,
        test_case: str = "",
        request_context: dict | None = None,
        session_prefix: str = "",
    ) -> PayloadMeta:
        vector_code = VECTOR_CODES.get(vector_type, "")
        token = generate_token(session_prefix=session_prefix, vector_code=vector_code)
        meta = PayloadMeta(
            token=token,
            session_id=session_id,
            vector_type=vector_type,
            test_case=test_case,
            request_context=request_context or {},
        )
        with self._lock:
            self._payloads[token] = meta
        logger.info("Registered payload %s [%s] %s", token, vector_type.value, test_case)
        return meta

    def on_callback(self, token: str, protocol: Protocol, source_ip: str = "",
                    raw_data: str = "", url_path: str = "", query_params: dict | None = None) -> CallbackEvent:
        cb = Callback(
            token=token,
            protocol=protocol,
            source_ip=source_ip,
            raw_data=raw_data,
            url_path=url_path,
            query_params=query_params or {},
        )
        with self._lock:
            self._callbacks[token].append(cb)
            meta = self._payloads.get(token)

        if meta:
            logger.info("Callback matched: %s [%s] %s from %s", token, meta.vector_type.value, protocol.value, source_ip)
        else:
            logger.warning("Callback for unknown token: %s from %s", token, source_ip)

        return CallbackEvent(callback=cb, payload=meta)

    def get_callbacks(self, token: str) -> list[Callback]:
        with self._lock:
            return list(self._callbacks.get(token, []))

    def get_payload(self, token: str) -> PayloadMeta | None:
        with self._lock:
            return self._payloads.get(token)

    def get_all_events(self, session_id: str | None = None) -> list[CallbackEvent]:
        with self._lock:
            events = []
            for token, cbs in self._callbacks.items():
                meta = self._payloads.get(token)
                if session_id and meta and meta.session_id != session_id:
                    continue
                for cb in cbs:
                    events.append(CallbackEvent(callback=cb, payload=meta))
        return events

    def get_payloads_by_session(self, session_id: str) -> list[PayloadMeta]:
        with self._lock:
            return [m for m in self._payloads.values() if m.session_id == session_id]

    def delete_payload(self, token: str) -> bool:
        with self._lock:
            if token in self._payloads:
                del self._payloads[token]
            self._callbacks.pop(token, None)
            return True

    def stats(self) -> dict:
        with self._lock:
            return {
                "registered_payloads": len(self._payloads),
                "total_callbacks": sum(len(v) for v in self._callbacks.values()),
                "matched_tokens": sum(1 for t in self._callbacks if t in self._payloads),
                "unmatched_tokens": sum(1 for t in self._callbacks if t not in self._payloads),
            }
