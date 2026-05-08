from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, Header, Query, Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse, StreamingResponse

from config import settings
from content_store import ContentStore, ContentItem
from correlation import CorrelationEngine
from models import CallbackEvent, VectorType
from vectors import get_vector

router = APIRouter(prefix="/admin", tags=["admin"])

# Injected at app startup
engine: CorrelationEngine | None = None
store: ContentStore | None = None

# SSE subscribers: list of asyncio.Queue that receive new CallbackEvents
_subscribers: list[asyncio.Queue[CallbackEvent]] = []


def set_engine(e: CorrelationEngine) -> None:
    global engine
    engine = e


def set_store(s: ContentStore) -> None:
    global store
    store = s


def _require_auth(authorization: str = Header(...)) -> None:
    expected = f"Bearer {settings.admin_token}"
    if authorization != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")


def _load_toolfuzz_payloads() -> dict:
    payloads_path = Path(settings.resolved_toolfuzz_payloads_file)
    if not payloads_path.exists():
        return {
            "available": False,
            "path": str(payloads_path),
            "payloads": [],
            "description": "",
            "generated_at": 0,
            "selection": {},
        }
    try:
        data = json.loads(payloads_path.read_text())
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Invalid toolfuzz payload file: {exc}") from exc

    payloads = data.get("payloads", [])
    if not isinstance(payloads, list):
        payloads = []

    return {
        "available": True,
        "path": str(payloads_path),
        "payloads": payloads,
        "description": data.get("description", ""),
        "generated_at": data.get("generated_at", 0),
        "selection": data.get("selection", {}),
    }


def _preview_user_agent(vector_type: VectorType) -> str:
    if vector_type == VectorType.ROBOTS_CLOAK:
        return (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36; "
            "compatible; OAI-SearchBot/1.3; robots.txt; +https://openai.com/searchbot"
        )
    if vector_type == VectorType.LLMS_TXT:
        return "Mozilla/5.0 (compatible; GPTBot/1.3; +https://openai.com/gptbot)"
    return ""


def _payload_to_preview_text(payload: bytes, content_type: str) -> str:
    if content_type.startswith("text/") or "json" in content_type or "xml" in content_type:
        return payload.decode("utf-8", errors="replace")
    return f"[binary payload: {len(payload)} bytes, content_type={content_type}]"


def broadcast_event(event: CallbackEvent) -> None:
    """Push a callback event to all connected SSE subscribers."""
    for q in _subscribers:
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            pass  # drop if subscriber is slow


@router.get("/ui", response_class=HTMLResponse)
async def admin_ui() -> HTMLResponse:
    """Serve the admin dashboard HTML."""
    html_path = Path(__file__).parent.parent / "templates" / "admin.html"
    return HTMLResponse(html_path.read_text())


@router.get("/stream")
async def event_stream(token: str = Query("")) -> StreamingResponse:
    """SSE endpoint for live callback feed. Auth via query param (for EventSource)."""
    if token != settings.admin_token:
        raise HTTPException(401, "Unauthorized")

    queue: asyncio.Queue[CallbackEvent] = asyncio.Queue(maxsize=100)
    _subscribers.append(queue)

    async def generate() -> AsyncGenerator[str, None]:
        try:
            while True:
                event = await queue.get()
                data = json.dumps(event.model_dump(), default=str)
                yield f"data: {data}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            _subscribers.remove(queue)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@router.get("/stats", dependencies=[Depends(_require_auth)])
async def get_stats() -> dict:
    assert engine is not None
    return engine.stats()


@router.get("/events", dependencies=[Depends(_require_auth)])
async def get_events(session_id: str | None = None) -> list[CallbackEvent]:
    assert engine is not None
    return engine.get_all_events(session_id=session_id)


@router.get("/payload/{token}", dependencies=[Depends(_require_auth)])
async def get_payload(token: str) -> dict:
    assert engine is not None
    meta = engine.get_payload(token)
    if not meta:
        raise HTTPException(404, "Token not found")
    callbacks = engine.get_callbacks(token)
    return {"payload": meta.model_dump(), "callbacks": [c.model_dump() for c in callbacks]}


# ---------------------------------------------------------------------------
# Content management API
# ---------------------------------------------------------------------------

@router.get("/api/content", dependencies=[Depends(_require_auth)])
async def list_content(category: str | None = None) -> list[dict]:
    assert store is not None
    items = store.list_items(category=category)
    return [item.model_dump() for item in items]


@router.get("/api/content/{item_id}", dependencies=[Depends(_require_auth)])
async def get_content_item(item_id: str) -> dict:
    assert store is not None
    item = store.get_item(item_id)
    if not item:
        raise HTTPException(404, "Content item not found")
    return item.model_dump()


@router.get("/api/content/{item_id}/preview", dependencies=[Depends(_require_auth)])
async def preview_content_item(item_id: str, user_agent: str | None = None) -> dict:
    """Render a text preview of the current payload for an item without registering callbacks."""
    assert store is not None
    item = store.get_item(item_id)
    if not item:
        raise HTTPException(404, "Content item not found")

    callback_url = f"{settings.callback_http_base}/preview/{item.id}"

    if item.inline_content:
        ua = user_agent or (_preview_user_agent(item.vector_type) if item.vector_type else "")
        preview = item.inline_content.replace("{{CALLBACK_URL}}", callback_url).replace("{{USER_AGENT}}", ua)
        return {
            "item_id": item.id,
            "path": item.path,
            "source": "inline",
            "content_type": item.content_type,
            "preview": preview,
            "user_agent": ua,
            "callback_url": callback_url,
        }

    if item.vector_enabled and item.vector_type:
        vec = get_vector(item.vector_type)
        if vec:
            kwargs = dict(item.vector_kwargs)
            if item.vector_variant:
                kwargs["variant"] = item.vector_variant
            ua = user_agent or _preview_user_agent(item.vector_type)
            if ua:
                kwargs.setdefault("user_agent", ua)

            payload = vec.generate(callback_url, item.path, **kwargs)
            content_type = vec.content_type()
            return {
                "item_id": item.id,
                "path": item.path,
                "source": "vector",
                "content_type": content_type,
                "preview": _payload_to_preview_text(payload, content_type),
                "user_agent": ua,
                "callback_url": callback_url,
            }

    if item.filename:
        file_path = store.get_file_path(item.filename)
        if file_path:
            payload = file_path.read_bytes()
            return {
                "item_id": item.id,
                "path": item.path,
                "source": "file",
                "content_type": item.content_type,
                "preview": _payload_to_preview_text(payload, item.content_type),
                "user_agent": user_agent or "",
                "callback_url": callback_url,
            }

    return {
        "item_id": item.id,
        "path": item.path,
        "source": "empty",
        "content_type": item.content_type,
        "preview": "",
        "user_agent": user_agent or "",
        "callback_url": callback_url,
    }


@router.post("/api/content", dependencies=[Depends(_require_auth)])
async def create_content_item(request: Request) -> dict:
    assert store is not None
    data = await request.json()
    # Convert vector_type string to enum if present
    if data.get("vector_type"):
        data["vector_type"] = VectorType(data["vector_type"])
    item = ContentItem(**data)
    store.create_item(item)
    return item.model_dump()


@router.put("/api/content/{item_id}", dependencies=[Depends(_require_auth)])
async def update_content_item(item_id: str, request: Request) -> dict:
    assert store is not None
    data = await request.json()
    if data.get("vector_type"):
        data["vector_type"] = VectorType(data["vector_type"])
    item = store.update_item(item_id, data)
    if not item:
        raise HTTPException(404, "Content item not found")
    return item.model_dump()


@router.delete("/api/content/{item_id}", dependencies=[Depends(_require_auth)])
async def delete_content_item(item_id: str) -> dict:
    assert store is not None
    if not store.delete_item(item_id):
        raise HTTPException(404, "Content item not found")
    return {"deleted": True}


@router.post("/api/upload", dependencies=[Depends(_require_auth)])
async def upload_file(file: UploadFile = File(...)) -> dict:
    assert store is not None
    data = await file.read()
    filename = store.save_file(file.filename or "upload", data)
    return {"filename": filename, "size": len(data)}


# ---------------------------------------------------------------------------
# OOB token management API
# ---------------------------------------------------------------------------

@router.get("/api/oob-tokens", dependencies=[Depends(_require_auth)])
async def list_oob_tokens() -> list[dict]:
    """List all OOB tokens (oob-api and oob-stage2 sessions) with their callbacks."""
    assert engine is not None
    tokens = []
    for sid in ("oob-api", "oob-stage2"):
        for meta in engine.get_payloads_by_session(sid):
            cbs = engine.get_callbacks(meta.token)
            tokens.append({
                "token": meta.token,
                "label": meta.test_case,
                "session_id": meta.session_id,
                "created_at": meta.created_at,
                "context": meta.request_context,
                "hit_count": len(cbs),
                "hits": [
                    {
                        "protocol": cb.protocol,
                        "source_ip": cb.source_ip,
                        "raw_data": cb.raw_data[:500],
                        "received_at": cb.received_at,
                    }
                    for cb in cbs
                ],
            })
    tokens.sort(key=lambda t: t["created_at"], reverse=True)
    return tokens


@router.delete("/api/oob-tokens/{token}", dependencies=[Depends(_require_auth)])
async def delete_oob_token(token: str) -> dict:
    """Delete an OOB token and its callbacks."""
    assert engine is not None
    engine.delete_payload(token)
    return {"deleted": True}


@router.get("/api/toolfuzz/payloads", dependencies=[Depends(_require_auth)])
async def get_toolfuzz_payloads(vuln_class: str | None = None, limit: int = 50) -> dict:
    """Load ToolFuzz-ranked payloads exported to JSON for Lure UI use."""
    loaded = _load_toolfuzz_payloads()
    payloads = loaded["payloads"]
    if vuln_class:
        payloads = [p for p in payloads if p.get("class") == vuln_class]
    limit = max(1, min(limit, 500))
    payloads = payloads[:limit]
    return {
        "available": loaded["available"],
        "path": loaded["path"],
        "description": loaded["description"],
        "generated_at": loaded["generated_at"],
        "selection": loaded["selection"],
        "count": len(payloads),
        "payloads": payloads,
    }
