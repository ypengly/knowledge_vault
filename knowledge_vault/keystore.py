"""API-key handling. Keys come from the environment, the OS keyring (opt-in),
or are held in memory for the current session only. Never written to disk by us."""
from __future__ import annotations

import os

try:  # optional dependency
    import keyring  # type: ignore
except Exception:  # pragma: no cover
    keyring = None

_SERVICE = "KnowledgeVault"
_session: dict[str, str] = {}


def keyring_available() -> bool:
    return keyring is not None


def get_key(provider: str) -> str:
    env = os.environ.get("KV_LLM_API_KEY") or os.environ.get(f"KV_{provider.upper()}_API_KEY")
    if env:
        return env
    if provider in _session:
        return _session[provider]
    if keyring is not None:
        try:
            return keyring.get_password(_SERVICE, provider) or ""
        except Exception:
            return ""
    return ""


def set_session_key(provider: str, key: str) -> None:
    if key:
        _session[provider] = key
    else:
        _session.pop(provider, None)


def store_in_keyring(provider: str, key: str) -> bool:
    if keyring is None:
        return False
    try:
        keyring.set_password(_SERVICE, provider, key)
        return True
    except Exception:
        return False
