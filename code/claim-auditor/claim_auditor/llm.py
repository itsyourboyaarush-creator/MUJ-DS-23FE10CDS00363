"""Thin Anthropic client: retries with backoff, JSON parsing/repair, disk cache, usage stats."""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)


class LLMError(RuntimeError):
    pass


@dataclass
class Usage:
    calls: int = 0
    cache_hits: int = 0
    input_tokens: int = 0
    output_tokens: int = 0


def _retryable(exc: Exception) -> bool:
    status = getattr(exc, "status_code", None) or getattr(exc, "code", None)  # anthropic / google-genai
    if isinstance(status, int):
        return status == 429 or status >= 500
    return type(exc).__name__ in {"APIConnectionError", "APITimeoutError"}


def parse_json(text: str) -> dict:
    """Parse a JSON object from model output, tolerating fences and stray prose."""
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("\n") + 1:] if "\n" in text else text
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object found")
    return json.loads(text[start:end + 1])


class LLMClient:
    def __init__(self, model: str, max_tokens: int = 2000, temperature: float = 0.2,
                 max_retries: int = 3, timeout_s: float = 60,
                 cache_dir: str | Path | None = None, client=None,
                 provider: str = "anthropic"):
        if provider not in ("anthropic", "gemini"):
            raise ValueError(f"unknown provider: {provider!r} (use 'anthropic' or 'gemini')")
        self.provider = provider
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.max_retries = max_retries
        self.cache_dir = Path(cache_dir) if cache_dir else None
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        if client is None:  # SDKs are imported lazily so tests need no SDK/key
            if provider == "gemini":
                from google import genai
                from google.genai import types
                client = genai.Client(http_options=types.HttpOptions(timeout=int(timeout_s * 1000)))
            else:
                import anthropic
                client = anthropic.Anthropic(timeout=timeout_s, max_retries=0)
        self._client = client
        self.usage = Usage()
        self._lock = threading.Lock()

    # -- provider request: returns (text, input_tokens, output_tokens) ------
    def _request(self, system: str, user: str) -> tuple[str, int, int]:
        if self.provider == "gemini":
            from google.genai import types
            resp = self._client.models.generate_content(
                model=self.model, contents=user,
                config=types.GenerateContentConfig(
                    system_instruction=system, temperature=self.temperature,
                    max_output_tokens=self.max_tokens,
                    response_mime_type="application/json",
                    # 2.5 Flash "thinking" tokens would eat max_output_tokens; extraction doesn't need them
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                ),
            )
            meta = resp.usage_metadata
            return (resp.text or "", getattr(meta, "prompt_token_count", 0) or 0,
                    getattr(meta, "candidates_token_count", 0) or 0)
        resp = self._client.messages.create(
            model=self.model, max_tokens=self.max_tokens,
            temperature=self.temperature, system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(b.text for b in resp.content if b.type == "text")
        return text, resp.usage.input_tokens, resp.usage.output_tokens

    # -- raw call -----------------------------------------------------------
    def _call(self, system: str, user: str) -> str:
        for attempt in range(self.max_retries + 1):
            try:
                text, tin, tout = self._request(system, user)
                with self._lock:
                    self.usage.calls += 1
                    self.usage.input_tokens += tin
                    self.usage.output_tokens += tout
                return text
            except Exception as exc:  # noqa: BLE001
                if attempt == self.max_retries or not _retryable(exc):
                    raise LLMError(f"LLM call failed: {exc}") from exc
                delay = 2 ** attempt
                log.warning("retryable error (%s); retrying in %ss", exc, delay)
                time.sleep(delay)
        raise LLMError("unreachable")

    # -- cache --------------------------------------------------------------
    def _key(self, system: str, user: str) -> Path | None:
        if not self.cache_dir:
            return None
        h = hashlib.sha256(f"{self.model}\0{system}\0{user}".encode()).hexdigest()
        return self.cache_dir / f"{h}.json"

    # -- public -------------------------------------------------------------
    def complete_json(self, system: str, user: str) -> dict:
        """Return a parsed JSON object; one repair attempt if the reply is malformed."""
        path = self._key(system, user)
        if path and path.exists():
            with self._lock:
                self.usage.cache_hits += 1
            return json.loads(path.read_text(encoding="utf-8"))

        raw = self._call(system, user)
        try:
            data = parse_json(raw)
        except ValueError:  # JSONDecodeError subclasses ValueError
            log.warning("malformed JSON from model, requesting repair")
            repair = (f"{user}\n\nYour previous reply was not valid JSON:\n{raw[:500]}\n"
                      "Reply again with ONLY the JSON object.")
            try:
                data = parse_json(self._call(system, repair))
            except ValueError as exc:
                raise LLMError("model did not return valid JSON") from exc

        if path:
            path.write_text(json.dumps(data), encoding="utf-8")
        return data
