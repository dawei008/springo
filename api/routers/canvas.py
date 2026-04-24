"""
Canvas Router

Short-poll endpoints the Electron renderer uses to pick up and answer
tool requests targeting the live Canvas iframe.
"""

import logging
from typing import Any, Dict, List

from fastapi import APIRouter
from pydantic import BaseModel

from ..services.canvas_bridge import drain_queue, submit_result

logger = logging.getLogger(__name__)

router = APIRouter()


class ResultPayload(BaseModel):
    # Renderer-provided result; shape depends on the action.
    success: bool = True
    error: str = ""
    data: Dict[str, Any] = {}


@router.get("/canvas/pending")
async def list_pending_canvas_requests() -> Dict[str, List[Dict[str, Any]]]:
    """Renderer long-poll endpoint — returns and clears all queued requests."""
    items = await drain_queue()
    return {"requests": items}


@router.post("/canvas/result/{req_id}")
async def post_canvas_result(req_id: str, payload: ResultPayload) -> Dict[str, bool]:
    """Renderer posts the execution result back once it has run a request."""
    ok = await submit_result(req_id, payload.model_dump())
    return {"accepted": ok}
