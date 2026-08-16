"""Jainam DMA token packing and credential resolution.

Combined auth token:

    ``interactive_token:::feed_token:::user_id:::client_id``

Split of identities (same as Apex Fo):

* ``user_id`` (part 3) — dealer *login* user / RMS client, e.g. ITC3278A06.
  Used for ``/user/balance`` (available cash, M2M, utilised margin).
* ``client_id`` (part 4) — parent *trading* client from session
  ``clientCodes[0]``, e.g. ITC3278. Used for dealer position/order books.
  Dealer books are empty when queried with the login user id.
"""

from __future__ import annotations

import os
import re

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


_DEALER_USER_SUFFIX = re.compile(r"^([A-Z]{2,}\d+)[A-Z]\d{2}$")


def strip_dealer_user_suffix(client_id: str | None) -> str:
    """ITC3278A06 (dealer login user) -> ITC3278 (trading client)."""
    raw = (client_id or "").strip()
    match = _DEALER_USER_SUFFIX.match(raw)
    return match.group(1) if match else ""


def pick_trading_client_id(config: dict | None, session_result: dict | None = None) -> str:
    """Prefer session clientCodes[0]; else strip dealer-user suffix from env id."""
    result = session_result or {}
    codes = result.get("clientCodes") or result.get("ClientCodes") or []
    if isinstance(codes, list) and codes:
        code = str(codes[0]).strip()
        if code:
            return code
    configured = resolve_client_id(config)
    return strip_dealer_user_suffix(configured) or configured


def is_dealer_login_user(client_id: str | None) -> bool:
    """True for DMA login users like ITC3278A06 (not parent book ITC3278)."""
    return bool(strip_dealer_user_suffix(client_id))


def resolve_rms_client_id(auth_token: str | None, config: dict | None = None) -> str:
    """clientID for ``/user/balance``.

    RMS figures (available cash, M2M, utilised debits) belong to the dealer
    login user (ITC3278A06), not the parent trading book packed as token
    part 4 (ITC3278). Prefer a dealer-user form from the packed session
    ``userID`` or ``JAINAMXTS_CLIENT_ID``; never the trading client.
    """
    _, _, user_id, _ = split_auth(auth_token)
    configured = resolve_client_id(config)
    for cid in (user_id, configured):
        if is_dealer_login_user(cid):
            return cid
    return user_id or configured


def dealer_client_candidates(auth_token: str | None) -> list[str | None]:
    """clientIDs to try for dealer books. Last entry None omits the param."""
    packed = split_auth(auth_token)[3]
    seen: set[str] = set()
    out: list[str | None] = []
    for cid in (packed, strip_dealer_user_suffix(packed), resolve_client_id({})):
        if cid and cid not in seen:
            seen.add(cid)
            out.append(cid)
        stripped = strip_dealer_user_suffix(cid) if cid else ""
        if stripped and stripped not in seen:
            seen.add(stripped)
            out.append(stripped)
    out.append(None)
    return out


def env_order_keys_present() -> bool:
    api_key, api_secret = resolve_order_keys({})
    return bool(api_key and api_secret)
