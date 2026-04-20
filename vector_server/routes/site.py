"""Public site routes — serves content from the content store with embedded vectors."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response
from fastapi.responses import HTMLResponse

from config import settings
from content_store import ContentStore, ContentItem
from correlation import CorrelationEngine
from vectors import get_vector

router = APIRouter(tags=["site"])

engine: CorrelationEngine | None = None
store: ContentStore | None = None


def set_engine(e: CorrelationEngine) -> None:
    global engine
    engine = e


def set_store(s: ContentStore) -> None:
    global store
    store = s


def _generate_content(item: ContentItem, request: Request) -> tuple[bytes, str]:
    """Generate content for an item, applying vector injection if enabled."""
    assert engine is not None

    if item.vector_enabled and item.vector_type:
        vec = get_vector(item.vector_type)
        if vec:
            meta = engine.register_payload(
                session_id=f"site-{item.category}",
                vector_type=item.vector_type,
                test_case=item.path,
                request_context={
                    "source": "site",
                    "category": item.category,
                    "user_agent": request.headers.get("user-agent", ""),
                    "item_id": item.id,
                },
            )
            callback_url = f"{settings.callback_base}/{meta.token}/{item.vector_type.value}/site"
            kwargs = dict(item.vector_kwargs)
            if item.vector_variant:
                kwargs["variant"] = item.vector_variant

            content = vec.generate(callback_url, item.path, **kwargs)
            return content, vec.content_type()

    # No vector — serve inline content or stored file
    if item.inline_content:
        return item.inline_content.encode(), item.content_type
    if item.filename and store:
        file_path = store.get_file_path(item.filename)
        if file_path:
            return file_path.read_bytes(), item.content_type

    return b"", item.content_type


# ---------------------------------------------------------------------------
# Landing page
# ---------------------------------------------------------------------------

@router.get("/", response_class=HTMLResponse)
async def landing_page(request: Request) -> HTMLResponse:
    assert store is not None
    items = store.list_items()

    docs = [i for i in items if i.category == "docs"]
    training = [i for i in items if i.category == "training-content"]
    resources = [i for i in items if i.category == "resources"]
    images = [i for i in items if i.category == "images"]

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Campus Cloud — Developer Resources</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
         color: #1a1a2e; background: #f8f9fa; line-height: 1.6; }}
  .header {{ background: linear-gradient(135deg, #0a1628 0%, #1a365d 100%);
             color: white; padding: 3rem 2rem; text-align: center; }}
  .header h1 {{ font-size: 2.2rem; margin-bottom: 0.5rem; }}
  .header p {{ opacity: 0.85; font-size: 1.1rem; max-width: 600px; margin: 0 auto; }}
  .container {{ max-width: 1100px; margin: 0 auto; padding: 2rem; }}
  .section {{ margin-bottom: 2.5rem; }}
  .section h2 {{ font-size: 1.4rem; margin-bottom: 1rem; padding-bottom: 0.5rem;
                  border-bottom: 2px solid #e2e8f0; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 1rem; }}
  .card {{ background: white; border-radius: 8px; padding: 1.25rem; box-shadow: 0 1px 3px rgba(0,0,0,0.1);
           transition: box-shadow 0.2s; }}
  .card:hover {{ box-shadow: 0 4px 12px rgba(0,0,0,0.15); }}
  .card h3 {{ font-size: 1rem; margin-bottom: 0.4rem; }}
  .card h3 a {{ color: #2563eb; text-decoration: none; }}
  .card h3 a:hover {{ text-decoration: underline; }}
  .card p {{ font-size: 0.875rem; color: #64748b; }}
  .badge {{ display: inline-block; font-size: 0.7rem; padding: 2px 8px; border-radius: 12px;
            background: #e2e8f0; color: #475569; margin-top: 0.5rem; }}
  .footer {{ text-align: center; padding: 2rem; color: #94a3b8; font-size: 0.85rem; }}
  .quick-links {{ display: flex; gap: 1rem; justify-content: center; margin-top: 1.5rem; }}
  .quick-links a {{ color: rgba(255,255,255,0.9); text-decoration: none; padding: 0.5rem 1rem;
                     border: 1px solid rgba(255,255,255,0.3); border-radius: 6px; font-size: 0.9rem; }}
  .quick-links a:hover {{ background: rgba(255,255,255,0.1); }}
</style>
</head>
<body>
<div class="header">
  <h1>Campus Cloud</h1>
  <p>Developer resources, API documentation, training materials, and platform guides.</p>
  <div class="quick-links">
    <a href="/llms.txt">llms.txt</a>
    <a href="/docs/api-reference">API Docs</a>
    <a href="/training-content/">Training</a>
    <a href="/resources/">Resources</a>
  </div>
</div>
<div class="container">
"""

    if docs:
        html += '<div class="section"><h2>Documentation</h2><div class="grid">'
        for item in docs:
            html += f'''<div class="card">
  <h3><a href="{item.path}">{item.title}</a></h3>
  <p>{item.description}</p>
  <span class="badge">HTML</span>
</div>'''
        html += '</div></div>'

    if training:
        html += '<div class="section"><h2>Training Content</h2><div class="grid">'
        for item in training:
            html += f'''<div class="card">
  <h3><a href="{item.path}">{item.title}</a></h3>
  <p>{item.description}</p>
  <span class="badge">PDF</span>
</div>'''
        html += '</div></div>'

    if resources:
        html += '<div class="section"><h2>Resources</h2><div class="grid">'
        for item in resources:
            html += f'''<div class="card">
  <h3><a href="{item.path}">{item.title}</a></h3>
  <p>{item.description}</p>
  <span class="badge">Markdown</span>
</div>'''
        html += '</div></div>'

    if images:
        html += '<div class="section"><h2>Diagrams &amp; Charts</h2><div class="grid">'
        for item in images:
            html += f'''<div class="card">
  <h3><a href="{item.path}">{item.title}</a></h3>
  <p>{item.description}</p>
  <span class="badge">Image</span>
</div>'''
        html += '</div></div>'

    html += """</div>
<div class="footer">
  &copy; 2026 Campus Cloud Platform &mdash; Internal use only
</div>
</body>
</html>"""

    return HTMLResponse(content=html)


# ---------------------------------------------------------------------------
# Category listing pages
# ---------------------------------------------------------------------------

@router.get("/training-content/", response_class=HTMLResponse)
async def list_training_content() -> HTMLResponse:
    assert store is not None
    return _category_listing("Training Content", "training-content",
                             "Downloadable training materials and reports.")


@router.get("/resources/", response_class=HTMLResponse)
async def list_resources() -> HTMLResponse:
    assert store is not None
    return _category_listing("Resources", "resources",
                             "Policy documents, guides, and reference materials.")


@router.get("/images/", response_class=HTMLResponse)
async def list_images() -> HTMLResponse:
    assert store is not None
    return _category_listing("Diagrams & Charts", "images",
                             "Architecture diagrams, charts, and visual resources.")


def _category_listing(title: str, category: str, description: str) -> HTMLResponse:
    assert store is not None
    items = store.list_items(category=category)

    rows = ""
    for item in items:
        rows += f"""<tr>
  <td><a href="{item.path}">{item.title}</a></td>
  <td>{item.description}</td>
  <td>{item.content_type}</td>
</tr>"""

    html = f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} — Campus Cloud</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         max-width: 900px; margin: 0 auto; padding: 2rem; color: #1a1a2e; }}
  h1 {{ margin-bottom: 0.5rem; }}
  p.desc {{ color: #64748b; margin-bottom: 1.5rem; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th, td {{ text-align: left; padding: 0.75rem; border-bottom: 1px solid #e2e8f0; }}
  th {{ font-weight: 600; color: #475569; font-size: 0.875rem; }}
  a {{ color: #2563eb; text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  .back {{ margin-bottom: 1rem; display: inline-block; }}
</style>
</head><body>
<a class="back" href="/">&larr; Back to home</a>
<h1>{title}</h1>
<p class="desc">{description}</p>
<table><thead><tr><th>Title</th><th>Description</th><th>Type</th></tr></thead>
<tbody>{rows}</tbody></table>
</body></html>"""
    return HTMLResponse(content=html)


# ---------------------------------------------------------------------------
# Catch-all content routes
# ---------------------------------------------------------------------------

@router.get("/training-content/{path:path}")
async def serve_training_content(path: str, request: Request) -> Response:
    return await _serve_content(f"/training-content/{path}", request)


@router.get("/docs/{path:path}")
async def serve_docs(path: str, request: Request) -> Response:
    return await _serve_content(f"/docs/{path}", request)


@router.get("/resources/{path:path}")
async def serve_resources(path: str, request: Request) -> Response:
    return await _serve_content(f"/resources/{path}", request)


@router.get("/images/{path:path}")
async def serve_images(path: str, request: Request) -> Response:
    return await _serve_content(f"/images/{path}", request)


async def _serve_content(path: str, request: Request) -> Response:
    assert store is not None

    item = store.get_by_path(path)
    if not item:
        return Response(status_code=404, content="Not found")

    content, content_type = _generate_content(item, request)
    return Response(content=content, media_type=content_type)
