"""Jainam DMA (Symphony) base URLs.

Retail/pro XTS is jtrade.jainam.in:5000. DMA / prop dealer accounts use
the Symphony hosts instead:

    A: https://smpa.jainam.in:6543
    B: https://smpb.jainam.in:4143
    C: https://smpc.jainam.in:14543

Override with JAINAM_BASE_URL. Default is Symphony A as used by OpenAlgo
jainam_prop / Apex Fo DMA logins.
"""

from __future__ import annotations

import os

SYMPHONY_SERVERS = {
    "A": "https://smpa.jainam.in:6543",
    "B": "https://smpb.jainam.in:4143",
    "C": "https://smpc.jainam.in:14543",
}

DEFAULT_BASE_URL = SYMPHONY_SERVERS["A"]
HOSTLOOKUP_ACCESS_PASSWORD = "2021HostLookUpAccess"
HOSTLOOKUP_VERSION = "interactive_1.0.1"


def _settings_value(name: str) -> str:
    try:
        from backend.config import get_settings

        return str(getattr(get_settings(), name, "") or "")
    except Exception:
        return ""


def get_base_url() -> str:
    server = (
        _settings_value("jainam_active_symphony_server")
        or os.getenv("JAINAM_ACTIVE_SYMPHONY_SERVER")
        or ""
    ).strip().upper()
    if server in SYMPHONY_SERVERS:
        return SYMPHONY_SERVERS[server]
    explicit = (
        _settings_value("jainam_base_url")
        or os.getenv("JAINAM_BASE_URL")
        or DEFAULT_BASE_URL
    )
    return explicit.rstrip("/")


def get_hostlookup_url() -> str:
    return f"{get_base_url()}/hostlookup"


def get_interactive_url() -> str:
    return f"{get_base_url()}/interactive"


def get_market_data_url() -> str:
    return f"{get_base_url()}/apibinarymarketdata"


# Import-time aliases (re-read via the getters at call time when possible).
BASE_URL = DEFAULT_BASE_URL
HOSTLOOKUP_URL = f"{DEFAULT_BASE_URL}/hostlookup"
INTERACTIVE_URL = f"{DEFAULT_BASE_URL}/interactive"
MARKET_DATA_URL = f"{DEFAULT_BASE_URL}/apibinarymarketdata"
