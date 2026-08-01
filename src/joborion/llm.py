"""Unified LLM client with multi-provider auto-failover.

Auto-detects all configured providers from environment variables.
Supports Gemini, Anthropic Claude, OpenAI, OpenAI-compatible providers
(OpenRouter, DeepSeek, Together, Groq, etc.), and local Ollama/llama.cpp.

Priority order: Gemini (free) -> Anthropic -> OpenAI -> Custom -> Local

Users only paste API keys. Base URLs and models are pre-configured.
"""

from __future__ import annotations

import logging
import os
import time
from abc import ABC, abstractmethod

import httpx

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class BudgetExceeded(Exception):
    """Raised when an LLM call would exceed the configured budget."""


# ---------------------------------------------------------------------------
# Environment variable helpers
# ---------------------------------------------------------------------------

_ENV_ALIASES: dict[str, list[str]] = {
    "GEMINI_API_KEY": ["GOOGLE_API_KEY", "GEMINI_KEY"],
    "GEMINI_MODEL": ["LLM_MODEL_GEMINI"],
    "ANTHROPIC_API_KEY": [],
    "ANTHROPIC_MODEL": [],
    "OPENAI_API_KEY": ["OPENAI_KEY"],
    "OPENAI_BASE_URL": ["OPENAI_API_BASE", "OPENAI_BASE"],
    "OPENAI_MODEL": ["LLM_MODEL_OPENAI", "OPENAI_MODEL_NAME"],
    "CUSTOM_API_KEY": ["DEEPSEEK_API_KEY"],
    "CUSTOM_BASE_URL": ["DEEPSEEK_BASE_URL"],
    "CUSTOM_MODEL": ["DEEPSEEK_MODEL", "LLM_MODEL_CUSTOM"],
    "LLM_URL": ["LOCAL_LLM_URL", "OLLAMA_URL", "LLAMA_URL", "LOCAL_URL"],
    "LLM_MODEL": ["MODEL", "LLM_MODEL_LOCAL", "LOCAL_MODEL"],
    "LLM_API_KEY": ["LOCAL_API_KEY"],
    "LLM_MAX_CALLS": ["MAX_CALLS", "MAX_LLM_CALLS"],
    "LLM_MAX_COST": ["MAX_COST", "MAX_LLM_COST"],
}


def _get_env(name: str, default: str = "") -> str:
    """Get an env var by canonical name, falling back to known aliases."""
    value = os.environ.get(name, "")
    if value:
        return value.strip()
    for alias in _ENV_ALIASES.get(name, []):
        value = os.environ.get(alias, "")
        if value:
            log.warning("Deprecated env var '%s' — use '%s' instead", alias, name)
            return value.strip()
    return default


def _validate_env() -> list[str]:
    """Check for unknown API key env vars and return warning messages."""
    warnings: list[str] = []
    all_valid = set(_ENV_ALIASES.keys())
    for aliases in _ENV_ALIASES.values():
        all_valid.update(aliases)
    for key in os.environ:
        if "_API_" in key or key.endswith("_KEY") or "API_KEY" in key:
            if key not in all_valid:
                warnings.append(
                    f"Unknown env var '{key}' — use GEMINI_API_KEY, "
                    f"ANTHROPIC_API_KEY, OPENAI_API_KEY, or CUSTOM_API_KEY"
                )
    return warnings


# ---------------------------------------------------------------------------
# Provider backends
# ---------------------------------------------------------------------------


class LLMBackend(ABC):
    """Base class for an LLM provider backend.

    Each backend wraps a specific provider's SDK or API format.
    Backends are self-contained and manage their own transport.
    """

    name: str
    model: str

    @abstractmethod
    def chat(self, messages: list[dict], temperature: float, max_tokens: int) -> str:
        """Send messages and return the assistant response text."""

    def count_tokens(self, text: str) -> int:
        """Rough token estimate — override with SDK's counter if available."""
        return len(text.split())


class OpenAICompatBackend(LLMBackend):
    """For any provider that speaks the OpenAI chat completions format.

    Covers: OpenAI, OpenRouter, DeepSeek, Together, Groq, Perplexity, etc.
    """

    def __init__(self, name: str, api_key: str, base_url: str, model: str) -> None:
        self.name = name
        self.model = model
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")

    def chat(self, messages: list[dict], temperature: float, max_tokens: int) -> str:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        with httpx.Client(timeout=120) as client:
            resp = client.post(
                f"{self._base_url}/chat/completions",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]


class GeminiBackend(LLMBackend):
    """Google Gemini via the google.genai SDK."""

    def __init__(self, api_key: str, model: str) -> None:
        from google import genai as genai_module

        self._client = genai_module.Client(api_key=api_key)
        self.name = "gemini"
        self.model = model

    def _convert_messages(
        self, messages: list[dict]
    ) -> tuple[list, str | None]:
        """OpenAI-style messages -> Gemini contents + system instruction."""
        from google.genai import types as genai_types

        contents: list = []
        system_parts: list[str] = []

        for msg in messages:
            role = msg.get("role", "user")
            text = msg.get("content", "")
            if role == "system":
                system_parts.append(text)
            elif role == "user":
                contents.append(
                    genai_types.Content(
                        role="user", parts=[genai_types.Part(text=text)]
                    )
                )
            elif role == "assistant":
                contents.append(
                    genai_types.Content(
                        role="model", parts=[genai_types.Part(text=text)]
                    )
                )

        system_text = "\n".join(system_parts) if system_parts else None
        return contents, system_text

    def chat(self, messages: list[dict], temperature: float, max_tokens: int) -> str:
        from google.genai import types as genai_types

        contents, system_text = self._convert_messages(messages)

        response = self._client.models.generate_content(
            model=self.model,
            contents=contents,
            config=genai_types.GenerateContentConfig(
                temperature=temperature,
                max_output_tokens=max_tokens,
                system_instruction=system_text,
            ),
        )
        return response.text


class AnthropicBackend(LLMBackend):
    """Anthropic Claude via the anthropic SDK."""

    def __init__(self, api_key: str, model: str) -> None:
        import anthropic as anthropic_module

        self._client = anthropic_module.Anthropic(api_key=api_key)
        self.name = "anthropic"
        self.model = model

    @staticmethod
    def _convert_messages(
        messages: list[dict],
    ) -> tuple[list[dict], str | None]:
        """OpenAI-style messages -> Anthropic messages + system prompt."""
        system: str | None = None
        converted: list[dict] = []

        for msg in messages:
            role = msg.get("role", "user")
            text = msg.get("content", "")
            if role == "system":
                system = text
            elif role == "user":
                converted.append({"role": "user", "content": text})
            elif role == "assistant":
                converted.append({"role": "assistant", "content": text})

        return converted, system

    def chat(self, messages: list[dict], temperature: float, max_tokens: int) -> str:
        msgs, system = self._convert_messages(messages)

        kwargs: dict = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": msgs,
        }
        if system:
            kwargs["system"] = system

        response = self._client.messages.create(**kwargs)
        return response.content[0].text


# ---------------------------------------------------------------------------
# Provider detection
# ---------------------------------------------------------------------------


def _detect_providers() -> list[LLMBackend]:
    """Return all configured providers in priority order.

    Reads env vars at call time. Each backend wraps a specific provider's SDK.
    Priority: Gemini (free) -> Anthropic -> OpenAI -> Custom -> Local
    """
    providers: list[LLMBackend] = []

    # 1 — Gemini (free tier, best rate limits for personal use)
    if key := _get_env("GEMINI_API_KEY"):
        model = _get_env("GEMINI_MODEL") or "gemini-2.0-flash"
        try:
            providers.append(GeminiBackend(key, model))
        except ImportError:
            log.warning("GEMINI_API_KEY set but google-genai SDK not installed")

    # 2 — Anthropic Claude
    if key := _get_env("ANTHROPIC_API_KEY"):
        model = _get_env("ANTHROPIC_MODEL") or "claude-sonnet-4-20250514"
        try:
            providers.append(AnthropicBackend(key, model))
        except ImportError:
            log.warning("ANTHROPIC_API_KEY set but anthropic SDK not installed")

    # 3 — OpenAI (or OpenRouter / custom endpoint via OPENAI_BASE_URL)
    if key := _get_env("OPENAI_API_KEY"):
        base = _get_env("OPENAI_BASE_URL") or "https://api.openai.com/v1"
        model = _get_env("OPENAI_MODEL") or "gpt-4o-mini"
        name = "openrouter" if "openrouter" in base.lower() else "openai"
        providers.append(OpenAICompatBackend(name, key, base, model))

    # 4 — Custom OpenAI-compatible (DeepSeek, Together, Groq, etc.)
    if key := _get_env("CUSTOM_API_KEY"):
        base = _get_env("CUSTOM_BASE_URL", "")
        if base:
            model = _get_env("CUSTOM_MODEL") or "gpt-4o-mini"
            providers.append(OpenAICompatBackend("custom", key, base, model))

    # 5 — Local (Ollama / llama.cpp)
    if url := _get_env("LLM_URL"):
        model = _get_env("LLM_MODEL") or "local-model"
        providers.append(
            OpenAICompatBackend("local", _get_env("LLM_API_KEY"), url, model)
        )

    return providers


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

_MAX_RETRIES = 5
_TIMEOUT = 120
_RATE_LIMIT_BASE_WAIT = 10


class LLMClient:
    """Multi-provider LLM client with automatic failover.

    Accepts a list of backends (in priority order). The first backend is used
    initially. On failure (rate limit, timeout, or API error), the client
    automatically falls back to the next configured backend.

    Includes budget enforcement to prevent runaway API costs.
    """

    def __init__(self, backends: list[LLMBackend]) -> None:
        if not backends:
            raise ValueError("At least one provider is required")
        self.backends = backends
        self._backend_index: int = 0
        self._call_count: int = 0
        self._cost_usd: float = 0.0
        self._max_calls_per_run: int = int(_get_env("LLM_MAX_CALLS", "50"))
        self._max_cost_usd: float = float(_get_env("LLM_MAX_COST", "5.0"))
        self._current_run_id: str | None = None

    # -- provider switching ------------------------------------------------

    @property
    def _current(self) -> LLMBackend:
        return self.backends[self._backend_index]

    def _switch_backend(self) -> bool:
        if self._backend_index < len(self.backends) - 1:
            old = self._current
            self._backend_index += 1
            log.info(
                "Failing over: %s -> %s (%s)",
                old.name, self._current.name, self._current.model,
            )
            return True
        return False

    # -- budget -----------------------------------------------------------

    def reset_budget(self) -> None:
        """Reset caller counter, cost tracker, and provider index."""
        self._call_count = 0
        self._cost_usd = 0.0
        self._backend_index = 0

    def set_budget(
        self,
        max_calls: int | None = None,
        max_cost: float | None = None,
        run_id: str | None = None,
    ) -> None:
        """Set budget limits for the current session."""
        if max_calls is not None:
            self._max_calls_per_run = max_calls
        if max_cost is not None:
            self._max_cost_usd = max_cost
        self._current_run_id = run_id

    @property
    def cost_usd(self) -> float:
        """Current accumulated cost in USD."""
        return self._cost_usd

    @property
    def budget_remaining(self) -> float:
        """Remaining budget in USD."""
        return max(0.0, self._max_cost_usd - self._cost_usd)

    # -- chat -------------------------------------------------------------

    def chat(
        self,
        messages: list[dict],
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> str:
        """Send a chat completion and return the assistant message text.

        Automatically fails over to the next provider on errors.
        """
        if self._call_count >= self._max_calls_per_run:
            raise BudgetExceeded(
                f"LLM call budget exhausted: {self._call_count}/{self._max_calls_per_run} "
                f"calls used. Set LLM_MAX_CALLS to increase."
            )
        if self._cost_usd >= self._max_cost_usd:
            raise BudgetExceeded(
                f"LLM cost budget exhausted: ${self._cost_usd:.4f}/${self._max_cost_usd:.2f} "
                f"used. Set LLM_MAX_COST to increase."
            )
        self._call_count += 1

        # Qwen3: skip chain-of-thought
        if "qwen" in self._current.model.lower() and messages:
            first = messages[0]
            if first.get("role") == "user" and not first["content"].startswith("/no_think"):
                messages = [
                    {"role": "user", "content": f"/no_think\n{first['content']}"}
                ] + messages[1:]

        for attempt in range(_MAX_RETRIES):
            try:
                result = self._current.chat(messages, temperature, max_tokens)
                self._record_cost(action="chat", tokens_out=len(result.split()))
                return result

            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                if status in (429, 503):
                    if self._switch_backend():
                        continue
                    if attempt < _MAX_RETRIES - 1:
                        wait = self._backoff_wait(exc.response, attempt)
                        log.warning(
                            "Rate limited (HTTP %s) — all providers exhausted. "
                            "Waiting %ds before retry %d/%d.",
                            status, wait, attempt + 1, _MAX_RETRIES,
                        )
                        time.sleep(wait)
                        self._backend_index = 0
                        continue
                raise

            except (httpx.TimeoutException, httpx.ConnectError):
                if self._switch_backend():
                    continue
                if attempt < _MAX_RETRIES - 1:
                    wait = min(_RATE_LIMIT_BASE_WAIT * (2 ** attempt), 60)
                    log.warning(
                        "Connection error — all providers exhausted. "
                        "Retrying in %ds (attempt %d/%d)",
                        wait, attempt + 1, _MAX_RETRIES,
                    )
                    time.sleep(wait)
                    self._backend_index = 0
                    continue
                raise

            except Exception as exc:
                if self._switch_backend():
                    log.warning(
                        "%s failed: %s — failing over to %s",
                        self.backends[self._backend_index - 1].name,
                        exc, self._current.name,
                    )
                    continue
                raise

        raise RuntimeError("LLM request failed after all retries")

    @staticmethod
    def _backoff_wait(response: httpx.Response, attempt: int) -> float:
        """Extract Retry-After header or compute exponential backoff."""
        retry_after = (
            response.headers.get("Retry-After")
            or response.headers.get("X-RateLimit-Reset-Requests")
        )
        if retry_after:
            try:
                return float(retry_after)
            except (ValueError, TypeError):
                pass
        return min(_RATE_LIMIT_BASE_WAIT * (2 ** attempt), 60)

    def _record_cost(
        self,
        action: str,
        tokens_in: int = 0,
        tokens_out: int = 0,
    ) -> None:
        """Record cost for this call."""
        input_cost = tokens_in * 0.00000015
        output_cost = tokens_out * 0.00000060
        call_cost = input_cost + output_cost
        self._cost_usd += call_cost

        if self._current_run_id:
            try:
                from joborion.database import record_cost

                record_cost(
                    run_id=self._current_run_id,
                    action=action,
                    tool=self._current.model,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    cost_usd=call_cost,
                )
            except Exception:
                pass

    # -- convenience ------------------------------------------------------

    def ask(self, prompt: str, **kwargs: object) -> str:
        """Single user prompt -> assistant response."""
        return self.chat([{"role": "user", "content": prompt}], **kwargs)

    def close(self) -> None:
        """Dispose of resources. No-op — backends manage their own transport."""


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_instance: LLMClient | None = None


def get_client() -> LLMClient:
    """Return (or create) the module-level LLMClient singleton."""
    global _instance
    if _instance is None:
        from joborion.config import load_env

        load_env()
        backends = _detect_providers()
        if not backends:
            raise RuntimeError(
                "No LLM provider configured. "
                "Set GEMINI_API_KEY, ANTHROPIC_API_KEY, or OPENAI_API_KEY "
                "in your .env file."
            )
        log.info(
            "Configured providers: %s",
            ", ".join(f"{b.name} ({b.model})" for b in backends),
        )
        for warning in _validate_env():
            log.warning(".env: %s", warning)
        _instance = LLMClient(backends)
    return _instance
