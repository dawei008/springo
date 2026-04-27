"""
Canvas Tool — read-only inspection of Canvas artifacts.

list / read / state: served directly from the filesystem store (sync, no
bridge, no iframe roundtrip). These three are pure data reads and run
instantly.

query: still goes through the Canvas bridge, because it evaluates a CSS
selector against the live iframe DOM and that only exists in the renderer.

Writes (create / patch / action) are NOT in this tool. They go through the
<springo-artifact op="..."> XML tag emitted in the assistant's message text.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

VALID_ACTIONS = {"list", "read", "state", "query"}

# Reference to the main event loop — only needed for the `query` bridge path.
_main_loop: Optional[asyncio.AbstractEventLoop] = None


def set_main_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Called during app startup to capture the main event loop reference."""
    global _main_loop
    _main_loop = loop


def _error(msg: str) -> Dict[str, Any]:
    return {"success": False, "error": msg}


def _ok(data: Any) -> Dict[str, Any]:
    return {"success": True, "error": "", "data": data}


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
    Inspect the Springo Canvas panel. READ-ONLY.

    Writes go through the <springo-artifact op="create|patch|action"> XML
    tag in the assistant's message text, not through this tool.

    action: one of list | read | state | query
    artifact_id: required for everything except `list`
    path: for `read` — optional; if omitted, returns all files
    selector: for `query` — CSS selector inside the iframe
    timeout: seconds to wait (only relevant for `query`; default 15s)
    """
    if action not in VALID_ACTIONS:
        return _error(
            f"Unknown action '{action}'. Valid (read-only): {', '.join(sorted(VALID_ACTIONS))}. "
            "To create / patch / drive an artifact, emit a "
            "<springo-artifact op=\"create|patch|action\"> tag."
        )

    # ---- Filesystem-served actions (no bridge) --------------------------------
    from api.services import artifact_store

    if action == "list":
        try:
            return _ok({
                "artifacts": artifact_store.list_artifacts(),
                "activeArtifactId": None,
            })
        except Exception as e:
            logger.warning(f"[canvas] list failed: {e}")
            return _error(f"list failed: {e}")

    if action == "read":
        if not artifact_id:
            return _error("action='read' requires artifact_id")
        try:
            if path:
                return _ok(artifact_store.read_file(artifact_id, path))
            return _ok({"files": artifact_store.read_files(artifact_id)})
        except FileNotFoundError as e:
            return _error(str(e))
        except ValueError as e:
            return _error(str(e))

    if action == "state":
        if not artifact_id:
            return _error("action='state' requires artifact_id")
        try:
            # Touch meta to assert existence with a clear error message.
            artifact_store._read_meta(artifact_id)  # type: ignore[attr-defined]
            return _ok({"state": artifact_store.read_state(artifact_id)})
        except FileNotFoundError as e:
            return _error(str(e))

    # ---- Bridge-served action (DOM access required) ---------------------------
    if action == "query":
        if not artifact_id:
            return _error("action='query' requires artifact_id")
        if not selector:
            return _error("action='query' requires selector")

        request_payload: Dict[str, Any] = {
            "action": "query",
            "artifactId": artifact_id,
            "selector": selector,
        }

        if _main_loop is not None and _main_loop.is_running():
            future = asyncio.run_coroutine_threadsafe(
                _call_bridge(request_payload, timeout=timeout), _main_loop
            )
            try:
                return future.result(timeout=timeout + 2)
            except Exception as e:
                return _error(f"canvas bridge failed: {e}")

        logger.warning("[canvas] _main_loop unavailable; query cannot reach renderer")
        return _error("canvas bridge unavailable")

    return _error(f"Unhandled action: {action}")
