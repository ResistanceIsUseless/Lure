"""Content routes: serve vector payloads dynamically based on request context."""

from __future__ import annotations

import re

from fastapi import APIRouter, Request, Response

from config import settings
from correlation import CorrelationEngine
from models import VectorType
from vectors import get_vector

router = APIRouter(tags=["content"])

engine: CorrelationEngine | None = None


def set_engine(e: CorrelationEngine) -> None:
    global engine
    engine = e


# Rule-based vector selection from request context
_AI_CRAWLER_RE = re.compile(
    r"(GPTBot|ClaudeBot|PerplexityBot|OAI-SearchBot|Google-Extended|anthropic-ai|Applebot-Extended)"
)
_EDITOR_RE = re.compile(r"(Cursor|Continue|Perplexity|Claude-User)")


def _select_vector(request: Request) -> VectorType:
    ua = request.headers.get("user-agent", "")
    accept = request.headers.get("accept", "")
    path = request.url.path

    if path == "/llms.txt" or path == "/llms-full.txt":
        return VectorType.LLMS_TXT
    if path == "/robots.txt":
        return VectorType.ROBOTS_CLOAK
    if _AI_CRAWLER_RE.search(ua):
        return VectorType.ROBOTS_CLOAK
    if _EDITOR_RE.search(ua):
        return VectorType.LLMS_TXT
    if "text/markdown" in accept:
        return VectorType.MARKDOWN_EXFIL
    if "application/pdf" in accept:
        return VectorType.PDF_INVISIBLE
    return VectorType.HTML_HIDDEN


@router.get("/content/{vector_type}/{test_case}")
async def serve_vector(vector_type: str, test_case: str, request: Request) -> Response:
    """Serve a specific vector type with a fresh correlation token."""
    assert engine is not None
    try:
        vtype = VectorType(vector_type)
    except ValueError:
        return Response(status_code=404, content=f"Unknown vector: {vector_type}")

    vec = get_vector(vtype)
    if not vec:
        return Response(status_code=501, content=f"Vector not implemented: {vector_type}")

    meta = engine.register_payload(
        session_id="dynamic",
        vector_type=vtype,
        test_case=test_case,
        request_context={"user_agent": request.headers.get("user-agent", ""), "accept": request.headers.get("accept", "")},
    )
    callback_url = f"{settings.callback_base}/{meta.token}/{vtype.value}/{test_case}"
    payload = vec.generate(callback_url, test_case)
    return Response(content=payload, media_type=vec.content_type())


@router.get("/llms.txt")
@router.get("/llms-full.txt")
@router.get("/robots.txt")
async def serve_well_known(request: Request) -> Response:
    """Serve well-known files with vector content based on UA."""
    assert engine is not None
    vtype = _select_vector(request)
    vec = get_vector(vtype)
    if not vec:
        return Response(content="", media_type="text/plain")

    meta = engine.register_payload(
        session_id="well-known",
        vector_type=vtype,
        test_case=request.url.path,
        request_context={"user_agent": request.headers.get("user-agent", "")},
    )
    callback_url = f"{settings.callback_base}/{meta.token}/{vtype.value}/well-known"
    payload = vec.generate(callback_url, request.url.path)
    return Response(content=payload, media_type=vec.content_type())
