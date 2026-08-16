"""
Jainam XTS authentication.

Dealer/pro login (same as OpenAlgo): exchange stored Order API appKey +
secretKey for an interactive session token, then log into the Market Data
API for a feed token + userID.

``code_or_token`` is unused for the dealer flow (OpenAlgo passes the dummy
string ``"jainamxts"``). If a real callback accessToken is supplied, it is
forwarded as XTS ``accessToken``.
"""

from __future__ import annotations

import logging

import httpx

from backend.broker.jainamxts.baseurl import INTERACTIVE_URL, MARKET_DATA_URL
from backend.broker.jainamxts.xts_auth import pack_auth, resolve_market_keys, resolve_order_keys
from backend.utils.httpx_client import get_httpx_client

logger = logging.getLogger(__name__)


def get_feed_token(config: dict | None = None) -> tuple[str | None, str | None, str | None]:
    """Login to the Jainam market-data API.

    Returns ``(feed_token, user_id, error)``.
    """
    api_key, api_secret = resolve_market_keys(config)
    if not api_key or not api_secret:
        return None, None, (
            "Missing Jainam market-data API key/secret. "
            "Save them on Broker Configuration (or set JAINAMXTS_API_KEY_MARKET / "
            "JAINAMXTS_API_SECRET_MARKET)."
        )

    payload = {
        "secretKey": api_secret,
        "appKey": api_key,
        "source": "WebAPI",
    }
    headers = {"Content-Type": "application/json"}
    url = f"{MARKET_DATA_URL}/auth/login"

    try:
        client = get_httpx_client()
        response = client.post(url, json=payload, headers=headers)
        data = response.json()
    except Exception as e:
        logger.exception("Jainam market-data login failed")
        return None, None, f"Market data login error: {e}"

    if response.status_code == 200 and data.get("type") == "success":
        result = data.get("result") or {}
        token = result.get("token")
        user_id = result.get("userID")
        if token:
            logger.info("Jainam market-data feed token received")
            return token, user_id, None
        return None, None, "Market data login succeeded but no token was returned."

    message = (
        data.get("description")
        or data.get("message")
        or f"Market data login failed (HTTP {response.status_code})"
    )
    return None, None, message


def authenticate_broker(code_or_token: str | None, config: dict) -> tuple[str | None, str | None]:
    """Authenticate with Jainam XTS Interactive + Market Data APIs.

    Returns ``(combined_token, error_message)``. Combined token is
    ``interactive:::feed:::user_id``.
    """
    api_key, api_secret = resolve_order_keys(config)
    if not api_key or not api_secret:
        return None, (
            "Missing Jainam Order API key/secret. "
            "Save them on Broker Configuration (or set JAINAMXTS_API_KEY / JAINAMXTS_API_SECRET)."
        )

    access_token = (code_or_token or "").strip()
    if not access_token:
        access_token = "jainamxts"

    payload = {
        "appKey": api_key,
        "secretKey": api_secret,
        "accessToken": access_token,
    }
    headers = {"Content-Type": "application/json"}
    session_url = f"{INTERACTIVE_URL}/user/session"

    try:
        client = get_httpx_client()
        response = client.post(session_url, json=payload, headers=headers)
        try:
            result = response.json()
        except Exception:
            return None, f"Jainam authentication failed (HTTP {response.status_code})"

        if response.status_code == 200 and result.get("type") == "success":
            token = (result.get("result") or {}).get("token")
            if not token:
                return None, "Authentication succeeded but no interactive token was returned."

            feed_token, user_id, feed_error = get_feed_token(config)
            if feed_error:
                logger.warning("Jainam interactive login ok; feed token failed: %s", feed_error)
                # Interactive session is still usable for orders/funds.
                return pack_auth(token, "", user_id or ""), None

            logger.info("Successfully authenticated with Jainam XTS")
            return pack_auth(token, feed_token or "", user_id or ""), None

        message = result.get("description") or result.get("message") or "Authentication failed."
        return None, f"API error: {message}"

    except httpx.RequestError as e:
        logger.exception("HTTP request error during Jainam authentication")
        return None, f"HTTP request error: {e}"
    except Exception as e:
        logger.exception("Unexpected error during Jainam authentication")
        return None, f"Unexpected error during authentication: {e}"
