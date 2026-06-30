"""
WebSocket endpoint for the Springo Chrome extension.

The extension (running in the user's real Chrome) dials in here and then
receives browser-automation commands and returns their results. This lets
Springo drive the user's signed-in Chrome via the extension's
chrome.debugger / chrome.tabs / chrome.tabGroups APIs — the extension-based
alternative to the CDP/Playwright throwaway-browser path.

Connect: ws://localhost:8081/v1/browser

Protocol (JSON frames):
  extension → backend (handshake):  {"type": "hello", "version": "...", "tab": {...}}
  backend  → extension (command):   {"id": <int>, "action": "navigate", "params": {...}}
  extension → backend  (reply):     {"id": <int>, "result": {...}}  | {"id": <int>, "error": "..."}
  extension → backend  (event):     {"type": "event", "name": "...", "data": {...}}
"""

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..services.browser_bridge import get_browser_bridge

logger = logging.getLogger(__name__)

router = APIRouter()

# Only accept handshakes from a Chrome extension or local pages. CORS does not
# apply to WebSocket handshakes, so we gate the origin ourselves.
_ALLOWED_ORIGIN_PREFIXES = ("chrome-extension://", "moz-extension://")
_ALLOWED_ORIGIN_EXACT = {"http://localhost:8081", "http://127.0.0.1:8081", "file://"}


def _origin_allowed(origin: str) -> bool:
    if not origin:
        # Extensions' service-worker WS connections may omit Origin; allow it
        # since the link is loopback-only.
        return True
    if origin in _ALLOWED_ORIGIN_EXACT:
        return True
    return any(origin.startswith(p) for p in _ALLOWED_ORIGIN_PREFIXES)


@router.websocket("/browser")
async def browser_ws(ws: WebSocket):
    origin = ws.headers.get("origin", "")
    if not _origin_allowed(origin):
        logger.warning("Rejected browser-ext WS from origin: %s", origin)
        await ws.close(code=1008)
        return

    await ws.accept()
    bridge = get_browser_bridge()
    attached = False
    try:
        while True:
            message = await ws.receive_json()
            msg_type = message.get("type")

            if msg_type == "hello":
                displaced = bridge.attach(ws, {
                    "version": message.get("version"),
                    "tab": message.get("tab"),
                    "origin": origin,
                })
                attached = True
                # Proactively close any socket this one displaced so its receive
                # loop ends instead of lingering.
                if displaced is not None and displaced is not ws:
                    try:
                        await displaced.close(code=1000)
                    except Exception:  # noqa: BLE001
                        pass
                await ws.send_json({"type": "welcome", "ok": True})
                continue

            if msg_type == "event":
                # Browser-side events (tab closed, navigation, etc.) — log for now.
                logger.debug("Browser ext event: %s", message.get("name"))
                continue

            # Otherwise it's a reply to a command we sent (has an "id").
            if "id" in message:
                bridge.resolve(message)
    except WebSocketDisconnect:
        pass
    except Exception as e:  # noqa: BLE001
        logger.warning("Browser ext WS error: %s", e)
    finally:
        if attached:
            bridge.detach(ws)


@router.get("/browser/status")
async def browser_status():
    """Report whether the Chrome extension is currently connected."""
    return get_browser_bridge().status()
