"""Optional LLM providers (stdlib HTTP only). Nothing here runs unless the user
configures a provider AND confirms the request. Keys come from keystore, never source."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from urllib.parse import urlparse

from . import keystore

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}
PROVIDERS = {
    "none": "No AI model (show matching passages only)",
    "ollama": "Ollama (local)",
    "openai_compat": "OpenAI-compatible API (OpenAI, LM Studio, vLLM, ...)",
    "anthropic": "Anthropic API",
}


class LLMError(Exception):
    pass


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


class Provider:
    name = ""
    base_url = ""
    model = ""

    @property
    def is_external(self) -> bool:
        return _host(self.base_url) not in LOCAL_HOSTS

    def label(self) -> str:
        where = "External service" if self.is_external else "Local model"
        return f"{where}: {self.model or '?'} @ {_host(self.base_url)}"

    def generate(self, system: str, user: str) -> str:  # pragma: no cover
        raise NotImplementedError

    def _post(self, url: str, payload: dict, headers: dict) -> dict:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST",
                                     headers={"Content-Type": "application/json", **headers})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")[:300]
            raise LLMError(f"{self.name} returned HTTP {e.code}: {body}") from e
        except Exception as e:
            raise LLMError(f"Could not reach {self.name} at {self.base_url}: {e}") from e


class Ollama(Provider):
    name = "Ollama"

    def __init__(self, model: str, base_url: str = ""):
        self.model, self.base_url = model, (base_url or "http://localhost:11434").rstrip("/")

    def generate(self, system, user):
        d = self._post(f"{self.base_url}/api/chat", {
            "model": self.model, "stream": False, "options": {"temperature": 0.1},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}, {})
        try:
            return d["message"]["content"].strip()
        except (KeyError, TypeError) as e:
            raise LLMError(f"Unexpected Ollama response: {str(d)[:200]}") from e


class OpenAICompat(Provider):
    name = "OpenAI-compatible API"

    def __init__(self, model: str, base_url: str = ""):
        self.model, self.base_url = model, (base_url or "https://api.openai.com/v1").rstrip("/")

    def generate(self, system, user):
        key = keystore.get_key("openai_compat")
        headers = {"Authorization": f"Bearer {key}"} if key else {}
        if self.is_external and not key:
            raise LLMError("No API key set. Add one in Settings (or set KV_LLM_API_KEY).")
        d = self._post(f"{self.base_url}/chat/completions", {
            "model": self.model, "temperature": 0.1,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}, headers)
        try:
            return d["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError) as e:
            raise LLMError(f"Unexpected response: {str(d)[:200]}") from e


class AnthropicAPI(Provider):
    name = "Anthropic API"

    def __init__(self, model: str, base_url: str = ""):
        self.model, self.base_url = model, (base_url or "https://api.anthropic.com").rstrip("/")

    def generate(self, system, user):
        key = keystore.get_key("anthropic")
        if not key:
            raise LLMError("No API key set. Add one in Settings (or set KV_LLM_API_KEY).")
        d = self._post(f"{self.base_url}/v1/messages", {
            "model": self.model, "max_tokens": 1024, "temperature": 0.1, "system": system,
            "messages": [{"role": "user", "content": user}]},
            {"x-api-key": key, "anthropic-version": "2023-06-01"})
        try:
            return "".join(b.get("text", "") for b in d["content"]).strip()
        except (KeyError, TypeError) as e:
            raise LLMError(f"Unexpected response: {str(d)[:200]}") from e


def make_provider(settings) -> Provider | None:
    kind = settings.llm_provider
    if kind == "none":
        return None
    if not settings.llm_model.strip():
        raise LLMError("Choose a model name in Settings first.")
    cls = {"ollama": Ollama, "openai_compat": OpenAICompat, "anthropic": AnthropicAPI}.get(kind)
    if not cls:
        raise LLMError(f"Unknown provider: {kind}")
    return cls(settings.llm_model.strip(), settings.llm_base_url.strip())
