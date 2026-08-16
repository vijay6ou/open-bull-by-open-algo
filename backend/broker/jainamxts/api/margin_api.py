"""Jainam XTS does not expose a pre-trade margin calculator."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class _MockResponse:
    def __init__(self, status_code: int):
        self.status_code = status_code
        self.status = status_code


def calculate_margin_api(positions: list[dict], auth: str):
    logger.warning("Jainam XTS does not provide a margin calculator API")
    return _MockResponse(501), {
        "status": "error",
        "message": "Jainam XTS does not support a margin calculator API",
    }
