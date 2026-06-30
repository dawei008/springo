"""
Browser Bridge Service

Maintains a WebSocket link to the Springo Chrome extension running inside the
user's *real* Chrome and dispatches browser-automation commands to it.

This is the extension-based counterpart to the CDP/Playwright path: instead of
driving a throwaway Chrome on a debug port, the extension attaches
`chrome.debugger` to a tab in the user's signed-in Chrome and runs CDP commands
there. The backend is the WS *server*; the extension dials in as a client.

Only one extension connection is held at a time (the most recent wins). Tool
handlers call `send_command(...)` from a ThreadPoolExecutor thread; it schedules
the actual send on the main event loop and blocks on the reply, matched by a
monotonic message id.
"""

import asyncio
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class BrowserBridge:
    """Singleton bridge between backend tool handlers and the Chrome extension."""

    def __init__(self) -> None:
        self._ws = None  # the connected extension WebSocket (Starlette WebSocket)
        self._main_loop: Optional[asyncio.AbstractEventLoop] = None
        self._next_id = 0
        self._pending: Dict[int, asyncio.Future] = {}
        self._client_info: Dict[str, Any] = {}

    # -- lifecycle ---------------------------------------------------------

    def set_main_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Capture the main event loop (called once during app startup)."""
        self._main_loop = loop

    def attach(self, ws, client_info: Optional[Dict[str, Any]] = None):
        """Register a freshly-connected extension socket.

        Newest wins, but we return the displaced socket (if any) so the caller
        can close it — otherwise the old extension's receive loop lingers and a
        transient/duplicate connection (e.g. a diagnostic probe) can silently
        orphan the real extension.
        """
        displaced = self._ws if self._ws is not ws else None
        self._ws = ws
        self._client_info = client_info or {}
        # Fail any in-flight requests from a previous connection.
        self._fail_pending("extension reconnected")
        logger.info("Browser extension attached: %s", self._client_info)
        return displaced

    def detach(self, ws) -> None:
        """Deregister a socket on disconnect (only if it's the current one)."""
        if self._ws is ws:
            self._ws = None
            self._client_info = {}
            self._fail_pending("extension disconnected")
            logger.info("Browser extension detached")

    def is_connected(self) -> bool:
        return self._ws is not None

    def status(self) -> Dict[str, Any]:
        return {
            "connected": self.is_connected(),
            "client": self._client_info,
            "pending": len(self._pending),
        }

    # -- message handling --------------------------------------------------

    def resolve(self, message: Dict[str, Any]) -> None:
        """Called on the main loop when the extension sends a reply frame.

        Expected shape: {"id": <int>, "result": {...}} or {"id": <int>, "error": "..."}.
        """
        msg_id = message.get("id")
        if msg_id is None:
            return
        future = self._pending.pop(msg_id, None)
        if future is None or future.done():
            return
        if "error" in message and message["error"]:
            future.set_result({"error": message["error"]})
        else:
            future.set_result(message.get("result", {}))

    def _fail_pending(self, reason: str) -> None:
        for fut in self._pending.values():
            if not fut.done():
                fut.set_result({"error": f"Browser bridge: {reason}"})
        self._pending.clear()

    # -- public API for tool handlers (called from worker threads) ---------

    def send_command(self, action: str, params: Optional[Dict[str, Any]] = None,
                     timeout: float = 30.0) -> Dict[str, Any]:
        """Send a command to the extension and block until it replies.

        Safe to call from a ThreadPoolExecutor thread — it schedules the send on
        the main loop and waits on the result there.
        """
        if self._main_loop is None or not self._main_loop.is_running():
            return {"error": "Browser bridge not initialized (no main loop)"}
        if not self.is_connected():
            return {
                "error": "Springo Chrome extension is not connected. Install/enable "
                         "the extension and click Connect in its popup."
            }

        coro = self._send_and_wait(action, params or {}, timeout)
        try:
            cf = asyncio.run_coroutine_threadsafe(coro, self._main_loop)
            # Give the cross-thread future a little headroom over the inner timeout.
            return cf.result(timeout=timeout + 5)
        except Exception as e:  # noqa: BLE001 — surface any failure as a tool error
            return {"error": f"Browser command failed: {e}"}

    async def _send_and_wait(self, action: str, params: Dict[str, Any],
                             timeout: float) -> Dict[str, Any]:
        if self._ws is None:
            return {"error": "Extension disconnected"}
        self._next_id += 1
        msg_id = self._next_id
        future: asyncio.Future = self._main_loop.create_future()
        self._pending[msg_id] = future
        try:
            await self._ws.send_json({"id": msg_id, "action": action, "params": params})
        except Exception as e:  # noqa: BLE001
            self._pending.pop(msg_id, None)
            return {"error": f"Failed to send to extension: {e}"}
        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            self._pending.pop(msg_id, None)
            return {"error": f"Extension did not respond within {timeout}s for '{action}'"}


_bridge: Optional[BrowserBridge] = None


def get_browser_bridge() -> BrowserBridge:
    global _bridge
    if _bridge is None:
        _bridge = BrowserBridge()
    return _bridge
