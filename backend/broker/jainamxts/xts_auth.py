"""Jainam DMA token packing and credential resolution.

Combined auth token:

    ``interactive_token:::feed_token:::user_id:::client_id``

DMA dealer calls need ``clientID`` (e.g. ITC3278A06) on every interactive
request. Market + order keys fall back to OpenAlgo ``BROKER_API_KEY*`` names.
"""

from __future__ import annotations

import os

TOKEN_SEP = ":::"


def _settings_value(name: str) -> str:
    try:
        from backend.config import get_settings

        return str(getattr(get_settings(), name, "") or "")
    except Exception:
        return ""


def pack_auth(
    interactive_token: str,
    feed_token: str = "",
    user_id: str = "",
    client_id: str = "",
) -> str:
    return (
        f"{interactive_token}{TOKEN_SEP}{feed_token}"
        f"{TOKEN_SEP}{user_id}{TOKEN_SEP}{client_id}"
    )


def split_auth(auth_token: str | None) -> tuple[str, str, str, str]:
    """Return (interactive_token, feed_token, user_id, client_id)."""
    raw = auth_token or ""
    if TOKEN_SEP in raw:
        parts = raw.split(TOKEN_SEP)
        interactive = parts[0] if parts else ""
        feed = parts[1] if len(parts) > 1 else ""
        user_id = parts[2] if len(parts) > 2 else ""
        client_id = parts[3] if len(parts) > 3 else ""
        return interactive, feed, user_id, client_id
    return raw, "", "", ""


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


def resolve_client_id(config: dict | None) -> str:
    cfg = config or {}
    return _first_nonempty(
        cfg.get("client_id"),
        _settings_value("jainamxts_client_id"),
        os.getenv("JAINAMXTS_CLIENT_ID"),
        os.getenv("JAINAM_SYMPHONY_A_PRO_CLIENT_ID"),
        os.getenv("JAINAM_SYMPHONY_A_NORMAL_CLIENT_ID"),
    )


def env_order_keys_present() -> bool:
    api_key, api_secret = resolve_order_keys({})
    return bool(api_key and api_secret)
