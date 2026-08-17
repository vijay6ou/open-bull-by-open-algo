"""
Positions router - GET /web/positions
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool

from backend.dependencies import get_broker_context, BrokerContext
from backend.services.positions_service import get_positions_with_auth

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/web", tags=["positions"])


@router.get("/positions")
async def positions(ctx: BrokerContext = Depends(get_broker_context)):
    """Get open positions from the broker."""
    success, response_data, status_code = await run_in_threadpool(
        get_positions_with_auth,
        ctx.auth_token,
        ctx.broker_name,
        ctx.broker_config,
        ctx.user.id,
    )

    if not success:
        raise HTTPException(status_code=status_code, detail=response_data.get("message", "Failed to fetch positions"))

    return response_data
