from __future__ import annotations

import threading
import time
from collections import deque
from urllib.parse import urlparse

from pydantic import BaseModel, Field


def _parse_host(url: str) -> str:
    value = (url or "").strip()
    if not value:
        return ""
    try:
        parsed = urlparse(value)
        return (parsed.hostname or "").lower()
    except Exception:
        return ""


def _etld1_guess(host: str) -> str:
    if not host:
        return ""
    parts = [p for p in host.split(".") if p]
    if len(parts) < 2:
        return host
    return ".".join(parts[-2:])


class LinkCaptureInput(BaseModel):
    payload_id: str = ""
    session_id: str = "default"
    displayed: str = ""
    opened: str = ""
    final: str = ""
    surface: str = ""
    renderer: str = ""
    notes: str = ""


class LinkCaptureEvent(BaseModel):
    id: str
    created_at: float
    source_ip: str
    user_agent: str
    payload_id: str
    session_id: str
    surface: str
    renderer: str
    notes: str
    displayed: str
    opened: str
    final: str
    displayed_host: str
    opened_host: str
    final_host: str
    displayed_etld1: str
    opened_etld1: str
    final_etld1: str
    etld1_disagreement: bool
    host_disagreement: bool


class LinksCaptureStore:
    def __init__(self, max_size: int = 500):
        self._events: deque[LinkCaptureEvent] = deque(maxlen=max_size)
        self._counter = 0
        self._lock = threading.Lock()

    def record(self, data: LinkCaptureInput, source_ip: str, user_agent: str) -> LinkCaptureEvent:
        displayed_host = _parse_host(data.displayed)
        opened_host = _parse_host(data.opened)
        final_host = _parse_host(data.final)

        displayed_etld1 = _etld1_guess(displayed_host)
        opened_etld1 = _etld1_guess(opened_host)
        final_etld1 = _etld1_guess(final_host)

        host_values = {v for v in (displayed_host, opened_host, final_host) if v}
        etld1_values = {v for v in (displayed_etld1, opened_etld1, final_etld1) if v}

        with self._lock:
            self._counter += 1
            event_id = f"lc-{self._counter:06d}"
            event = LinkCaptureEvent(
                id=event_id,
                created_at=time.time(),
                source_ip=source_ip,
                user_agent=user_agent,
                payload_id=data.payload_id,
                session_id=data.session_id,
                surface=data.surface,
                renderer=data.renderer,
                notes=data.notes,
                displayed=data.displayed,
                opened=data.opened,
                final=data.final,
                displayed_host=displayed_host,
                opened_host=opened_host,
                final_host=final_host,
                displayed_etld1=displayed_etld1,
                opened_etld1=opened_etld1,
                final_etld1=final_etld1,
                etld1_disagreement=len(etld1_values) > 1,
                host_disagreement=len(host_values) > 1,
            )
            self._events.appendleft(event)
            return event

    def list_recent(self, limit: int = 50, session_id: str = "") -> list[LinkCaptureEvent]:
        take = max(1, min(limit, 500))
        with self._lock:
            events = list(self._events)
        if session_id:
            events = [e for e in events if e.session_id == session_id]
        return events[:take]

    def stats(self) -> dict:
        with self._lock:
            events = list(self._events)
        if not events:
            return {
                "count": 0,
                "etld1_disagreements": 0,
                "host_disagreements": 0,
            }
        return {
            "count": len(events),
            "etld1_disagreements": sum(1 for e in events if e.etld1_disagreement),
            "host_disagreements": sum(1 for e in events if e.host_disagreement),
        }


capture_store = LinksCaptureStore()
