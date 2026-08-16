"""
Dashboard router - GET /web/dashboard (funds overview).
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool

from backend.dependencies import get_broker_context, BrokerContext
from backend.services.funds_service import get_funds_with_auth

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/web", tags=["dashboard"])


@router.get("/dashboard")
async def dashboard(ctx: BrokerContext = Depends(get_broker_context)):
    """Get dashboard data including funds/margin information."""
    success, response_data, status_code = await run_in_threadpool(
        get_funds_with_auth,
        ctx.auth_token,
        ctx.broker_name,
        ctx.broker_config,
        ctx.user.id,
    )

    if not success:
        raise HTTPException(status_code=status_code, detail=response_data.get("message", "Failed to fetch funds"))

    return response_data
