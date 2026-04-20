"""Lure vector server — FastAPI entrypoint.

Runs the content/bundle/admin API and a background task that polls
Interactsh for incoming callbacks.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from config import settings
from content_store import ContentStore
from correlation import CorrelationEngine
from interactsh_client import InteractshClient
from models import Protocol
from routes import admin, bundles, content, mcp, site

# Ensure vector modules are imported so they register with the registry
import vectors.agent_config  # noqa: F401
import vectors.claude_hooks  # noqa: F401
import vectors.copilot_vscode  # noqa: F401
import vectors.html  # noqa: F401
import vectors.llms_txt  # noqa: F401
import vectors.markdown  # noqa: F401
import vectors.mcp_config  # noqa: F401
import vectors.multimodal  # noqa: F401
import vectors.pdf  # noqa: F401
import vectors.rag  # noqa: F401
import vectors.robots_txt  # noqa: F401
import vectors.skill_md  # noqa: F401
import vectors.unicode  # noqa: F401

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

engine = CorrelationEngine(maxsize=settings.token_max_size, ttl=settings.token_ttl)
content_store = ContentStore()
content_store.seed_defaults()


@asynccontextmanager
async def lifespan(application: FastAPI):
    client = InteractshClient(settings.interactsh_url, settings.interactsh_token)
    application.state.interactsh = client
    try:
        await client.register()
    except Exception:
        logger.warning("Could not register with Interactsh — polling will retry on first poll")
    poll_task = asyncio.create_task(_poll_loop(client))
    yield
    poll_task.cancel()
    try:
        await poll_task
    except asyncio.CancelledError:
        pass
    await client.close()


app = FastAPI(title="Lure Vector Server", version="0.1.0", lifespan=lifespan)

# Wire engine + content store into route modules
admin.set_engine(engine)
admin.set_store(content_store)
content.set_engine(engine)
bundles.set_engine(engine)
mcp.set_engine(engine)
site.set_engine(engine)
site.set_store(content_store)

app.include_router(admin.router)
app.include_router(content.router)
app.include_router(bundles.router)
app.include_router(mcp.router)
app.include_router(site.router)


async def _poll_loop(client: InteractshClient) -> None:
    while True:
        try:
            events = await client.poll()
            for event in events:
                _ingest_interactsh_event(event)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Interactsh poll error")
        await asyncio.sleep(settings.interactsh_poll_interval)


def _ingest_interactsh_event(event: dict) -> None:
    """Parse an Interactsh interaction record and feed it to the correlation engine."""
    unique_id = event.get("unique-id", "")
    # Interactsh unique-id contains our correlation token as a prefix of the subdomain
    # Format: <token>.<random>.oob.example.com or just the subdomain portion
    token = unique_id.split(".")[0] if "." in unique_id else unique_id

    proto_str = event.get("protocol", "dns").lower()
    try:
        protocol = Protocol(proto_str)
    except ValueError:
        protocol = Protocol.HTTP

    raw = event.get("raw-request", "") or event.get("raw-response", "")
    source_ip = event.get("remote-address", "")

    cb_event = engine.on_callback(
        token=token,
        protocol=protocol,
        source_ip=source_ip,
        raw_data=raw,
        url_path=event.get("full-url", ""),
        query_params={},
    )
    # Push to SSE subscribers for live admin UI
    admin.broadcast_event(cb_event)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "stats": engine.stats()}
