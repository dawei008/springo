"""
Canvas Bridge

Short-lived request/response channel between the backend (where tools run)
and the Electron renderer (where Canvas artifacts live).

Flow for a tool call:
    1. Tool enqueues a request via `enqueue_request(payload)` → returns an id.
    2. Renderer polls `GET /v1/canvas/pending` → receives the queued request.
    3. Renderer executes against the iframe and POSTs `/v1/canvas/result/{id}`.
    4. Tool resolves via `await_result(id)` which waits on the per-id event.

In-memory only (no disk persistence) because these are ephemeral RPCs.
"""

import asyncio
import logging
import time
import uuid
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class _Pending:
    __slots__ = ("payload", "event", "result", "created_at")

    def __init__(self, payload: Dict[str, Any]):
        self.payload = payload
        self.event = asyncio.Event()
        self.result: Optional[Dict[str, Any]] = None
        self.created_at = time.time()


_queue: List[Dict[str, Any]] = []
_pending: Dict[str, _Pending] = {}
_lock = asyncio.Lock()


async def enqueue_request(payload: Dict[str, Any]) -> str:
    """Queue a Canvas request; return an id the renderer will echo back."""
    req_id = "canvas-" + uuid.uuid4().hex[:12]
    async with _lock:
        _pending[req_id] = _Pending(payload)
        _queue.append({"id": req_id, "payload": payload})
    logger.info(f"[canvas-bridge] Enqueued {req_id} action={payload.get('action')} queue_size={len(_queue)} pending={len(_pending)}")
    return req_id


async def await_result(req_id: str, timeout: float = 15.0) -> Dict[str, Any]:
    """Block until the renderer posts the result, or timeout."""
    pending = _pending.get(req_id)
    if pending is None:
        return {"success": False, "error": f"Unknown canvas request id: {req_id}"}
    try:
        await asyncio.wait_for(pending.event.wait(), timeout=timeout)
        return pending.result or {"success": False, "error": "Empty result"}
    except asyncio.TimeoutError:
        return {
            "success": False,
            "error": (
                f"Canvas request timed out after {timeout:.0f}s. "
                "The renderer may not be polling or the Canvas panel may be closed."
            ),
        }
    finally:
        async with _lock:
            _pending.pop(req_id, None)
            # Also drop from queue if still waiting (shouldn't happen but be safe)
            for i, q in enumerate(_queue):
                if q["id"] == req_id:
                    _queue.pop(i)
                    break


_poll_count = 0

async def drain_queue() -> List[Dict[str, Any]]:
    """Return and clear all pending requests for the renderer."""
    global _poll_count
    async with _lock:
        items = list(_queue)
        _queue.clear()
    _poll_count += 1
    if items:
        logger.info(f"[canvas-bridge] Drained {len(items)} request(s): {[i['id'] for i in items]}")
    elif _poll_count % 20 == 1:  # Log every 10 seconds of empty polls
        logger.debug(f"[canvas-bridge] Poll #{_poll_count}: queue empty, pending={len(_pending)}")
    return items


async def submit_result(req_id: str, result: Dict[str, Any]) -> bool:
    """Called by the renderer once it has executed a request."""
    async with _lock:
        pending = _pending.get(req_id)
    if pending is None:
        logger.warning(f"[canvas-bridge] Result for unknown id {req_id} — dropped (success={result.get('success')})")
        return False
    logger.info(f"[canvas-bridge] Result received for {req_id} (success={result.get('success')})")
    pending.result = result
    pending.event.set()
    return True
