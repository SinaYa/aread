"""Minimal LM Studio (OpenAI-compatible) client using only the stdlib.

The key trick for this tool: when several chat-completion requests share an
identical leading prefix (here: the system message carrying the file content),
LM Studio reuses its prefill / KV cache for that prefix. So we read & prefill
the file exactly once, then run each task as its own completion that reuses the
cache. Each task gets an independent answer with no cross-contamination.
"""

from __future__ import annotations

import json
from urllib import error as urlerror
from urllib import request as urlrequest


def normalize_base_url(base_url: str) -> str:
    trimmed = base_url.strip().rstrip("/")
    if not trimmed:
        raise ValueError("LM Studio base URL is required.")
    return trimmed if trimmed.endswith("/v1") else f"{trimmed}/v1"


def _native_root(base_url: str) -> str:
    """Host root for LM Studio's native REST API (strip the OpenAI '/v1')."""
    trimmed = base_url.strip().rstrip("/")
    if trimmed.endswith("/v1"):
        trimmed = trimmed[:-3]
    return trimmed.rstrip("/")


def get_loaded_models(base_url: str, timeout: float) -> list[dict]:
    """Return the currently loaded models with their loaded context length.

    Each item: {"id": str, "loaded_context_length": int|None,
    "max_context_length": int|None}. Empty list if none loaded or unreachable.
    """
    url = f"{_native_root(base_url)}/api/v0/models"
    req = urlrequest.Request(url, method="GET")
    try:
        with urlrequest.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (urlerror.URLError, ValueError):
        return []
    return [
        {
            "id": entry.get("id"),
            "loaded_context_length": entry.get("loaded_context_length"),
            "max_context_length": entry.get("max_context_length"),
        }
        for entry in (payload.get("data") or [])
        if entry.get("state") == "loaded"
    ]


def get_loaded_context_length(
    base_url: str, timeout: float, model: str | None = None
) -> int | None:
    """Return the context length the loaded model was actually loaded with.

    Uses LM Studio's native /api/v0/models endpoint, which (unlike the
    OpenAI-compatible /v1) reports `loaded_context_length` — the real, possibly
    user-lowered window for a model loaded in the UI. Returns None if the
    endpoint is unreachable or doesn't report it (caller falls back to config).
    """
    url = f"{_native_root(base_url)}/api/v0/models"
    req = urlrequest.Request(url, method="GET")
    try:
        with urlrequest.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (urlerror.URLError, ValueError):
        return None

    loaded = [
        entry
        for entry in (payload.get("data") or [])
        if entry.get("state") == "loaded" and entry.get("loaded_context_length")
    ]
    if not loaded:
        return None
    if model:
        for entry in loaded:
            if entry.get("id") == model:
                return int(entry["loaded_context_length"])
    return int(loaded[0]["loaded_context_length"])


class LMStudioError(RuntimeError):
    """Raised when LM Studio is unreachable or returns an error."""


class ContextOverflowError(LMStudioError):
    """Raised when the input exceeds the model's context window.

    Some models/runtimes return an explicit error for this (rather than
    silently truncating), e.g. "n_keep >= n_ctx ... provide a shorter input".
    """


def _looks_like_context_overflow(detail: str) -> bool:
    low = detail.lower()
    return any(
        marker in low
        for marker in ("n_keep", "n_ctx", "context length", "context window", "shorter input")
    )


def list_models(base_url: str, timeout: float) -> list[str]:
    url = f"{normalize_base_url(base_url)}/models"
    req = urlrequest.Request(url, method="GET")
    try:
        with urlrequest.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urlerror.URLError as exc:
        raise LMStudioError(
            f"Could not reach LM Studio at {url}. Is the server running "
            f"(LM Studio > Developer > Start Server)? Details: {exc}"
        ) from exc
    data = payload.get("data") or []
    return [entry["id"] for entry in data if entry.get("id")]


def resolve_model(model: str, use_loaded: bool, base_url: str, timeout: float) -> str:
    """Return the model id to use, honoring the 'auto'/loaded preference."""
    if not use_loaded:
        return model
    models = list_models(base_url, timeout)
    if not models:
        raise LMStudioError(
            "Config requested the currently-loaded model ('auto'), but LM Studio "
            "reports no loaded models. Load a model in the LM Studio UI first."
        )
    return models[0]


def chat_completion(
    *,
    base_url: str,
    model: str,
    system: str,
    user: str,
    temperature: float,
    timeout: float,
) -> dict:
    """Run a single non-streaming chat completion.

    Returns {"text": str, "prompt_tokens": int|None, "completion_tokens": int|None}.
    `prompt_tokens` is how many input tokens LM Studio actually prefilled — used
    by the caller to detect that the input was truncated to fit the context.
    """
    url = f"{normalize_base_url(base_url)}/chat/completions"
    body = json.dumps(
        {
            "model": model,
            "temperature": temperature,
            "stream": False,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
    ).encode("utf-8")

    req = urlrequest.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlrequest.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urlerror.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        if _looks_like_context_overflow(detail):
            raise ContextOverflowError(detail) from exc
        raise LMStudioError(f"LM Studio request failed ({exc.code}): {detail}") from exc
    except urlerror.URLError as exc:
        raise LMStudioError(
            f"Could not reach LM Studio at {url}. Is the server running? Details: {exc}"
        ) from exc

    usage = payload.get("usage") or {}
    prompt_tokens = usage.get("prompt_tokens")
    completion_tokens = usage.get("completion_tokens")

    choices = payload.get("choices") or []
    if not choices:
        raise LMStudioError("LM Studio returned no choices.")
    message = choices[0].get("message") or {}
    content = (message.get("content") or "").strip()
    reasoning = (message.get("reasoning_content") or "").strip()
    text = content or reasoning
    if not text:
        if choices[0].get("finish_reason") == "length":
            raise LMStudioError(
                "LM Studio hit the token limit before answering. "
                "Increase the timeout or shorten the task."
            )
        raise LMStudioError("LM Studio returned no answer text.")
    return {
        "text": text,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
    }
