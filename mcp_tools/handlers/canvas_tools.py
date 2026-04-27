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
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

VALID_ACTIONS = {"list", "read", "state", "query"}

# Reference to the main event loop — the Canvas bridge's _pending dict and
# asyncio.Event objects are created on this loop.  We MUST schedule
# enqueue+await on this same loop, otherwise the event.set() from submit_result
# (HTTP handler on main loop) never wakes up our wait() on a different loop.
_main_loop: asyncio.AbstractEventLoop | None = None


def set_main_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Called during app startup to capture the main event loop reference."""
    global _main_loop
    _main_loop = loop


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
    timeout: float = 15.0,
) -> Dict[str, Any]:
    """
    Inspect the Springo Canvas panel. This tool is READ-ONLY.

    Writes (create / modify / drive) go through the <springo-artifact op="..."> XML
    tag emitted in the assistant's message text — not through this tool.

    action: one of list | read | state | query
    artifact_id: required for everything except `list`
    path: for `read` — optional; if omitted, returns all files
    selector: for `query` — CSS selector inside the iframe
    timeout: seconds to wait for the renderer to respond (default 15s)
    """
    if action not in VALID_ACTIONS:
        return _error(
            f"Unknown action '{action}'. Valid (read-only): {', '.join(sorted(VALID_ACTIONS))}. "
            "To create / patch / drive an artifact, emit a <springo-artifact op=\"create|patch|action\"> tag."
        )

    if action != "list" and not artifact_id:
        return _error(f"action='{action}' requires artifact_id")
    if action == "query" and not selector:
        return _error("action='query' requires selector")

    request_payload: Dict[str, Any] = {"action": action}
    if artifact_id:
        request_payload["artifactId"] = artifact_id
    if path is not None:
        request_payload["path"] = path
    if selector is not None:
        request_payload["selector"] = selector

    # Canvas bridge's Event objects live on the main loop — schedule there.
    if _main_loop is not None and _main_loop.is_running():
        future = asyncio.run_coroutine_threadsafe(
            _call_bridge(request_payload, timeout=timeout), _main_loop
        )
        try:
            return future.result(timeout=timeout + 2)
        except Exception as e:
            return _error(f"canvas bridge failed: {e}")

    # Fallback for tests or no-main-loop contexts — won't receive renderer
    # results because submit_result runs on a different loop.
    logger.warning("[canvas] _main_loop unavailable; falling back to fresh loop (renderer results won't arrive)")
    return asyncio.run(_call_bridge(request_payload, timeout=timeout))
