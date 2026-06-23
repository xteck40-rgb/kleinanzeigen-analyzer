"""
Minimal OpenRouter chat client for the watch agents.

API key + model live in the `settings` table (set via the frontend settings
panel, /api/settings). No env vars needed.
"""
import asyncio
import json
import logging
import re

import httpx

logger = logging.getLogger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "deepseek/deepseek-chat-v3.1"

RETRYABLE_STATUS = {408, 429, 500, 502, 503, 524}


class LLMNotConfigured(Exception):
    """No OpenRouter API key configured."""


class LLMError(Exception):
    """OpenRouter call failed after retries."""


async def chat(
    api_key: str,
    model: str,
    messages: list[dict],
    temperature: float = 0.2,
    max_tokens: int = 4000,
    json_mode: bool = False,
    retries: int = 3,
) -> str:
    """One chat completion. Returns assistant text. Raises LLMError/LLMNotConfigured."""
    if not api_key:
        raise LLMNotConfigured("Kein OpenRouter API-Key gesetzt (Tab Agenten → Einstellungen)")

    payload = {
        "model": model or DEFAULT_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:5173",
        "X-Title": "Kleinanzeigen Analyzer",
    }

    last_err = None
    for attempt in range(retries + 1):
        try:
            async with httpx.AsyncClient(timeout=180) as client:
                r = await client.post(OPENROUTER_URL, json=payload, headers=headers)
            if r.status_code in RETRYABLE_STATUS:
                last_err = f"HTTP {r.status_code}: {r.text[:300]}"
                await asyncio.sleep(2 ** attempt * 2)
                continue
            if r.status_code >= 400:
                raise LLMError(f"OpenRouter HTTP {r.status_code}: {r.text[:500]}")
            data = r.json()
            choices = data.get("choices") or []
            if not choices:
                raise LLMError(f"OpenRouter: leere Antwort: {json.dumps(data)[:300]}")
            content = choices[0].get("message", {}).get("content") or ""
            if not content.strip():
                last_err = "leerer content"
                await asyncio.sleep(2 ** attempt)
                continue
            return content
        except (httpx.TimeoutException, httpx.TransportError) as e:
            last_err = f"{type(e).__name__}: {e}"
            await asyncio.sleep(2 ** attempt * 2)

    raise LLMError(f"OpenRouter fehlgeschlagen nach {retries + 1} Versuchen: {last_err}")


def extract_json_array(text: str) -> list:
    """Best-effort: pull the first JSON array out of an LLM response."""
    if not text:
        return []
    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", cleaned, re.DOTALL)
    candidate = fence.group(1) if fence else None
    if candidate is None:
        start, end = cleaned.find("["), cleaned.rfind("]")
        if start == -1 or end <= start:
            return []
        candidate = cleaned[start:end + 1]
    try:
        out = json.loads(candidate)
        return out if isinstance(out, list) else []
    except Exception:
        return []


def extract_json_object(text: str) -> dict:
    """Best-effort: pull the first JSON object out of an LLM response."""
    if not text:
        return {}
    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
    candidate = fence.group(1) if fence else None
    if candidate is None:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start == -1 or end <= start:
            return {}
        candidate = cleaned[start:end + 1]
    try:
        out = json.loads(candidate)
        return out if isinstance(out, dict) else {}
    except Exception:
        return {}
