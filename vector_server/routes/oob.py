"""OOB URL API — lets external tools create callback URLs and poll for hits."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from config import settings
from correlation import CorrelationEngine
from models import VectorType

router = APIRouter(prefix="/api/oob", tags=["oob"])

engine: CorrelationEngine | None = None


def set_engine(e: CorrelationEngine) -> None:
    global engine
    engine = e


def _require_auth(authorization: str = Header(...)) -> None:
    if authorization != f"Bearer {settings.admin_token}":
        raise HTTPException(status_code=401, detail="Unauthorized")


# --- request / response models ---


class CreateURLRequest(BaseModel):
    label: str = ""
    metadata: dict = Field(default_factory=dict)


class CreateURLResponse(BaseModel):
    token: str
    callback_url: str
    dns_hostname: str
    poll_url: str


class HitEntry(BaseModel):
    protocol: str
    source_ip: str
    raw_data: str
    received_at: float


class PollResponse(BaseModel):
    token: str
    label: str
    hits: list[HitEntry]


# --- routes ---


@router.post("/url", response_model=CreateURLResponse, dependencies=[Depends(_require_auth)])
async def create_url(body: CreateURLRequest) -> CreateURLResponse:
    """Create a new OOB callback URL.  Returns the URL and a poll endpoint."""
    assert engine is not None
    ctx = body.metadata.copy()
    if body.label:
        ctx["label"] = body.label

    meta = engine.register_payload(
        session_id="oob-api",
        vector_type=VectorType.OOB_URL,
        test_case=body.label,
        request_context=ctx,
    )

    callback_url = f"{settings.callback_base}/{meta.token}/oob-url/hook"
    dns_hostname = f"{meta.token}.{settings.interactsh_correlation_id}{settings.interactsh_nonce}.{settings.oob_domain}"

    return CreateURLResponse(
        token=meta.token,
        callback_url=callback_url,
        dns_hostname=dns_hostname,
        poll_url=f"/api/oob/poll/{meta.token}",
    )


@router.get("/poll/{token}", response_model=PollResponse, dependencies=[Depends(_require_auth)])
async def poll_token(token: str) -> PollResponse:
    """Check whether a callback URL has been triggered."""
    assert engine is not None
    meta = engine.get_payload(token)
    if meta is None:
        raise HTTPException(status_code=404, detail="Token not found or expired")

    callbacks = engine.get_callbacks(token)
    hits = [
        HitEntry(
            protocol=cb.protocol,
            source_ip=cb.source_ip,
            raw_data=cb.raw_data,
            received_at=cb.received_at,
        )
        for cb in callbacks
    ]
    return PollResponse(
        token=token,
        label=meta.test_case,
        hits=hits,
    )
