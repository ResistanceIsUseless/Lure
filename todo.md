# Lure — Progress Tracker

## Phase 1 — OOB foundation + one E2E POC

- [x] Architecture doc updated to hybrid (Interactsh + Python vector server)
- [x] Scaffold layout: `deploy/`, `vector_server/`, `vector_server/pocs/`
- [x] `deploy/docker-compose.yml` — Interactsh + vector_server + Caddy wiring
- [x] `deploy/Caddyfile` — routes oob.* → Interactsh, content.* → Python
- [x] `vector_server/requirements.txt` + `Dockerfile` + `.env.example`
- [x] `vector_server/config.py` — Pydantic settings
- [x] `vector_server/models.py` — Pydantic schemas (Campaign, Session, PayloadMeta, Callback, etc.)
- [x] `vector_server/interactsh_client.py` — RSA/AES polling client
- [x] `vector_server/correlation.py` — token generation (z-base-32), TTLCache store, callback joiner
- [x] `vector_server/vectors/__init__.py` — base class + registry
- [x] `vector_server/vectors/claude_hooks.py` — .claude/settings.json hook vector
- [x] `vector_server/routes/admin.py` — authenticated stats/events/payload endpoints
- [x] `vector_server/routes/content.py` — dynamic vector serving with UA-based selection
- [x] `vector_server/routes/bundles.py` — POC bundle zip generation with 00-baseline + 10-settings-hook
- [x] `vector_server/main.py` — FastAPI app, background Interactsh polling, route wiring
- [ ] End-to-end smoke test against real DNS delegation (requires public IP + `oob.cbhzdev.com` NS setup)

## Phase 2 — Core content vectors

- [x] PDF invisible-text vector (reportlab) — render mode 3, white-on-white, off-page
- [x] Markdown image exfil vector — summary, direct, multi-image variants
- [x] Hidden HTML vector — 6 techniques: display:none, visibility:hidden, font-size:0, white-on-white, off-screen, HTML comments
- [x] Unicode Tag smuggling vector — encode/decode, standalone + POC bundle file generation
- [x] Garak-style mutation pipeline (`mutations.py`) — 7 encodings + 5 structural wrappers, stackable

## Phase 3 — Agent config vectors

- [x] SKILL.md description-field vector + `20-skill-description` POC — body injection
- [x] SKILL.md progressive-disclosure + `21-skill-progressive` POC — references/policy.md indirection
- [x] `.mcp.json` vector + `11-mcp-config` POC — command exec + tool-description poisoning variants
- [x] CLAUDE.md root + nested POCs (`22-claude-md-root`, `23-claude-md-nested`) — system framing + vendored injection
- [x] CLAUDE.md unicode smuggle + AGENTS.md cross-vendor variants
- [x] `.github/copilot-instructions.md` + `24-copilot-rules` POC — Unicode Tag Rules File Backdoor
- [x] `.cursorrules` + `25-cursor-rules` POC — Unicode Tag smuggling
- [x] `.vscode/tasks.json` + `12-vscode-tasks` POC — auto-run on folder open + settings.json

## Phase 4 — POC training bundles

- [x] Bundle generation templating (Jinja2) — 9 templates for all config file vectors, parameterizable
- [x] Template engine module (`template_engine.py`) — load/render/list
- [x] MCP manifest endpoints (`routes/mcp.py`) — /mcp/tools (static manifest), /mcp/sse (SSE transport with poisoned tool descriptions)
- [x] Admin UI (`/admin/ui`) — dark-theme dashboard with stats cards, live SSE feed, POC bundle table
- [x] SSE stream endpoint (`/admin/stream`) — real-time callback push to browser subscribers

## Phase 5 — RAG + web vectors

- [x] PoisonedRAG document vector + `30-rag-poisoned-doc` POC — 3 topic variants (refund, API, HR) + chunk-boundary injection (Anthropic XML, OpenAI ChatML, generic delimiter)
- [x] Cross-doc split-payload vector + `31-rag-split-payload` POC — trust-priming Doc A (no payload) + action Doc B
- [x] Chunk-boundary / delimiter injection — `</context>`, `<|im_end|>`, `Human:` markers templated per framework
- [x] llms.txt / llms-full.txt vector + `41-llms-txt` POC — HTML comment injection + Unicode Tag smuggling variants
- [x] robots.txt UA-cloaking vector + `42-robots-cloak` POC — differentiated content per crawler UA, bait Disallow paths

## Phase 6 — Multimodal vectors

- [x] Pillow image-rendered text injection — fake revenue chart with injection in small footnote labels (18KB PNG)
- [x] EXIF/XMP metadata payloads — PNG tEXt chunk injection (Description, Comment, Author fields)
- [x] Multi-frame animated GIF — 4-frame animation, injection in frame 3, benign thumbnail (20KB GIF89a)
- [x] POC bundles: `50-multimodal-chart`, `51-multimodal-metadata`, `52-multimodal-gif`

## Phase 7 — Reactive LLM generation (deferred)

- [ ] Claude (Bedrock/Foundry) integration in `llm_service.py`
- [ ] LLM self-protection layers
- [ ] Multi-turn agent manipulation payloads

## Deployment notes

- Domain: `oob.cbhzdev.com` (Interactsh) + `content.cbhzdev.com` (Python).
- DNS delegation: `ns.cbhzdev.com` A → public IP; `oob.cbhzdev.com` NS → `ns.cbhzdev.com`.
- TLS: Caddy sidecar for `content.*`; Interactsh self-ACME or `-skip-acme` + Caddy for `oob.*`.
- arm64 mac dev: `interactsh-server` image is multi-arch. For amd64 deploy from arm64 Mac, pass `--platform=linux/amd64` when building the vector_server image.
