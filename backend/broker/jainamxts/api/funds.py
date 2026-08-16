"""Jainam XTS funds / RMS balance."""

from __future__ import annotations

import logging

from backend.broker.jainamxts.baseurl import get_interactive_url
from backend.broker.jainamxts.xts_auth import resolve_rms_client_id, split_auth
from backend.utils.httpx_client import get_httpx_client

logger = logging.getLogger(__name__)


def _fmt(value) -> str:
    try:
        if value is None or str(value).lower() == "nan":
            return "0.00"
        return f"{float(value):.2f}"
    except (ValueError, TypeError):
        return "0.00"


def get_margin_data(auth_token: str, config: dict | None = None) -> dict:
    """Fetch margin data. Returns OpenBull funds keys as strings.

    DMA RMS is per dealer *login* user (ITC3278A06), not the parent dealer
    book used for positions (ITC3278). Matches Apex Fo ``/user/balance``.
    """
    interactive, _, _, _ = split_auth(auth_token)
    if not interactive:
        logger.error("Missing Jainam interactive token for funds call")
        return {}

    client_id = resolve_rms_client_id(auth_token, config)
    url = f"{get_interactive_url()}/user/balance"
    if client_id:
        url = f"{url}?clientID={client_id}"
    logger.info("Jainam DMA funds GET %s", url)

    try:
        client = get_httpx_client()
        response = client.get(
            url,
            headers={"authorization": interactive, "Content-Type": "application/json"},
        )
        margin_data = response.json()
    except Exception as e:
        logger.error("Error fetching Jainam funds: %s", e)
        return {}

    result = margin_data.get("result") if isinstance(margin_data, dict) else None
    balance_list = (result or {}).get("BalanceList") or []
    if not balance_list:
        logger.error("Jainam funds response missing BalanceList: %s", margin_data)
        return {}

    rms = (balance_list[0].get("limitObject") or {}).get("RMSSubLimits") or {}
    return {
        "availablecash": _fmt(rms.get("netMarginAvailable")),
        "collateral": _fmt(rms.get("collateral")),
        "m2munrealized": _fmt(rms.get("UnrealizedMTM")),
        "m2mrealized": _fmt(rms.get("RealizedMTM")),
        "utiliseddebits": _fmt(rms.get("marginUtilized")),
    }
