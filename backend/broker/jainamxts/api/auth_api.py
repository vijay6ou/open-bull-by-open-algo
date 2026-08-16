"""
Jainam DMA (Symphony) authentication.

Retail XTS on jtrade.jainam.in is a different product. DMA / prop dealer
accounts (OpenAlgo jainam_prop, Apex Fo) use:

  1. POST {BASE}/hostlookup  → uniqueKey + connectionString
  2. POST {interactive}/user/session with appKey, secretKey, uniqueKey, source=WEBAPI
  3. POST {BASE}/apibinarymarketdata/auth/login with market appKey/secret

``clientID`` (e.g. ITC3278A06) is stored on the combined token for dealer calls.
"""

from __future__ import annotations

import logging

import httpx

from backend.broker.jainamxts.baseurl import (
    HOSTLOOKUP_ACCESS_PASSWORD,
    HOSTLOOKUP_VERSION,
    get_base_url,
    get_hostlookup_url,
    get_interactive_url,
    get_market_data_url,
)
from backend.broker.jainamxts.xts_auth import (
    pack_auth,
    pick_trading_client_id,
    resolve_market_keys,
    resolve_order_keys,
)
from backend.utils.httpx_client import get_httpx_client

logger = logging.getLogger(__name__)

SOURCE = "WEBAPI"


def hostlookup() -> tuple[str | None, str | None, str | None]:
    """Return (unique_key, connection_string, error)."""
    url = get_hostlookup_url()
    payloads = [
        {"accesspassword": HOSTLOOKUP_ACCESS_PASSWORD, "version": HOSTLOOKUP_VERSION},
        {"AccessPassword": HOSTLOOKUP_ACCESS_PASSWORD, "version": HOSTLOOKUP_VERSION},
        {"accesspassword": HOSTLOOKUP_ACCESS_PASSWORD, "version": "interactiveapi_1.0.1"},
    ]
    client = get_httpx_client()
    last_error = "Hostlookup failed"
    for payload in payloads:
        try:
            response = client.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=20.0,
            )
            data = response.json()
        except Exception as e:
            last_error = f"Hostlookup error: {e}"
            continue
        result = data.get("result") if isinstance(data, dict) else None
        if not isinstance(result, dict):
            result = {}
        unique = (
            result.get("uniqueKey")
            or result.get("UniqueKey")
            or (data.get("uniqueKey") if isinstance(data, dict) else None)
        )
        conn = result.get("connectionString") or result.get("ConnectionString")
        # Symphony A returns type=True (bool); some SDKs use type="success".
        type_ok = data.get("type") in ("success", True, "true", 1)
        if response.status_code == 200 and unique and (type_ok or conn):
            logger.info("Jainam DMA hostlookup ok (conn=%s)", conn)
            return unique, conn, None
        last_error = (
            (data.get("description") if isinstance(data, dict) else None)
            or (data.get("message") if isinstance(data, dict) else None)
            or f"Hostlookup failed (HTTP {response.status_code})"
        )
    return None, None, last_error


def _interactive_session_url(connection_string: str | None) -> str:
    """Build ``.../user/session`` from hostlookup ``connectionString`` or the default interactive URL."""
    conn = (connection_string or "").strip().rstrip("/")
    if conn:
        if conn.startswith("http://") or conn.startswith("https://"):
            if conn.endswith("/user/session"):
                return conn
            return f"{conn}/user/session"
        if not conn.startswith("/"):
            conn = f"/{conn}"
        return f"{get_base_url()}{conn}/user/session"
    return f"{get_interactive_url()}/user/session"


def get_feed_token(config: dict | None = None) -> tuple[str | None, str | None, str | None]:
    """Login to the Jainam DMA market-data API. Returns (feed_token, user_id, error)."""
    api_key, api_secret = resolve_market_keys(config)
    if not api_key or not api_secret:
        return None, None, (
            "Missing Jainam market-data API key/secret. "
            "Save them on Broker Configuration (or set BROKER_API_KEY_MARKET / "
            "BROKER_API_SECRET_MARKET)."
        )

    payload = {
        "secretKey": api_secret,
        "appKey": api_key,
        "source": SOURCE,
    }
    urls = [
        f"{get_market_data_url()}/auth/login",
        f"{get_base_url()}/apimarketdata/auth/login",
    ]

    client = get_httpx_client()
    last_error = "Market data login failed"
    for url in urls:
        try:
            response = client.post(
                url, json=payload, headers={"Content-Type": "application/json"}, timeout=20.0
            )
            data = response.json()
        except Exception as e:
            last_error = f"Market data login error: {e}"
            logger.warning("Jainam DMA market-data login failed at %s: %s", url, e)
            continue

        if response.status_code == 200 and data.get("type") == "success":
            result = data.get("result") or {}
            token = result.get("token")
            user_id = result.get("userID")
            if token:
                logger.info("Jainam DMA market-data feed token received (%s)", url)
                return token, user_id, None
            last_error = "Market data login succeeded but no token was returned."
            continue

        last_error = (
            data.get("description")
            or data.get("message")
            or f"Market data login failed (HTTP {response.status_code})"
        )
        if response.status_code not in (400, 404):
            break
    return None, None, last_error


def authenticate_broker(code_or_token: str | None, config: dict) -> tuple[str | None, str | None]:
    """Authenticate with Jainam DMA Interactive + Market Data APIs.

    Returns ``(combined_token, error_message)``. Combined token is
    ``interactive:::feed:::user_id:::client_id``.
    """
    api_key, api_secret = resolve_order_keys(config)
    if not api_key or not api_secret:
        return None, (
            "Missing Jainam Order API key/secret. "
            "Save them on Broker Configuration (or set BROKER_API_KEY / BROKER_API_SECRET)."
        )

    unique_key, connection_string, lookup_error = hostlookup()
    if lookup_error or not unique_key:
        logger.warning("Jainam DMA hostlookup failed (%s); trying direct WEBAPI session", lookup_error)

    base_payload = {
        "appKey": api_key,
        "secretKey": api_secret,
        "source": SOURCE,
    }
    extra_token = (code_or_token or "").strip()
    # Retail XTS used a dummy accessToken ("jainamxts"). DMA / Symphony
    # dealer login is WEBAPI + optional uniqueKey from hostlookup.
    if extra_token and extra_token not in ("jainamxts", "jainam_prop", "jainamdma"):
        base_payload["accessToken"] = extra_token

    attempts: list[tuple[str, dict]] = []
    if unique_key:
        with_key = {**base_payload, "uniqueKey": unique_key}
        attempts.append((_interactive_session_url(connection_string), with_key))
    # OpenAlgo jainam_prop / Apex Fo DMA: WEBAPI session without uniqueKey.
    attempts.append((f"{get_interactive_url()}/user/session", dict(base_payload)))

    headers = {"Content-Type": "application/json"}
    last_message = "Authentication failed."

    try:
        client = get_httpx_client()
        for session_url, payload in attempts:
            try:
                response = client.post(session_url, json=payload, headers=headers, timeout=20.0)
                result = response.json()
            except Exception as e:
                last_message = f"Jainam DMA authentication failed: {e}"
                logger.warning("Jainam DMA session error at %s: %s", session_url, e)
                continue

            if response.status_code == 200 and result.get("type") == "success":
                body = result.get("result") or {}
                token = body.get("token")
                session_user = body.get("userID") or ""
                if not token:
                    return None, "Authentication succeeded but no interactive token was returned."

                feed_token, feed_user, feed_error = get_feed_token(config)
                user_id = session_user or feed_user or ""
                client_id = pick_trading_client_id(config, body)
                if feed_error:
                    logger.warning("Jainam DMA interactive login ok; feed token failed: %s", feed_error)
                    return pack_auth(token, "", user_id, client_id), None

                logger.info(
                    "Authenticated Jainam DMA (userID=%s tradingClientID=%s url=%s)",
                    user_id,
                    client_id,
                    session_url,
                )
                return pack_auth(token, feed_token or "", user_id, client_id), None

            last_message = result.get("description") or result.get("message") or "Authentication failed."
            logger.warning(
                "Jainam DMA session failed at %s (HTTP %s): %s",
                session_url,
                response.status_code,
                last_message,
            )

        if lookup_error:
            last_message = f"{last_message} (hostlookup: {lookup_error})"
        return None, f"API error: {last_message}"

    except httpx.RequestError as e:
        logger.exception("HTTP request error during Jainam DMA authentication")
        return None, f"HTTP request error: {e}"
    except Exception as e:
        logger.exception("Unexpected error during Jainam DMA authentication")
        return None, f"Unexpected error during authentication: {e}"
