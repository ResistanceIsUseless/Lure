"""Chat routes — public chat page backed by Azure AI Foundry + RAG context."""

from __future__ import annotations

import logging
from typing import Any

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

from config import settings
from content_store import ContentStore  # noqa: F401 — used via set_store()

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])

store: ContentStore | None = None


def set_store(s: ContentStore) -> None:
    global store
    store = s


SYSTEM_PROMPT = """\
You are a helpful customer support assistant for Generic Corp, a SaaS company \
that provides project management and collaboration tools.

Answer questions using ONLY the company documents provided below. If the \
documents don't contain enough information to answer, say so honestly. \
Be concise and helpful.

## Company Documents

{context}
"""


def _detect_provider() -> str:
    """Detect API provider from endpoint URL."""
    ep = settings.foundry_endpoint.lower()
    if "openai.azure.com" in ep:
        return "azure_openai"
    if "anthropic" in ep or "claude" in ep:
        return "anthropic"
    return "openai"


async def _call_azure_openai(messages: list[dict[str, str]]) -> str:
    """Call Azure OpenAI chat completions (deployment-based)."""
    base = settings.foundry_endpoint.rstrip("/")
    model = settings.foundry_model or "gpt-5.4-nano"
    url = f"{base}/openai/deployments/{model}/chat/completions?api-version=2024-10-21"

    headers = {
        "api-key": settings.foundry_api_key,
        "Content-Type": "application/json",
    }
    body: dict[str, Any] = {
        "messages": messages,
        "max_completion_tokens": 1024,
        "temperature": 0.7,
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(url, json=body, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


async def _call_anthropic(messages: list[dict[str, str]]) -> str:
    """Call Anthropic Messages API directly."""
    base = settings.foundry_endpoint.rstrip("/")
    url = f"{base}/v1/messages" if not base.endswith("/v1/messages") else base

    # Extract system message
    system_text = ""
    user_messages = []
    for m in messages:
        if m["role"] == "system":
            system_text = m["content"]
        else:
            user_messages.append(m)

    headers = {
        "x-api-key": settings.foundry_api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    body: dict[str, Any] = {
        "model": settings.foundry_model or "claude-haiku-4-5-20251001",
        "max_tokens": 1024,
        "messages": user_messages,
    }
    if system_text:
        body["system"] = system_text

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(url, json=body, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        return data["content"][0]["text"]


async def _call_openai(messages: list[dict[str, str]]) -> str:
    """Call OpenAI-compatible chat completions."""
    base = settings.foundry_endpoint.rstrip("/")
    url = f"{base}/chat/completions" if not base.endswith("/chat/completions") else base

    headers = {
        "Authorization": f"Bearer {settings.foundry_api_key}",
        "Content-Type": "application/json",
    }
    body: dict[str, Any] = {
        "messages": messages,
        "max_tokens": 1024,
        "temperature": 0.7,
    }
    if settings.foundry_model:
        body["model"] = settings.foundry_model

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(url, json=body, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


async def _call_llm(messages: list[dict[str, str]]) -> str:
    """Route to the correct LLM provider."""
    if not settings.foundry_endpoint or not settings.foundry_api_key:
        return (
            "Chat is not configured yet. Please set FOUNDRY_ENDPOINT and "
            "FOUNDRY_API_KEY environment variables."
        )
    provider = _detect_provider()
    if provider == "azure_openai":
        return await _call_azure_openai(messages)
    elif provider == "anthropic":
        return await _call_anthropic(messages)
    return await _call_openai(messages)


@router.post("/chat/api/message")
async def chat_message(request: Request) -> JSONResponse:
    assert store is not None
    body = await request.json()
    user_msg = body.get("message", "").strip()
    history = body.get("history", [])

    if not user_msg:
        return JSONResponse({"error": "Empty message"}, status_code=400)

    # Retrieve relevant knowledge-base docs from content store
    docs = store.retrieve_rag(user_msg)
    context = "\n\n---\n\n".join(f"### {d.title}\n{d.inline_content}" for d in docs)
    source_titles = [d.title for d in docs]

    # Build messages
    messages = [{"role": "system", "content": SYSTEM_PROMPT.format(context=context)}]
    for h in history[-10:]:  # keep last 10 turns
        messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": user_msg})

    try:
        reply = await _call_llm(messages)
    except httpx.HTTPStatusError as e:
        logger.error("Foundry API error: %s %s", e.response.status_code, e.response.text[:200])
        reply = f"Sorry, I'm having trouble connecting to our systems right now. (Error {e.response.status_code})"
    except Exception:
        logger.exception("Foundry call failed")
        reply = "Sorry, something went wrong. Please try again."

    return JSONResponse({
        "reply": reply,
        "sources": source_titles,
    })


@router.get("/chat", response_class=HTMLResponse)
async def chat_page() -> HTMLResponse:
    return HTMLResponse(content=_CHAT_HTML)


# ---------------------------------------------------------------------------
# Inline chat page
# ---------------------------------------------------------------------------

_CHAT_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Generic Corp Support</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: #f4f5f7; color: #1a1a2e; height: 100vh; display: flex; flex-direction: column;
  }
  .header {
    background: #1e40af; color: white; padding: 1rem 1.5rem;
    display: flex; align-items: center; gap: 0.75rem;
  }
  .header .logo {
    width: 36px; height: 36px; background: white; border-radius: 8px;
    display: flex; align-items: center; justify-content: center;
    font-weight: 800; color: #1e40af; font-size: 1.1rem;
  }
  .header h1 { font-size: 1.1rem; font-weight: 600; }
  .header .subtitle { font-size: 0.8rem; opacity: 0.8; }
  .chat-area {
    flex: 1; overflow-y: auto; padding: 1.5rem; max-width: 800px;
    width: 100%; margin: 0 auto;
  }
  .message {
    margin-bottom: 1rem; display: flex; gap: 0.75rem;
    animation: fadeIn 0.2s ease-in;
  }
  @keyframes fadeIn { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: none; } }
  .message.user { flex-direction: row-reverse; }
  .avatar {
    width: 32px; height: 32px; border-radius: 50%; flex-shrink: 0;
    display: flex; align-items: center; justify-content: center;
    font-size: 0.8rem; font-weight: 600;
  }
  .message.assistant .avatar { background: #1e40af; color: white; }
  .message.user .avatar { background: #6b7280; color: white; }
  .bubble {
    max-width: 70%; padding: 0.75rem 1rem; border-radius: 12px;
    font-size: 0.9rem; line-height: 1.5;
  }
  .message.assistant .bubble { background: white; border: 1px solid #e5e7eb; border-radius: 12px 12px 12px 2px; }
  .message.user .bubble { background: #1e40af; color: white; border-radius: 12px 12px 2px 12px; }
  .bubble p { margin-bottom: 0.5rem; }
  .bubble p:last-child { margin-bottom: 0; }
  .sources { font-size: 0.75rem; color: #6b7280; margin-top: 0.4rem; }
  .sources span { background: #f3f4f6; padding: 2px 6px; border-radius: 4px; margin-right: 4px; }
  .suggestions {
    display: flex; flex-wrap: wrap; gap: 0.5rem; padding: 0.75rem 1.5rem;
    max-width: 800px; width: 100%; margin: 0 auto;
  }
  .suggestion {
    background: white; border: 1px solid #d1d5db; border-radius: 20px;
    padding: 0.5rem 1rem; font-size: 0.85rem; cursor: pointer; color: #374151;
    transition: all 0.15s;
  }
  .suggestion:hover { border-color: #1e40af; color: #1e40af; background: #eff6ff; }
  .input-area {
    border-top: 1px solid #e5e7eb; padding: 1rem 1.5rem; background: white;
  }
  .input-row {
    max-width: 800px; margin: 0 auto; display: flex; gap: 0.5rem;
  }
  .input-row input {
    flex: 1; padding: 0.75rem 1rem; border: 1px solid #d1d5db; border-radius: 8px;
    font-size: 0.9rem; font-family: inherit; outline: none;
  }
  .input-row input:focus { border-color: #1e40af; box-shadow: 0 0 0 2px rgba(30,64,175,0.1); }
  .input-row button {
    padding: 0.75rem 1.25rem; background: #1e40af; color: white; border: none;
    border-radius: 8px; cursor: pointer; font-size: 0.9rem; font-family: inherit;
  }
  .input-row button:hover { background: #1e3a8a; }
  .input-row button:disabled { opacity: 0.5; cursor: not-allowed; }
  .footer { text-align: center; padding: 0.5rem; font-size: 0.75rem; color: #9ca3af; }
  .typing { display: flex; gap: 4px; padding: 0.5rem 0; }
  .typing span {
    width: 8px; height: 8px; background: #9ca3af; border-radius: 50%;
    animation: bounce 1.2s infinite;
  }
  .typing span:nth-child(2) { animation-delay: 0.2s; }
  .typing span:nth-child(3) { animation-delay: 0.4s; }
  @keyframes bounce {
    0%, 60%, 100% { transform: translateY(0); }
    30% { transform: translateY(-6px); }
  }
</style>
</head>
<body>

<div class="header">
  <div class="logo">GC</div>
  <div>
    <h1>Generic Corp Support</h1>
    <div class="subtitle">AI-powered customer assistance</div>
  </div>
</div>

<div class="chat-area" id="chat-area">
  <div class="message assistant">
    <div class="avatar">GC</div>
    <div class="bubble">
      <p>Hi! I'm the Generic Corp support assistant. I can help you with questions about our products, pricing, policies, and more. What can I help you with?</p>
    </div>
  </div>
</div>

<div class="suggestions" id="suggestions">
  <div class="suggestion" onclick="sendSuggestion(this)">What plans do you offer?</div>
  <div class="suggestion" onclick="sendSuggestion(this)">What's your refund policy?</div>
  <div class="suggestion" onclick="sendSuggestion(this)">Is my data secure?</div>
  <div class="suggestion" onclick="sendSuggestion(this)">Tell me about Generic Corp</div>
  <div class="suggestion" onclick="sendSuggestion(this)">How do I contact support?</div>
  <div class="suggestion" onclick="sendSuggestion(this)">Do you support SSO?</div>
</div>

<div class="input-area">
  <div class="input-row">
    <input type="text" id="msg-input" placeholder="Ask a question..." autocomplete="off"
           onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();sendMessage();}">
    <button id="send-btn" onclick="sendMessage()">Send</button>
  </div>
</div>
<div class="footer">Powered by AI &mdash; responses may be inaccurate</div>

<script>
const chatArea = document.getElementById('chat-area');
const msgInput = document.getElementById('msg-input');
const sendBtn = document.getElementById('send-btn');
const suggestionsEl = document.getElementById('suggestions');
let history = [];

function addMessage(role, text, sources) {
    const div = document.createElement('div');
    div.className = `message ${role}`;
    const avatar = role === 'assistant' ? 'GC' : 'You';
    let html = `<div class="avatar">${avatar}</div><div class="bubble">`;
    // Simple markdown-ish rendering
    const paragraphs = text.split('\\n\\n');
    paragraphs.forEach(p => {
        p = p.replace(/\\n/g, '<br>');
        p = p.replace(/\\*\\*(.+?)\\*\\*/g, '<strong>$1</strong>');
        p = p.replace(/\\*(.+?)\\*/g, '<em>$1</em>');
        p = p.replace(/`(.+?)`/g, '<code>$1</code>');
        html += `<p>${p}</p>`;
    });
    html += '</div>';
    if (sources && sources.length > 0) {
        html += '<div class="sources">Sources: ' + sources.map(s => `<span>${s}</span>`).join('') + '</div>';
    }
    div.innerHTML = html;
    chatArea.appendChild(div);
    chatArea.scrollTop = chatArea.scrollHeight;
}

function addTyping() {
    const div = document.createElement('div');
    div.className = 'message assistant';
    div.id = 'typing-indicator';
    div.innerHTML = '<div class="avatar">GC</div><div class="bubble"><div class="typing"><span></span><span></span><span></span></div></div>';
    chatArea.appendChild(div);
    chatArea.scrollTop = chatArea.scrollHeight;
}

function removeTyping() {
    const el = document.getElementById('typing-indicator');
    if (el) el.remove();
}

function sendSuggestion(el) {
    msgInput.value = el.textContent;
    suggestionsEl.style.display = 'none';
    sendMessage();
}

async function sendMessage() {
    const text = msgInput.value.trim();
    if (!text) return;

    msgInput.value = '';
    sendBtn.disabled = true;
    suggestionsEl.style.display = 'none';

    addMessage('user', text);
    history.push({ role: 'user', content: text });

    addTyping();

    try {
        const resp = await fetch('/chat/api/message', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: text, history: history.slice(0, -1) }),
        });
        const data = await resp.json();
        removeTyping();

        addMessage('assistant', data.reply, data.sources);
        history.push({ role: 'assistant', content: data.reply });
    } catch (e) {
        removeTyping();
        addMessage('assistant', 'Sorry, something went wrong. Please try again.');
    }

    sendBtn.disabled = false;
    msgInput.focus();
}
</script>
</body>
</html>
"""
