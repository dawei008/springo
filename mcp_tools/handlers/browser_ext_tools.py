"""
Browser Extension Tool Handlers

These tools drive the user's *real* Chrome through the Springo Chrome
extension (see api/services/browser_bridge.py). Unlike the Playwright/CDP path
which spins up a throwaway browser, these operate inside the user's signed-in
Chrome — so authenticated sites, cookies, and sessions just work.

Handlers run synchronously in a ThreadPoolExecutor (mcp_tools/core.py). The
bridge's send_command() schedules the actual WS send on the main loop and blocks
on the reply, so these stay simple.

Tool names are prefixed `web_` to read as a coherent group and avoid clashing
with the file-system / general tools.
"""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def _bridge():
    from api.services.browser_bridge import get_browser_bridge
    return get_browser_bridge()


def web_browser_status() -> Dict[str, Any]:
    """Report whether the Springo Chrome extension is connected and ready."""
    return _bridge().status()


def web_navigate(url: str, timeout: float = 30.0) -> Dict[str, Any]:
    """Navigate the controlled Chrome tab to a URL (within Springo's tab group)."""
    if not url:
        return {"error": "url is required"}
    return _bridge().send_command("navigate", {"url": url}, timeout=timeout)


def web_click(selector: str = "", x: Optional[float] = None,
              y: Optional[float] = None, timeout: float = 30.0) -> Dict[str, Any]:
    """Click an element by CSS selector, or at viewport coordinates (x, y)."""
    if not selector and (x is None or y is None):
        return {"error": "Provide either a selector or both x and y coordinates"}
    return _bridge().send_command(
        "click", {"selector": selector, "x": x, "y": y}, timeout=timeout
    )


def web_type(text: str, selector: str = "", submit: bool = False,
             timeout: float = 30.0) -> Dict[str, Any]:
    """Type text into the focused element (or one matched by selector).

    Set submit=true to press Enter afterward.
    """
    return _bridge().send_command(
        "type", {"text": text, "selector": selector, "submit": submit}, timeout=timeout
    )


def web_read_page(format: str = "text", timeout: float = 30.0) -> Dict[str, Any]:
    """Read the current page's content. format: 'text' (default) | 'html'."""
    return _bridge().send_command("read_page", {"format": format}, timeout=timeout)


def web_screenshot(full_page: bool = False, timeout: float = 30.0) -> Dict[str, Any]:
    """Capture a screenshot of the controlled tab (returns base64 PNG)."""
    return _bridge().send_command("screenshot", {"full_page": full_page}, timeout=timeout)


def web_evaluate(expression: str, timeout: float = 30.0) -> Dict[str, Any]:
    """Evaluate a JavaScript expression in the page and return the result."""
    if not expression:
        return {"error": "expression is required"}
    return _bridge().send_command("evaluate", {"expression": expression}, timeout=timeout)


def web_tabs(action: str = "list", url: str = "", index: Optional[int] = None,
             timeout: float = 30.0) -> Dict[str, Any]:
    """Manage tabs in Springo's tab group. action: 'list' | 'open' | 'close' | 'select'."""
    return _bridge().send_command(
        "tabs", {"action": action, "url": url, "index": index}, timeout=timeout
    )
