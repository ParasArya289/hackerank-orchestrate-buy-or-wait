"""Thin HTTP client wrapper around a local Ollama server.

No API keys/secrets involved (local, unauthenticated Ollama daemon).
OLLAMA_HOST may optionally be set via environment variable to point at a
non-default host; defaults to the standard local address. Per AGENTS.md
6.4, secrets (if any existed) would only ever come from environment
variables -- there are none here, but the host is still overridable via
env var rather than hardcoded, for portability across machines.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

_DEFAULT_HOST = "http://localhost:11434"
_DEFAULT_TIMEOUT_SECONDS = 120


class OllamaError(RuntimeError):
    """Raised when the local Ollama server is unreachable or returns an error."""


@dataclass
class UsageRecord:
    """One logged model call, for the Phase 4 usage_report.md accounting."""

    model: str
    call_type: str  # "vision_extract" | "text_interpret" | "explain"
    prompt_tokens: int
    completion_tokens: int
    duration_seconds: float


@dataclass
class OllamaClient:
    host: str = field(default_factory=lambda: os.environ.get("OLLAMA_HOST", _DEFAULT_HOST))
    timeout_seconds: int = _DEFAULT_TIMEOUT_SECONDS
    usage_log: list[UsageRecord] = field(default_factory=list)
    _cache: dict = field(default_factory=dict, repr=False)

    def generate(
        self,
        model: str,
        prompt: str,
        images: list[str] | None = None,
        temperature: float = 0.0,
        call_type: str = "text_interpret",
    ) -> str:
        """Call POST /api/generate with a single-turn prompt (optionally
        with base64-encoded images for a vision model). Returns the raw
        text response. Records token usage for later cost reporting.

        Deterministic (temperature=0.0) calls are memoized in-process by
        (model, prompt, image-count) so re-running the same message/image
        through the pipeline (e.g. the same message shared by multiple
        requests for one user, or repeated test invocations) doesn't
        re-pay the ~20-30s local-model latency. Each cache hit still
        appends a usage_log record (with duration_seconds=0.0) so the
        Phase 4 usage report reflects true call counts, not just
        wall-clock-billed calls.
        """
        cache_key = None
        if temperature == 0.0:
            image_fingerprint = len(images) if images else 0
            cache_key = (model, prompt, image_fingerprint)
            if cache_key in self._cache:
                cached_response, cached_prompt_tokens, cached_completion_tokens = self._cache[cache_key]
                self.usage_log.append(
                    UsageRecord(
                        model=model,
                        call_type=call_type,
                        prompt_tokens=cached_prompt_tokens,
                        completion_tokens=cached_completion_tokens,
                        duration_seconds=0.0,
                    )
                )
                return cached_response

        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature},
        }
        if images:
            payload["images"] = images

        url = f"{self.host}/api/generate"
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url, data=data, headers={"Content-Type": "application/json"}
        )

        t0 = time.time()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
            raise OllamaError(
                f"Ollama call failed (model={model}, host={self.host}): {exc}"
            ) from exc
        duration = time.time() - t0

        prompt_tokens = int(body.get("prompt_eval_count", 0) or 0)
        completion_tokens = int(body.get("eval_count", 0) or 0)
        response_text = str(body.get("response", ""))

        self.usage_log.append(
            UsageRecord(
                model=model,
                call_type=call_type,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                duration_seconds=duration,
            )
        )

        if cache_key is not None:
            self._cache[cache_key] = (response_text, prompt_tokens, completion_tokens)

        return response_text


_default_client: OllamaClient | None = None


def get_default_client() -> OllamaClient:
    """Module-level singleton so all call sites share one usage_log for
    the Phase 4 usage_report.md accounting."""
    global _default_client
    if _default_client is None:
        _default_client = OllamaClient()
    return _default_client
