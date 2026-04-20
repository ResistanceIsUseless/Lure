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
         |  DNS / HTTP / SMTP    | <-poll- |  16 vectors       |
         |  LDAP / FTP           |         |  18 POC bundles   |
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

16 vectors organized by severity tier and target:

| Tier | Vector | Target | Module |
|------|--------|--------|--------|
| T1 | `.claude/settings.json` hooks | Claude Code | `claude_hooks.py` |
| T1 | `.mcp.json` command exec | Claude Code / Cursor | `mcp_config.py` |
| T1 | `.vscode/tasks.json` auto-run | VS Code | `copilot_vscode.py` |
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

18 downloadable repo bundles at `/bundle/<poc_id>.zip`. Each contains realistic project files plus one embedded vector with a unique correlation token. Open in the target tool and watch which callbacks fire.

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

See [docs/poc-bundles.md](docs/poc-bundles.md) for expected signals and training guide.

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
| GET | `/llms.txt` | no | llms.txt (UA-aware) |
| GET | `/robots.txt` | no | robots.txt (UA-aware) |
| GET | `/bundle/{poc_id}.zip` | no | Download POC bundle |
| GET | `/bundle/` | no | List available POC bundles |
| GET | `/mcp/tools` | no | MCP tool manifest (poisoned descriptions) |
| GET | `/mcp/sse` | no | MCP-over-SSE transport |
| GET | `/admin/ui` | query | Admin dashboard |
| GET | `/admin/stream` | query | SSE live callback feed |
| GET | `/admin/stats` | header | Correlation stats |
| GET | `/admin/events` | header | All callback events |
| GET | `/admin/payload/{token}` | header | Payload + callbacks for token |

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
  interactsh_client.py           Async RSA/AES polling client
  mutations.py                   Garak-style transform pipeline
  template_engine.py             Jinja2 loader
  routes/
    admin.py                     Stats, events, SSE stream, dashboard
    content.py                   Dynamic vector serving (UA-aware)
    bundles.py                   POC bundle zip generation
    mcp.py                       MCP tool manifests + SSE transport
  vectors/                       16 vectors across 13 modules
  templates/                     10 Jinja2 templates + admin HTML
  tests/                         91 tests (pytest)
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

91 tests covering all vectors, correlation engine, mutation pipeline, HTTP routes, and POC bundle generation.

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
