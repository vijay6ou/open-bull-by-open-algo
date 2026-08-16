"""Shared Jainam XTS token packing and credential resolution.

OpenBull stores a combined auth token so REST + streaming can recover
interactive session, market-data feed token, and XTS userID:

    ``interactive_token:::feed_token:::user_id``

Market API keys live on the per-user BrokerConfig (extra_config) with
OpenAlgo-compatible env fallbacks so the same keys work in both apps.
"""

from __future__ import annotations

import os

TOKEN_SEP = ":::"


def _settings_value(name: str) -> str:
    """Read an optional key from OpenBull Settings (.env via pydantic)."""
    try:
        from backend.config import get_settings

        return str(getattr(get_settings(), name, "") or "")
    except Exception:
        return ""


def pack_auth(interactive_token: str, feed_token: str = "", user_id: str = "") -> str:
    return f"{interactive_token}{TOKEN_SEP}{feed_token}{TOKEN_SEP}{user_id}"


def split_auth(auth_token: str | None) -> tuple[str, str, str]:
    """Return (interactive_token, feed_token, user_id)."""
    raw = auth_token or ""
    if TOKEN_SEP in raw:
        parts = raw.split(TOKEN_SEP)
        interactive = parts[0] if parts else ""
        feed = parts[1] if len(parts) > 1 else ""
        user_id = parts[2] if len(parts) > 2 else ""
        return interactive, feed, user_id
    return raw, "", ""


def _first_nonempty(*values: str | None) -> str:
    for value in values:
        if value:
            return str(value)
    return ""


def resolve_order_keys(config: dict | None) -> tuple[str, str]:
    cfg = config or {}
    api_key = _first_nonempty(
        cfg.get("api_key"),
        _settings_value("jainamxts_api_key"),
        _settings_value("broker_api_key"),
        os.getenv("JAINAMXTS_API_KEY"),
        os.getenv("BROKER_API_KEY"),
    )
    api_secret = _first_nonempty(
        cfg.get("api_secret"),
        _settings_value("jainamxts_api_secret"),
        _settings_value("broker_api_secret"),
        os.getenv("JAINAMXTS_API_SECRET"),
        os.getenv("BROKER_API_SECRET"),
    )
    return api_key, api_secret


def resolve_market_keys(config: dict | None) -> tuple[str, str]:
    cfg = config or {}
    api_key = _first_nonempty(
        cfg.get("api_key_market"),
        _settings_value("jainamxts_api_key_market"),
        _settings_value("broker_api_key_market"),
        os.getenv("JAINAMXTS_API_KEY_MARKET"),
        os.getenv("BROKER_API_KEY_MARKET"),
    )
    api_secret = _first_nonempty(
        cfg.get("api_secret_market"),
        _settings_value("jainamxts_api_secret_market"),
        _settings_value("broker_api_secret_market"),
        os.getenv("JAINAMXTS_API_SECRET_MARKET"),
        os.getenv("BROKER_API_SECRET_MARKET"),
    )
    return api_key, api_secret


def env_order_keys_present() -> bool:
    api_key, api_secret = resolve_order_keys({})
    return bool(api_key and api_secret)
