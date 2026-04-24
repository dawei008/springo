"""
Canvas Tool

Operate on Springo's Canvas panel through the renderer bridge. See the
`canvas` skill (~/.springo/skills/canvas/SKILL.md) for the decision tree
on when to use this tool vs <springo-patch>/<springo-action>/etc.

All actions are thin wrappers that enqueue a request for the renderer,
await its response, and surface it to the assistant as a tool_result.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

VALID_ACTIONS = {"list", "read", "state", "query", "patch", "dispatch"}


def _error(msg: str) -> Dict[str, Any]:
    return {"success": False, "error": msg}


async def _call_bridge(payload: Dict[str, Any], timeout: float = 15.0) -> Dict[str, Any]:
    """Enqueue a request and await the renderer's response."""
    from api.services.canvas_bridge import enqueue_request, await_result

    req_id = await enqueue_request(payload)
    return await await_result(req_id, timeout=timeout)


def canvas(
    action: str,
    artifact_id: Optional[str] = None,
    path: Optional[str] = None,
    selector: Optional[str] = None,
    files: Optional[List[Dict[str, Any]]] = None,
    payload: Optional[Dict[str, Any]] = None,
    timeout: float = 15.0,
) -> Dict[str, Any]:
    """
    Operate on the Springo Canvas panel.

    action: one of list | read | state | query | patch | dispatch
    artifact_id: required for everything except `list`
    path: for `read` — optional; if omitted, returns all files
    selector: for `query` and `dispatch` — CSS selector inside the iframe
    files: for `patch` — [{path, action: replace|create|delete, content, file_type}]
    payload: for arbitrary extra data (unused for now)
    timeout: seconds to wait for the renderer to respond (default 15s)
    """
    if action not in VALID_ACTIONS:
        return _error(
            f"Unknown action '{action}'. Valid: {', '.join(sorted(VALID_ACTIONS))}"
        )

    if action != "list" and not artifact_id:
        return _error(f"action='{action}' requires artifact_id")
    if action == "query" and not selector:
        return _error("action='query' requires selector")
    if action == "dispatch" and not selector:
        return _error("action='dispatch' requires selector")
    if action == "patch" and not files:
        return _error("action='patch' requires files=[{path, action, content, file_type}]")

    request_payload: Dict[str, Any] = {"action": action}
    if artifact_id:
        request_payload["artifactId"] = artifact_id
    if path is not None:
        request_payload["path"] = path
    if selector is not None:
        request_payload["selector"] = selector
    if files is not None:
        request_payload["files"] = files
    if payload is not None:
        request_payload["payload"] = payload

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # We're inside an already-running loop — the tool dispatcher
            # runs us in a thread executor, so just await the coroutine on
            # a fresh loop.
            return asyncio.run_coroutine_threadsafe(
                _call_bridge(request_payload, timeout=timeout), loop
            ).result(timeout=timeout + 2)
    except RuntimeError:
        pass
    return asyncio.run(_call_bridge(request_payload, timeout=timeout))
