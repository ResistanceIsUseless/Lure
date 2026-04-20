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
