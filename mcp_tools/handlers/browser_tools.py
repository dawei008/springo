"""
Browser Automation Tools
Playwright-based browser control
"""

import os
import base64
import tempfile
import threading
from typing import Any, Dict

# Optional playwright import
try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

# Thread lock for browser operations
_browser_lock = threading.Lock()


class BrowserManager:
    """Singleton browser manager for Playwright"""
    _instance = None
    _playwright = None
    _browser = None
    _page = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def get_page(self):
        if not HAS_PLAYWRIGHT:
            return None, "Playwright not available. Install with: pip install playwright && playwright install chromium"

        try:
            if self._playwright is None:
                self._playwright = sync_playwright().start()

            if self._browser is None:
                self._browser = self._playwright.chromium.launch(headless=True)

            if self._page is None:
                self._page = self._browser.new_page()

            return self._page, None
        except Exception as e:
            return None, str(e)

    def close(self):
        if self._page:
            self._page.close()
            self._page = None
        if self._browser:
            self._browser.close()
            self._browser = None
        if self._playwright:
            self._playwright.stop()
            self._playwright = None


def browser_navigate(url: str, wait_until: str = "load") -> Dict[str, Any]:
    """Navigate browser to URL"""
    manager = BrowserManager.get_instance()
    page, error = manager.get_page()

    if error:
        return {"error": error}

    try:
        page.goto(url, wait_until=wait_until)
        return {
            "success": True,
            "url": page.url,
            "title": page.title()
        }
    except Exception as e:
        return {"error": f"Navigation failed: {str(e)}"}


def browser_screenshot(selector: str = None, full_page: bool = False) -> Dict[str, Any]:
    """Take a screenshot"""
    manager = BrowserManager.get_instance()
    page, error = manager.get_page()

    if error:
        return {"error": error}

    try:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            screenshot_path = f.name

        if selector:
            element = page.locator(selector)
            element.screenshot(path=screenshot_path)
        else:
            page.screenshot(path=screenshot_path, full_page=full_page)

        with open(screenshot_path, "rb") as f:
            screenshot_data = base64.b64encode(f.read()).decode("ascii")

        os.unlink(screenshot_path)

        return {
            "success": True,
            "screenshot": screenshot_data,
            "encoding": "base64",
            "format": "png"
        }
    except Exception as e:
        return {"error": f"Screenshot failed: {str(e)}"}


def browser_click(selector: str) -> Dict[str, Any]:
    """Click an element"""
    manager = BrowserManager.get_instance()
    page, error = manager.get_page()

    if error:
        return {"error": error}

    try:
        page.click(selector)
        return {"success": True, "selector": selector}
    except Exception as e:
        return {"error": f"Click failed: {str(e)}"}


def browser_type(selector: str, text: str, clear: bool = True) -> Dict[str, Any]:
    """Type text into an input"""
    manager = BrowserManager.get_instance()
    page, error = manager.get_page()

    if error:
        return {"error": error}

    try:
        if clear:
            page.fill(selector, text)
        else:
            page.type(selector, text)
        return {"success": True, "selector": selector, "text": text}
    except Exception as e:
        return {"error": f"Type failed: {str(e)}"}


def browser_get_text(selector: str = None) -> Dict[str, Any]:
    """Get page or element text"""
    manager = BrowserManager.get_instance()
    page, error = manager.get_page()

    if error:
        return {"error": error}

    try:
        if selector:
            element = page.locator(selector)
            text = element.inner_text()
        else:
            text = page.inner_text("body")

        if len(text) > 50000:
            text = text[:50000] + "\n... (truncated)"

        return {
            "success": True,
            "text": text,
            "length": len(text)
        }
    except Exception as e:
        return {"error": f"Get text failed: {str(e)}"}


def browser_evaluate(script: str) -> Dict[str, Any]:
    """Execute JavaScript"""
    manager = BrowserManager.get_instance()
    page, error = manager.get_page()

    if error:
        return {"error": error}

    try:
        result = page.evaluate(script)
        return {
            "success": True,
            "result": result
        }
    except Exception as e:
        return {"error": f"Script execution failed: {str(e)}"}


def browser_close() -> Dict[str, Any]:
    """Close the browser"""
    try:
        manager = BrowserManager.get_instance()
        manager.close()
        return {"success": True, "message": "Browser closed"}
    except Exception as e:
        return {"error": f"Failed to close browser: {str(e)}"}


def browser(action: str, **kwargs) -> Dict[str, Any]:
    """
    Unified Browser tool - combines all browser operations into one tool.

    Actions: navigate, screenshot, click, type, get_text, evaluate, close
    """
    action = action.lower()

    handlers = {
        "navigate": lambda: browser_navigate(
            url=kwargs.get("url", ""),
            wait_until=kwargs.get("wait_until", "load")
        ),
        "screenshot": lambda: browser_screenshot(
            selector=kwargs.get("selector"),
            full_page=kwargs.get("full_page", False)
        ),
        "click": lambda: browser_click(
            selector=kwargs.get("selector", "")
        ),
        "type": lambda: browser_type(
            selector=kwargs.get("selector", ""),
            text=kwargs.get("text", ""),
            clear=kwargs.get("clear", True)
        ),
        "get_text": lambda: browser_get_text(
            selector=kwargs.get("selector")
        ),
        "evaluate": lambda: browser_evaluate(
            script=kwargs.get("script", "")
        ),
        "close": lambda: browser_close()
    }

    if action not in handlers:
        return {"error": f"Unknown browser action: {action}. Valid actions: {', '.join(handlers.keys())}"}

    # Use thread lock to prevent concurrent access issues
    with _browser_lock:
        try:
            return handlers[action]()
        except Exception as e:
            # Reset browser on error to allow retry
            BrowserManager.get_instance().close()
            return {"error": f"Browser operation failed: {str(e)}"}
