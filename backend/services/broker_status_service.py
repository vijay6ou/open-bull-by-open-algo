"""Live broker session ping — used by the header connection status."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

from backend.utils.plugin_loader import get_broker_module, get_plugin_info

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ping_broker(
    auth_token: str | None,
    broker: str | None,
    config: dict | None = None,
) -> dict[str, Any]:
    """Round-trip the broker. Never raises; always returns a status dict."""
    plugin = get_plugin_info(broker or "") or {}
    display_name = plugin.get("display_name") or broker or ""
    payload: dict[str, Any] = {
        "connected": False,
        "token_valid": True,
        "broker": broker,
        "display_name": display_name,
        "client_id": None,
        "user_id": None,
        "trading_client_id": None,
        "latency_ms": None,
        "message": "Not connected",
        "checked_at": _now_iso(),
    }
    if not broker or not auth_token:
        payload["token_valid"] = False
        payload["message"] = "No broker session"
        return payload

    try:
        auth_mod = get_broker_module(broker, "auth_api")
        if hasattr(auth_mod, "ping_session"):
            result = auth_mod.ping_session(auth_token, config)
            for key in (
                "connected",
                "token_valid",
                "latency_ms",
                "client_id",
                "user_id",
                "trading_client_id",
                "message",
            ):
                if key in result:
                    payload[key] = result[key]
            payload["broker"] = broker
            payload["display_name"] = display_name
            payload["checked_at"] = _now_iso()
            return payload
    except Exception:
        logger.exception("broker ping_session failed for %s; falling back to funds", broker)

    try:
        funds_mod = get_broker_module(broker, "funds")
        started = time.perf_counter()
        margin = funds_mod.get_margin_data(auth_token, config)
        payload["latency_ms"] = int((time.perf_counter() - started) * 1000)
        if margin:
            payload["connected"] = True
            payload["message"] = "pong"
        else:
            payload["message"] = "Broker funds call returned no data"
    except Exception as exc:
        payload["message"] = str(exc)
        logger.warning("broker funds ping failed for %s: %s", broker, exc)

    payload["checked_at"] = _now_iso()
    return payload
