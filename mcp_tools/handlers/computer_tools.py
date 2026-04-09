"""
Computer Use Tool Handler

Implements computer use for macOS via Springo.
Handles screenshot capture with resize/scaling, mouse actions, keyboard input.
Supports multi-display: specify display_index to target a specific monitor.

Coordinate scaling:
  - Screenshots are resized to fit API limits (1568px max edge, ~1.15MP)
  - Model returns coordinates in resized image space
  - We scale coordinates back to screen space before dispatching actions
  - For non-main displays, screen coordinates include the display origin offset
"""

import base64
import io
import logging
import math
import os
import time
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# API resize parameters (from Anthropic computer use spec)
MAX_LONG_EDGE = 1568
MAX_TOTAL_PIXELS = 1_150_000

# Active display index — persisted across calls within a session
_active_display: Optional[int] = None


def _compute_scale(screen_w: int, screen_h: int) -> float:
    """Compute the scale factor to resize screenshots for the API."""
    long_edge_scale = MAX_LONG_EDGE / max(screen_w, screen_h)
    total_pixels_scale = math.sqrt(MAX_TOTAL_PIXELS / (screen_w * screen_h))
    return min(long_edge_scale, total_pixels_scale, 1.0)


def _api_dimensions(screen_w: int, screen_h: int) -> Tuple[int, int]:
    """Return (api_w, api_h) — the dimensions we report to the API."""
    scale = _compute_scale(screen_w, screen_h)
    return int(screen_w * scale), int(screen_h * scale)


def _to_screen_coords(api_x: int, api_y: int, screen_w: int, screen_h: int,
                       origin_x: int = 0, origin_y: int = 0) -> Tuple[int, int]:
    """Convert coordinates from API (resized) space to global screen space.

    For secondary displays, origin_x/origin_y offset the coordinates into
    the global macOS screen coordinate system.
    """
    scale = _compute_scale(screen_w, screen_h)
    if scale <= 0:
        return api_x + origin_x, api_y + origin_y
    return int(api_x / scale) + origin_x, int(api_y / scale) + origin_y


def _get_active_display_info() -> dict:
    """Get info for the active display (or main if none set)."""
    from ..utilities.macos_control import list_displays
    displays = list_displays()

    if _active_display is not None:
        for d in displays:
            if d["index"] == _active_display:
                return d

    # Default: main
    for d in displays:
        if d["is_main"]:
            return d
    return displays[0]


# ---------------------------------------------------------------------------
# Screenshot
# ---------------------------------------------------------------------------

def _screenshot(display_index: int = None) -> Dict[str, Any]:
    """Take screenshot, resize to API limits, return base64 image data."""
    from ..utilities.macos_control import take_screenshot

    idx = display_index or _active_display
    info = _get_active_display_info() if idx is None else None
    if info is None:
        from ..utilities.macos_control import list_displays
        displays = list_displays()
        info = next((d for d in displays if d["index"] == idx), _get_active_display_info())

    screen_w, screen_h = info["width"], info["height"]
    api_w, api_h = _api_dimensions(screen_w, screen_h)

    path = take_screenshot(display_index=info["index"])
    try:
        from PIL import Image
        img = Image.open(path)

        if img.mode == "RGBA":
            img = img.convert("RGB")

        if (img.width, img.height) != (api_w, api_h):
            img = img.resize((api_w, api_h), Image.LANCZOS)

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=75)
        b64_data = base64.standard_b64encode(buf.getvalue()).decode("ascii")
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass

    return {
        "type": "computer_screenshot",
        "image": {
            "type": "base64",
            "media_type": "image/jpeg",
            "data": b64_data,
        },
        "display_width": api_w,
        "display_height": api_h,
        "display_index": info["index"],
    }


# ---------------------------------------------------------------------------
# Action dispatcher
# ---------------------------------------------------------------------------

def computer(action: str, coordinate: list = None, text: str = None,
             duration: int = None, scroll_direction: str = None,
             scroll_amount: int = None, start_coordinate: list = None,
             display: int = None, **kwargs) -> Dict[str, Any]:
    """Main computer use tool handler.

    Args:
        action: One of: screenshot, left_click, right_click, middle_click,
                double_click, triple_click, mouse_move, left_click_drag,
                key, type, scroll, cursor_position, wait, list_displays,
                switch_display
        coordinate: [x, y] in API coordinate space
        text: For 'key' (combo like 'ctrl+a') or 'type' (text to type)
        duration: For 'wait' action (seconds)
        scroll_direction: 'up', 'down', 'left', 'right'
        scroll_amount: Number of scroll steps (default 3)
        start_coordinate: [x, y] start position for drag
        display: Target display index (1-based). Sets active display for this
                 and subsequent calls. Use list_displays to see available displays.
    """
    global _active_display

    from ..utilities.macos_control import (
        list_displays,
        get_display_size, get_display_origin,
        mouse_move as _mouse_move,
        mouse_click, mouse_double_click, mouse_triple_click,
        mouse_drag, mouse_scroll, get_cursor_position,
        key_press, type_text,
    )

    action = action.strip().lower()

    # Switch active display if specified
    if display is not None:
        _active_display = int(display)

    # List all displays
    if action == "list_displays":
        displays = list_displays()
        lines = []
        for d in displays:
            main_tag = " (MAIN)" if d["is_main"] else ""
            active_tag = " (ACTIVE)" if d["index"] == (_active_display or 1) else ""
            lines.append(
                f"Display {d['index']}: {d['width']}x{d['height']} "
                f"at ({d['origin_x']}, {d['origin_y']}){main_tag}{active_tag}"
            )
        return {"output": "\n".join(lines), "displays": displays}

    # Switch display (explicit action)
    if action == "switch_display":
        if display is None:
            return {"error": "display parameter required for switch_display"}
        displays = list_displays()
        if not any(d["index"] == _active_display for d in displays):
            _active_display = None
            return {"error": f"Display {display} not found"}
        return _screenshot()

    # Get active display info for coordinate resolution
    disp = _get_active_display_info()
    screen_w, screen_h = disp["width"], disp["height"]
    origin_x, origin_y = disp["origin_x"], disp["origin_y"]

    # Screenshot
    if action == "screenshot":
        return _screenshot()

    # Cursor position query
    if action == "cursor_position":
        sx, sy = get_cursor_position()
        # Convert global screen coords to API coords for active display
        local_x = sx - origin_x
        local_y = sy - origin_y
        scale = _compute_scale(screen_w, screen_h)
        api_x = int(local_x * scale)
        api_y = int(local_y * scale)
        return {"output": f"Cursor position: ({api_x}, {api_y}) on display {disp['index']}"}

    # Wait
    if action == "wait":
        secs = min(duration or 2, 10)
        time.sleep(secs)
        return {"output": f"Waited {secs} seconds"}

    def _resolve(coord):
        """Convert API coords to global screen coords (with display offset)."""
        if coord is None:
            return None, None
        x, y = int(coord[0]), int(coord[1])
        return _to_screen_coords(x, y, screen_w, screen_h, origin_x, origin_y)

    # Click actions
    if action in ("left_click", "click"):
        if coordinate is None:
            return {"error": "coordinate required for left_click"}
        sx, sy = _resolve(coordinate)
        mouse_click(sx, sy, "left")
        return _screenshot()

    if action == "right_click":
        if coordinate is None:
            return {"error": "coordinate required for right_click"}
        sx, sy = _resolve(coordinate)
        mouse_click(sx, sy, "right")
        return _screenshot()

    if action == "middle_click":
        if coordinate is None:
            return {"error": "coordinate required for middle_click"}
        sx, sy = _resolve(coordinate)
        mouse_click(sx, sy, "middle")
        return _screenshot()

    if action == "double_click":
        if coordinate is None:
            return {"error": "coordinate required for double_click"}
        sx, sy = _resolve(coordinate)
        mouse_double_click(sx, sy)
        return _screenshot()

    if action == "triple_click":
        if coordinate is None:
            return {"error": "coordinate required for triple_click"}
        sx, sy = _resolve(coordinate)
        mouse_triple_click(sx, sy)
        return _screenshot()

    # Mouse move
    if action == "mouse_move":
        if coordinate is None:
            return {"error": "coordinate required for mouse_move"}
        sx, sy = _resolve(coordinate)
        _mouse_move(sx, sy)
        return _screenshot()

    # Drag
    if action in ("left_click_drag", "drag"):
        if start_coordinate is None or coordinate is None:
            return {"error": "start_coordinate and coordinate required for drag"}
        sx1, sy1 = _resolve(start_coordinate)
        sx2, sy2 = _resolve(coordinate)
        mouse_drag(sx1, sy1, sx2, sy2)
        return _screenshot()

    # Keyboard: key combo
    if action == "key":
        if not text:
            return {"error": "text required for key action (e.g. 'ctrl+c')"}
        key_press(text)
        time.sleep(0.1)
        return _screenshot()

    # Keyboard: type text
    if action == "type":
        if text is None:
            return {"error": "text required for type action"}
        type_text(text)
        time.sleep(0.1)
        return _screenshot()

    # Scroll
    if action == "scroll":
        sx, sy = _resolve(coordinate) if coordinate else get_cursor_position()
        direction = (scroll_direction or "down").lower()
        amount = scroll_amount or 3

        dx, dy = 0, 0
        if direction == "up":
            dy = amount
        elif direction == "down":
            dy = -amount
        elif direction == "left":
            dx = amount
        elif direction == "right":
            dx = -amount

        mouse_scroll(sx, sy, delta_x=dx, delta_y=dy)
        return _screenshot()

    return {"error": f"Unknown action: {action}"}
