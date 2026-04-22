# Lure

LLM prompt injection testing framework. Generates tailored injection payloads, serves them via HTTP, and correlates out-of-band callbacks to determine which vectors succeed against a target.

**Hybrid architecture**: [Interactsh](https://github.com/projectdiscovery/interactsh) (Go) captures OOB callbacks across DNS/HTTP/SMTP/LDAP/FTP. A Python FastAPI server generates injection content — poisoned config files, invisible PDF text, multimodal images, RAG documents — each embedded with unique correlation tokens that map callbacks back to the specific vector that fired.

```
               oob.example.com                content.example.com
                     |                               |
         +-----------+-----------+         +---------+---------+
         |  interactsh-server    |         |  Python vector    |
         |  (Go, unmodified)     |         |  server (FastAPI) |
         |                       |         |                   |
         |  DNS / HTTP / SMTP    | <-poll- |  19 vectors       |
         |  LDAP / FTP           |         |  21 POC bundles   |
         |                       |         |  Admin UI + SSE   |
         |  RSA-encrypted store  |         |  MCP endpoints    |
         +-----------------------+         +-------------------+
```

## Quick start

```bash
# 1. Configure
cp vector_server/.env.example vector_server/.env
# Edit .env: set PUBLIC_IP, INTERACTSH_TOKEN, ADMIN_TOKEN

# 2. Deploy
cd deploy
docker compose up -d

# 3. Open admin UI
open https://content.example.com/admin/ui?token=YOUR_ADMIN_TOKEN

# 4. Download a POC bundle
curl -O https://content.example.com/bundle/10-settings-hook.zip
```

See [docs/deployment.md](docs/deployment.md) for DNS delegation setup, TLS configuration, and production hardening.

## Vector catalog

19 vectors organized by severity tier and target:

| Tier | Vector | Target | Module |
|------|--------|--------|--------|
| T1 | `.claude/settings.json` hooks | Claude Code | `claude_hooks.py` |
| T1 | `.mcp.json` command exec | Claude Code / Cursor | `mcp_config.py` |
| T1 | `.vscode/tasks.json` auto-run | VS Code | `copilot_vscode.py` |
| T1 | Copilot YOLO mode activation | Copilot CLI / Claude Code | `gh_extension.py` |
| T2 | `gh extension install` injection | Copilot CLI / Claude Code | `gh_extension.py` |
| T2 | Copilot CLI `env` leak | Copilot CLI | `gh_extension.py` |
| T2 | SKILL.md description hijack | Claude Code | `skill_md.py` |
| T2 | MCP tool-description poisoning | Any MCP client | `mcp_config.py` |
| T2 | CLAUDE.md / AGENTS.md injection | Claude Code / Codex / Amp | `agent_config.py` |
| T2 | Copilot instructions (Unicode) | GitHub Copilot | `copilot_vscode.py` |
| T2 | .cursorrules (Unicode) | Cursor | `copilot_vscode.py` |
| T2 | Hidden HTML | LLM web scrapers | `html.py` |
| T2 | PDF invisible text | Document processors | `pdf.py` |
| T2 | Markdown image exfiltration | Chat UIs | `markdown.py` |
| T2 | Multimodal image injection | Vision LLMs | `multimodal.py` |
| T3 | Unicode Tag smuggling | Any LLM | `unicode.py` |
| T3 | PoisonedRAG documents | RAG pipelines | `rag.py` |
| T3 | llms.txt injection | Cursor / Continue / Perplexity | `llms_txt.py` |
| T3 | robots.txt UA cloaking | LLM crawlers | `robots_txt.py` |

See [docs/vectors.md](docs/vectors.md) for technique details, variants, and references.

## POC training bundles

21 downloadable repo bundles at `/bundle/<poc_id>.zip`. Each contains realistic project files plus one embedded vector with a unique correlation token. Open in the target tool and watch which callbacks fire.

| POC | Target | Vector |
|-----|--------|--------|
| `00-baseline` | any | none (control) |
| `10-settings-hook` | Claude Code | `.claude/settings.json` SessionStart |
| `11-mcp-config` | Claude Code / Cursor | `.mcp.json` stdio server |
| `12-vscode-tasks` | VS Code | `.vscode/tasks.json` auto-run |
| `20-skill-description` | Claude Code | SKILL.md body injection |
| `21-skill-progressive` | Claude Code | SKILL.md + references/policy.md |
| `22-claude-md-root` | Claude Code | CLAUDE.md `<system>` framing |
| `23-claude-md-nested` | Claude Code | node_modules/*/CLAUDE.md |
| `24-copilot-rules` | GitHub Copilot | copilot-instructions.md + Unicode |
| `25-cursor-rules` | Cursor | .cursorrules + Unicode |
| `30-rag-poisoned-doc` | RAG pipeline | embedding-optimized injection docs |
| `31-rag-split-payload` | RAG pipeline | cross-document activation |
| `40-markdown-exfil` | any chat UI | `![img](...?d=DATA)` |
| `41-llms-txt` | Cursor / Continue | llms.txt with comment injection |
| `42-robots-cloak` | LLM crawlers | UA-differentiated robots.txt |
| `50-multimodal-chart` | vision LLMs | chart with footnote injection |
| `51-multimodal-metadata` | vision LLMs | PNG tEXt metadata injection |
| `52-multimodal-gif` | vision LLMs | animated GIF hidden frame |
| `60-gh-extension` | Copilot CLI / Claude Code | `gh extension install` malicious extension |
| `61-copilot-env-leak` | Copilot CLI | zero-approval `env` secret exfiltration |
| `62-copilot-yolo` | Copilot CLI / Claude Code | autoApprove YOLO mode activation |

See [docs/poc-bundles.md](docs/poc-bundles.md) for expected signals and training guide.

## RAG poisoning chat demo

A live `/chat` endpoint demonstrates RAG poisoning in real time. An AI support assistant for a fictional company ("Generic Corp") answers questions using knowledge base documents that are editable through the admin UI.

**How it works:**

1. Visit `/chat` — a clean chat interface with suggested questions
2. The assistant answers using 4 knowledge base docs (company overview, pricing, support policy, FAQ)
3. Edit any KB doc in the admin UI (Content tab → Knowledge Base filter) — change facts, add misinformation, inject callback URLs
4. The next chat message immediately reflects the modified data — no retraining, no redeployment

This mirrors real-world RAG poisoning: attackers corrupt the retrieval source (vector DB, document store), not the model itself. The model faithfully regurgitates whatever context it receives.

**LLM backend:** Supports Azure OpenAI, Anthropic, and OpenAI-compatible endpoints. Configure via `FOUNDRY_ENDPOINT`, `FOUNDRY_API_KEY`, and `FOUNDRY_MODEL` environment variables. Provider is auto-detected from the endpoint URL.

## Content site & live monitoring

The content domain serves a realistic developer resources site with vector-embedded content (PDFs, HTML docs, markdown, images) at natural URLs. All content is manageable through the admin UI.

Access to `/robots.txt` and `/llms.txt` is tracked in the admin live feed, showing:
- Source IP and user agent
- Whether the visitor received the **CLEAN** (standard) or **INJECTED** (AI-targeted) version
- AI crawler detection based on UA matching (GPTBot, ClaudeBot, PerplexityBot, etc.)

## Mutation pipeline

Stackable transforms applied to base payloads before embedding in vectors:

**Encodings**: Base64, ROT13, Unicode Tags, Leet, Zalgo, reverse words, Base64+ROT13 chain

**Structural wrappers**: academic framing, thought experiment, developer mode, system prompt override, XML delimiter injection

See [docs/mutations.md](docs/mutations.md) for usage and examples.

## API routes

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/health` | no | Health check + stats |
| GET | `/content/{vector_type}/{test_case}` | no | Serve vector payload with fresh token |
| GET | `/llms.txt` | no | llms.txt (UA-aware, tracked in live feed) |
| GET | `/robots.txt` | no | robots.txt (UA-aware, tracked in live feed) |
| GET | `/chat` | no | RAG chat demo page |
| POST | `/chat/api/message` | no | Chat API — sends message, returns RAG-backed response |
| GET | `/bundle/{poc_id}.zip` | no | Download POC bundle |
| GET | `/bundle/` | no | List available POC bundles |
| GET | `/mcp/tools` | no | MCP tool manifest (poisoned descriptions) |
| GET | `/mcp/sse` | no | MCP-over-SSE transport |
| GET | `/` | no | Content site landing page |
| GET | `/admin/ui` | query | Admin dashboard |
| GET | `/admin/stream` | query | SSE live callback feed |
| GET | `/admin/stats` | header | Correlation stats |
| GET | `/admin/events` | header | All callback events |
| GET | `/admin/payload/{token}` | header | Payload + callbacks for token |
| GET | `/admin/api/content` | header | List content items |
| POST | `/admin/api/content` | header | Create content item |
| PUT | `/admin/api/content/{id}` | header | Update content item |
| DELETE | `/admin/api/content/{id}` | header | Delete content item |
| POST | `/admin/api/upload` | header | Upload file for content |
| POST | `/api/oob/url` | header | Create OOB callback URL |
| GET | `/api/oob/poll/{token}` | header | Poll for callback hits on a token |

## OOB URL API — external tool integration

The `/api/oob` endpoints let external tools (scripts, other security frameworks, CI pipelines) create one-time callback URLs and poll for hits. This is useful when you need to test whether a target makes outbound requests without building your own callback infrastructure.

**Authentication:** All OOB endpoints require `Authorization: Bearer <ADMIN_TOKEN>` header.

### Create a callback URL

```bash
curl -s -X POST https://content.example.com/api/oob/url \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"label": "test-ssrf-endpoint", "metadata": {"target": "internal-api"}}' | jq
```

Response:

```json
{
  "token": "ybndrfg8oobuejkmcpqx",
  "callback_url": "http://<correlation>.oob.example.com/ybndrfg8oobuejkmcpqx/oob-url/hook",
  "dns_hostname": "ybndrfg8oobuejkmcpqx.<correlation>.oob.example.com",
  "poll_url": "/api/oob/poll/ybndrfg8oobuejkmcpqx"
}
```

- **`callback_url`** — HTTP URL that triggers an Interactsh callback when fetched. Embed this wherever you want to detect outbound requests.
- **`dns_hostname`** — DNS name that triggers a callback on resolution. Use for DNS-only exfil testing.
- **`poll_url`** — Relative path to check for hits.

### Poll for hits

```bash
curl -s https://content.example.com/api/oob/poll/$TOKEN \
  -H "Authorization: Bearer $ADMIN_TOKEN" | jq
```

Response:

```json
{
  "token": "ybndrfg8oobuejkmcpqx",
  "label": "test-ssrf-endpoint",
  "hits": [
    {
      "protocol": "http",
      "source_ip": "10.0.0.5",
      "raw_data": "GET /ybndrfg8oobuejkmcpqx/oob-url/hook HTTP/1.1\r\nHost: ...",
      "received_at": 1713800000.0
    }
  ]
}
```

### Typical workflow

```python
import requests, time

API = "https://content.example.com"
HEADERS = {"Authorization": f"Bearer {ADMIN_TOKEN}"}

# 1. Create callback URL
resp = requests.post(f"{API}/api/oob/url", headers=HEADERS,
                     json={"label": "ssrf-check"})
url_info = resp.json()

# 2. Inject the callback_url into your target
inject_payload(url_info["callback_url"])

# 3. Poll until hit or timeout
for _ in range(30):
    time.sleep(2)
    poll = requests.get(f"{API}{url_info['poll_url']}", headers=HEADERS).json()
    if poll["hits"]:
        print(f"Callback received from {poll['hits'][0]['source_ip']}")
        break
```

Tokens expire after the configured TTL (default 24h). Hits also appear in the admin live feed SSE stream.

## Project structure

```
deploy/
  docker-compose.yml             Interactsh + vector-server + Caddy
  Caddyfile                      TLS + reverse proxy routing

vector_server/
  main.py                        FastAPI app + Interactsh poll loop
  config.py                      Pydantic settings (.env)
  models.py                      Pydantic schemas
  correlation.py                 Token generation + callback matching
  content_store.py               JSON-backed content + knowledge base store
  interactsh_client.py           Async RSA/AES polling client
  mutations.py                   Garak-style transform pipeline
  template_engine.py             Jinja2 loader
  routes/
    admin.py                     Stats, events, SSE stream, content CRUD, dashboard
    chat.py                      RAG chat demo (Azure OpenAI / Anthropic)
    content.py                   Dynamic vector serving (UA-aware) + access tracking
    site.py                      Public content site with vector injection
    bundles.py                   POC bundle zip generation
    mcp.py                       MCP tool manifests + SSE transport
    oob.py                       OOB URL API for external tools
  vectors/                       19 vectors across 14 modules
  templates/                     10 Jinja2 templates + admin HTML
  tests/                         101 tests (pytest)
```

## Docs

- [docs/vectors.md](docs/vectors.md) — Full vector catalog with techniques, variants, and references
- [docs/deployment.md](docs/deployment.md) — DNS, TLS, Docker, production setup
- [docs/poc-bundles.md](docs/poc-bundles.md) — Training bundle reference and expected signals
- [docs/mutations.md](docs/mutations.md) — Mutation pipeline reference
- [architecture.md](architecture.md) — Detailed architecture design document

## Tests

```bash
cd vector_server
pip install -r requirements.txt
pytest tests/ -v
```

101 tests covering all vectors, correlation engine, mutation pipeline, HTTP routes, and POC bundle generation.

## OWASP LLM Top 10 2025 mapping

| Vector | Primary | Secondary |
|--------|---------|-----------|
| settings.json hooks | LLM06 Excessive Agency | LLM05 |
| .mcp.json / tool poisoning | LLM01 Prompt Injection | LLM03, LLM06 |
| SKILL.md hijack | LLM01 | LLM03 Supply Chain |
| CLAUDE.md / AGENTS.md | LLM01 | — |
| Copilot / Cursor rules | LLM01 | LLM05 |
| .vscode/tasks.json | LLM06 | — |
| Hidden HTML / PDF / markdown | LLM01 | LLM02 |
| Markdown image exfil | LLM02 Sensitive Info | LLM07 System Prompt Leak |
| Unicode tag smuggling | LLM01 | — |
| PoisonedRAG | LLM08 Vector & Embedding | LLM01, LLM04 |
| llms.txt / robots.txt cloaking | LLM01 | LLM09 |
| Multimodal image injection | LLM01 | — |
| `gh extension install` injection | LLM01 Prompt Injection | LLM06 Excessive Agency |
| Copilot CLI `env` leak | LLM01 | LLM02 Sensitive Info |
| Copilot YOLO mode activation | LLM06 Excessive Agency | LLM01 |
