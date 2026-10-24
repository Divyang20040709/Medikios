"""
Local LLM Transport (free, no API keys)
────────────────────────────────────────
Talks to a locally-running model server. Two server flavours are supported,
auto-detected:

  1. Ollama          – native /api/chat + /api/tags            (default)
  2. OpenAI-compat   – LM Studio / llama.cpp server etc.
                       /v1/chat/completions + /v1/models

Configuration (backend/app/core/config.py → .env):
  LOCAL_LLM_ENABLED   – master switch (default true)
  OLLAMA_BASE_URL     – default http://127.0.0.1:11434
  OLLAMA_MODEL        – default llama3.2
  LLM_TIMEOUT_SECONDS – per-call generation timeout (default 20)

This module NEVER calls a paid provider and never raises to its callers:
any connection error, timeout or malformed response returns None so the
caller can fall back to predefined, clinically-reviewed content.
"""

import time
import logging
from typing import Any, Dict, List, Optional

import httpx

from backend.app.core.config import settings

logger = logging.getLogger(__name__)

# Availability probe cache (avoid hitting /api/tags on every kiosk turn).
# Module-level so it is shared across requests; tests can reset or force.
_AVAILABILITY_TTL_SECONDS = 60.0
_AVAIL_CACHE: Dict[str, Any] = {"key": None, "flavour": None, "ts": 0.0}


def reset_availability_cache() -> None:
    _AVAIL_CACHE.update({"key": None, "flavour": None, "ts": 0.0})


async def _http_json(
    method: str,
    url: str,
    payload: Optional[Dict[str, Any]] = None,
    timeout: float = 5.0,
) -> Dict[str, Any]:
    """
    Single HTTP seam for the whole module — tests monkeypatch this function
    instead of real networking. Returns parsed JSON dict, or raises
    httpx.HTTPError on transport failure.
    """
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.request(method, url, json=payload)
        resp.raise_for_status()
        return resp.json()


class LocalLLMClient:
    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.base_url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")
        self.model = (model or settings.OLLAMA_MODEL).strip()
        self.enabled = bool(settings.LOCAL_LLM_ENABLED)

    # ── availability ────────────────────────────────────────────────────
    async def probe(self, force: bool = False) -> Optional[str]:
        """
        Detect which server flavour is reachable and whether our model is
        present. Returns "ollama" | "openai" | None (cached briefly).
        """
        if not self.enabled:
            return None
        cache_key = f"{self.base_url}|{self.model}"
        now = time.monotonic()
        if (
            not force
            and _AVAIL_CACHE["key"] == cache_key
            and now - _AVAIL_CACHE["ts"] < _AVAILABILITY_TTL_SECONDS
        ):
            return _AVAIL_CACHE["flavour"]

        flavour: Optional[str] = None
        try:
            tags = await _http_json("GET", f"{self.base_url}/api/tags", timeout=2.5)
            names = [m.get("name", "") for m in tags.get("models", [])]
            # Ollama lists e.g. "llama3.2:latest" — match on the prefix
            if any(n == self.model or n.split(":")[0] == self.model for n in names) or (
                names and any(n.startswith(self.model) for n in names)
            ):
                flavour = "ollama"
            elif names:
                logger.info(
                    f"Ollama reachable but model '{self.model}' not pulled "
                    f"(found: {names[:5]}). Local LLM disabled until provisioned."
                )
        except Exception:
            pass

        if flavour is None:
            try:
                models = await _http_json("GET", f"{self.base_url}/v1/models", timeout=2.5)
                ids = [m.get("id", "") for m in models.get("data", [])]
                if ids:
                    flavour = "openai"
                    if self.model and not any(self.model in i for i in ids):
                        # LM Studio-style servers accept whatever is loaded;
                        # trust the first loaded model over our configured name.
                        self.model = ids[0]
            except Exception:
                flavour = None

        _AVAIL_CACHE.update({"key": cache_key, "flavour": flavour, "ts": now})
        return flavour

    async def is_available(self) -> bool:
        return (await self.probe()) is not None

    # ── generation ──────────────────────────────────────────────────────
    async def chat(
        self,
        messages: List[Dict[str, str]],
        system: Optional[str] = None,
        temperature: float = 0.4,
        max_tokens: int = 500,
        json_mode: bool = False,
        timeout: Optional[float] = None,
    ) -> Optional[str]:
        """
        Run one completion through the local server. Returns the raw text or
        None on any failure (never raises) so callers can use safe fallbacks.
        """
        flavour = await self.probe()
        if flavour is None:
            return None

        gen_timeout = timeout if timeout is not None else float(settings.LLM_TIMEOUT_SECONDS)
        msgs: List[Dict[str, str]] = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend(messages)

        try:
            if flavour == "ollama":
                payload: Dict[str, Any] = {
                    "model": self.model,
                    "messages": msgs,
                    "stream": False,
                    "options": {"temperature": temperature, "num_predict": max_tokens},
                }
                if json_mode:
                    payload["format"] = "json"
                data = await _http_json(
                    "POST", f"{self.base_url}/api/chat", payload=payload, timeout=gen_timeout
                )
                content = (data.get("message") or {}).get("content", "")
            else:
                payload = {
                    "model": self.model,
                    "messages": msgs,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                }
                if json_mode:
                    payload["response_format"] = {"type": "json_object"}
                data = await _http_json(
                    "POST",
                    f"{self.base_url}/v1/chat/completions",
                    payload=payload,
                    timeout=gen_timeout,
                )
                choices = data.get("choices", [])
                content = choices[0].get("message", {}).get("content", "") if choices else ""

            content = (content or "").strip()
            if content:
                return content
            logger.warning("Local LLM returned an empty completion.")
            return None
        except Exception as exc:
            # Timeouts / connection resets are expected on slower CPU inference —
            # stay quiet-ish and let the caller fall back.
            logger.warning(f"Local LLM call failed ({type(exc).__name__}); using fallback.")
            return None
