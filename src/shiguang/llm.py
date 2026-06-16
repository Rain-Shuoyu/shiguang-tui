"""LLM client: MiniMax / OpenAI / Anthropic streaming.

Faithful port of the macOS app's LLMClient. Same wire formats,
same auth headers, same `thinking` field-as-object requirement
for MiniMax M2.7.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import AsyncIterator, Optional

import httpx

from .config import LLMSettings


@dataclass
class ChatMessage:
    role: str        # "system" | "user" | "assistant"
    content: str


@dataclass
class ChatRequest:
    messages: list[ChatMessage]
    model: str
    temperature: float = 0.7
    max_tokens: int = 2048
    stream: bool = True
    enable_thinking: bool = True   # M2.7 has no working server-side disable; preserved for parity


class LLMError(Exception):
    pass


def _make_client(settings: LLMSettings, timeout: float = 120.0) -> httpx.AsyncClient:
    if not settings.api_key:
        raise LLMError("API key not set. Use `shi config` to configure.")
    return httpx.AsyncClient(timeout=timeout)


async def chat(settings: LLMSettings, req: ChatRequest) -> str:
    """Send a chat request, return the full response text."""
    chunks: list[str] = []
    async for chunk in stream(settings, req):
        chunks.append(chunk)
    return "".join(chunks)


async def stream(settings: LLMSettings, req: ChatRequest) -> AsyncIterator[str]:
    """Send a chat request, yield text chunks as they arrive."""
    provider = settings.provider.lower()
    if provider in ("minimax", "openai"):
        async for c in _stream_openai(settings, req):
            yield c
    elif provider == "anthropic":
        async for c in _stream_anthropic(settings, req):
            yield c
    else:
        raise LLMError(f"Unknown provider: {settings.provider}")


# ── OpenAI-compatible (MiniMax / OpenAI) ────────────────────────

async def _stream_openai(settings: LLMSettings, req: ChatRequest) -> AsyncIterator[str]:
    base = settings.base_url.rstrip("/")
    url = f"{base}/v1/chat/completions"
    body = {
        "model": req.model,
        "messages": [{"role": m.role, "content": m.content} for m in req.messages],
        "temperature": req.temperature,
        "max_tokens": req.max_tokens,
        "stream": True,
    }
    headers = {
        "Authorization": f"Bearer {settings.api_key}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }
    async with _make_client(settings) as client:
        try:
            async with client.stream("POST", url, json=body, headers=headers) as resp:
                if resp.status_code >= 300:
                    body_text = await resp.aread()
                    raise LLMError(f"HTTP {resp.status_code}: {body_text.decode('utf-8', 'replace')[:300]}")
                async for raw in resp.aiter_lines():
                    line = raw.strip()
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        break
                    try:
                        obj = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    choices = obj.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    content = delta.get("content")
                    if content:
                        yield content
        except httpx.HTTPError as e:
            raise LLMError(f"Network error: {e}")


# ── Anthropic Messages API ──────────────────────────────────────

async def _stream_anthropic(settings: LLMSettings, req: ChatRequest) -> AsyncIterator[str]:
    base = settings.base_url.rstrip("/")
    url = f"{base}/v1/messages"
    system_text = ""
    msgs = []
    for m in req.messages:
        if m.role == "system":
            system_text += ("\n" if system_text else "") + m.content
        else:
            msgs.append({"role": m.role, "content": m.content})
    body = {
        "model": req.model,
        "max_tokens": req.max_tokens,
        "temperature": req.temperature,
        "messages": msgs,
        "stream": True,
    }
    if system_text:
        body["system"] = system_text
    headers = {
        "x-api-key": settings.api_key,
        "Authorization": f"Bearer {settings.api_key}",
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }
    async with _make_client(settings) as client:
        try:
            async with client.stream("POST", url, json=body, headers=headers) as resp:
                if resp.status_code >= 300:
                    body_text = await resp.aread()
                    raise LLMError(f"HTTP {resp.status_code}: {body_text.decode('utf-8', 'replace')[:300]}")
                pending_event = ""
                async for raw in resp.aiter_lines():
                    line = raw.strip()
                    if not line:
                        pending_event = ""
                        continue
                    if line.startswith("event:"):
                        pending_event = line[6:].strip()
                        continue
                    if line.startswith("data:") and pending_event == "content_block_delta":
                        payload = line[5:].strip()
                        try:
                            obj = json.loads(payload)
                        except json.JSONDecodeError:
                            continue
                        delta = obj.get("delta") or {}
                        text = delta.get("text")
                        if text:
                            yield text
        except httpx.HTTPError as e:
            raise LLMError(f"Network error: {e}")
