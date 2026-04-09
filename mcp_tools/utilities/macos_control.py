"""
macOS Control — low-level screen capture, mouse, and keyboard via native APIs.

Uses:
  - `screencapture` CLI for screenshots (fast, reliable, no extra deps)
  - Quartz CGEvent API for mouse/keyboard (pyobjc-framework-Quartz)
  - NSScreen for display dimensions (pyobjc-framework-Cocoa)
"""

import subprocess
import tempfile
import time
import logging
from typing import Tuple, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Display info
# ---------------------------------------------------------------------------

def list_displays() -> list:
    """Return info for all connected displays.

    Each entry: {index, width, height, origin_x, origin_y, is_main, scale_factor}
    index corresponds to macOS display numbering (1-based for screencapture -D).
    """
    try:
        from AppKit import NSScreen
        displays = []
        for i, screen in enumerate(NSScreen.screens()):
            frame = screen.frame()
            displays.append({
                "index": i + 1,  # screencapture -D is 1-based
                "width": int(frame.size.width),
                "height": int(frame.size.height),
                "origin_x": int(frame.origin.x),
                "origin_y": int(frame.origin.y),
                "is_main": (screen == NSScreen.mainScreen()),
                "scale_factor": float(screen.backingScaleFactor()),
            })
        return displays
    except ImportError:
        return [{"index": 1, "width": 1920, "height": 1080,
                 "origin_x": 0, "origin_y": 0, "is_main": True, "scale_factor": 2.0}]


def get_display_size(display_index: int = None) -> Tuple[int, int]:
    """Return (width, height) of a display in logical points.

    Args:
        display_index: 1-based display index. None = main display.
    """
    displays = list_displays()
    if display_index is not None:
        for d in displays:
            if d["index"] == display_index:
                return d["width"], d["height"]
    # Default: main display
    for d in displays:
        if d["is_main"]:
            return d["width"], d["height"]
    return displays[0]["width"], displays[0]["height"] if displays else (1920, 1080)


def get_display_origin(display_index: int = None) -> Tuple[int, int]:
    """Return (origin_x, origin_y) of a display in global screen coordinates.

    macOS uses a coordinate system where (0,0) is the bottom-left of the main
    display. Secondary displays have offsets relative to the main display.
    """
    displays = list_displays()
    if display_index is not None:
        for d in displays:
            if d["index"] == display_index:
                return d["origin_x"], d["origin_y"]
    return 0, 0  # main display origin


def get_scale_factor(display_index: int = None) -> float:
    """Return the display scale factor (e.g. 2.0 for Retina)."""
    displays = list_displays()
    if display_index is not None:
        for d in displays:
            if d["index"] == display_index:
                return d["scale_factor"]
    for d in displays:
        if d["is_main"]:
            return d["scale_factor"]
    return 2.0


# ---------------------------------------------------------------------------
# Screenshot
# ---------------------------------------------------------------------------

def take_screenshot(path: Optional[str] = None, display_index: int = None) -> str:
    """Capture screenshot using CGWindowListCreateImage (no floating indicator).

    Uses Quartz API directly to avoid macOS's screencapture permission
    indicator that appears on macOS 15+/26+.

    Args:
        path: Output file path. Auto-generated if None.
        display_index: 1-based display index. None = main display.
    """
    if path is None:
        path = tempfile.mktemp(suffix=".png")

    try:
        return _screenshot_cg(path, display_index)
    except Exception as e:
        logger.warning(f"CGWindowListCreateImage failed ({e}), falling back to screencapture")
        return _screenshot_cli(path, display_index)


def _screenshot_cg(path: str, display_index: int = None) -> str:
    """Screenshot via Quartz CGWindowListCreateImage — no UI indicator."""
    from Quartz import (
        CGWindowListCreateImage, CGRectMake,
        kCGWindowListOptionOnScreenOnly, kCGNullWindowID,
        CGImageDestinationCreateWithURL,
        CGImageDestinationAddImage, CGImageDestinationFinalize,
    )
    from CoreFoundation import (
        CFURLCreateWithFileSystemPath, kCFAllocatorDefault, kCFURLPOSIXPathStyle,
    )

    # Determine capture rect for the target display
    displays = list_displays()
    if display_index is not None:
        disp = next((d for d in displays if d["index"] == display_index), None)
    else:
        disp = next((d for d in displays if d["is_main"]), displays[0])

    if disp is None:
        raise RuntimeError(f"Display {display_index} not found")

    rect = CGRectMake(disp["origin_x"], disp["origin_y"],
                      disp["width"], disp["height"])

    image = CGWindowListCreateImage(
        rect,
        kCGWindowListOptionOnScreenOnly,
        kCGNullWindowID,
        0,  # kCGWindowImageDefault
    )

    if image is None:
        raise RuntimeError("CGWindowListCreateImage returned None")

    # Save as PNG via CGImageDestination
    url = CFURLCreateWithFileSystemPath(kCFAllocatorDefault, path,
                                        kCFURLPOSIXPathStyle, False)
    dest = CGImageDestinationCreateWithURL(url, "public.png", 1, None)
    if dest is None:
        raise RuntimeError("Failed to create image destination")

    CGImageDestinationAddImage(dest, image, None)
    CGImageDestinationFinalize(dest)
    return path


def _screenshot_cli(path: str, display_index: int = None) -> str:
    """Fallback: screenshot via screencapture CLI."""
    cmd = ["screencapture", "-x", "-C"]
    if display_index is not None:
        cmd.extend(["-D", str(display_index)])
    cmd.append(path)
    subprocess.run(cmd, check=True, timeout=10)
    return path


# ---------------------------------------------------------------------------
# Mouse control via Quartz CGEvent
# ---------------------------------------------------------------------------

def _cg_point(x: int, y: int):
    """Create a CGPoint."""
    from Quartz import CGPoint
    return CGPoint(x, y)


def _post_event(event):
    """Post a CGEvent to the HID event system."""
    from Quartz import CGEventPost, kCGHIDEventTap
    CGEventPost(kCGHIDEventTap, event)


def mouse_move(x: int, y: int):
    """Move cursor to (x, y) in screen coordinates."""
    from Quartz import CGEventCreateMouseEvent, kCGEventMouseMoved, kCGMouseButtonLeft
    event = CGEventCreateMouseEvent(None, kCGEventMouseMoved, _cg_point(x, y), kCGMouseButtonLeft)
    _post_event(event)
    time.sleep(0.05)  # settle


def mouse_click(x: int, y: int, button: str = "left"):
    """Click at (x, y). button: 'left', 'right', 'middle'."""
    from Quartz import (
        CGEventCreateMouseEvent,
        kCGEventLeftMouseDown, kCGEventLeftMouseUp,
        kCGEventRightMouseDown, kCGEventRightMouseUp,
        kCGEventOtherMouseDown, kCGEventOtherMouseUp,
        kCGMouseButtonLeft, kCGMouseButtonRight, kCGMouseButtonCenter,
    )

    button_map = {
        "left": (kCGEventLeftMouseDown, kCGEventLeftMouseUp, kCGMouseButtonLeft),
        "right": (kCGEventRightMouseDown, kCGEventRightMouseUp, kCGMouseButtonRight),
        "middle": (kCGEventOtherMouseDown, kCGEventOtherMouseUp, kCGMouseButtonCenter),
    }
    down_type, up_type, btn = button_map.get(button, button_map["left"])
    pt = _cg_point(x, y)

    down = CGEventCreateMouseEvent(None, down_type, pt, btn)
    _post_event(down)
    time.sleep(0.02)
    up = CGEventCreateMouseEvent(None, up_type, pt, btn)
    _post_event(up)
    time.sleep(0.05)


def mouse_double_click(x: int, y: int):
    """Double-click at (x, y)."""
    from Quartz import (
        CGEventCreateMouseEvent, CGEventSetIntegerValueField,
        kCGEventLeftMouseDown, kCGEventLeftMouseUp,
        kCGMouseButtonLeft, kCGMouseEventClickState,
    )
    pt = _cg_point(x, y)

    for click_count in (1, 2):
        down = CGEventCreateMouseEvent(None, kCGEventLeftMouseDown, pt, kCGMouseButtonLeft)
        CGEventSetIntegerValueField(down, kCGMouseEventClickState, click_count)
        _post_event(down)
        time.sleep(0.02)
        up = CGEventCreateMouseEvent(None, kCGEventLeftMouseUp, pt, kCGMouseButtonLeft)
        CGEventSetIntegerValueField(up, kCGMouseEventClickState, click_count)
        _post_event(up)
        time.sleep(0.02)
    time.sleep(0.05)


def mouse_triple_click(x: int, y: int):
    """Triple-click at (x, y) (select line)."""
    from Quartz import (
        CGEventCreateMouseEvent, CGEventSetIntegerValueField,
        kCGEventLeftMouseDown, kCGEventLeftMouseUp,
        kCGMouseButtonLeft, kCGMouseEventClickState,
    )
    pt = _cg_point(x, y)

    for click_count in (1, 2, 3):
        down = CGEventCreateMouseEvent(None, kCGEventLeftMouseDown, pt, kCGMouseButtonLeft)
        CGEventSetIntegerValueField(down, kCGMouseEventClickState, click_count)
        _post_event(down)
        time.sleep(0.02)
        up = CGEventCreateMouseEvent(None, kCGEventLeftMouseUp, pt, kCGMouseButtonLeft)
        CGEventSetIntegerValueField(up, kCGMouseEventClickState, click_count)
        _post_event(up)
        time.sleep(0.02)
    time.sleep(0.05)


def mouse_drag(start_x: int, start_y: int, end_x: int, end_y: int):
    """Left-drag from (start_x, start_y) to (end_x, end_y)."""
    from Quartz import (
        CGEventCreateMouseEvent,
        kCGEventLeftMouseDown, kCGEventLeftMouseUp, kCGEventLeftMouseDragged,
        kCGMouseButtonLeft,
    )

    # Press at start
    down = CGEventCreateMouseEvent(None, kCGEventLeftMouseDown, _cg_point(start_x, start_y), kCGMouseButtonLeft)
    _post_event(down)
    time.sleep(0.05)

    # Animate drag in steps
    steps = 20
    for i in range(1, steps + 1):
        t = i / steps
        cx = int(start_x + (end_x - start_x) * t)
        cy = int(start_y + (end_y - start_y) * t)
        drag = CGEventCreateMouseEvent(None, kCGEventLeftMouseDragged, _cg_point(cx, cy), kCGMouseButtonLeft)
        _post_event(drag)
        time.sleep(0.01)

    # Release at end
    up = CGEventCreateMouseEvent(None, kCGEventLeftMouseUp, _cg_point(end_x, end_y), kCGMouseButtonLeft)
    _post_event(up)
    time.sleep(0.05)


def mouse_scroll(x: int, y: int, delta_x: int = 0, delta_y: int = 0):
    """Scroll at (x, y). delta_y: positive=up, negative=down. delta_x: positive=left, negative=right."""
    from Quartz import CGEventCreateScrollWheelEvent, kCGScrollEventUnitLine

    # Move to position first
    mouse_move(x, y)

    scroll = CGEventCreateScrollWheelEvent(None, kCGScrollEventUnitLine, 2, delta_y, delta_x)
    _post_event(scroll)
    time.sleep(0.1)


def get_cursor_position() -> Tuple[int, int]:
    """Return current cursor (x, y) in screen coordinates."""
    from Quartz import CGEventCreate, CGEventGetLocation
    event = CGEventCreate(None)
    loc = CGEventGetLocation(event)
    return int(loc.x), int(loc.y)


# ---------------------------------------------------------------------------
# Keyboard control via Quartz CGEvent
# ---------------------------------------------------------------------------

# Common key name → macOS virtual keycode mapping
_KEY_CODES = {
    "return": 0x24, "enter": 0x24, "tab": 0x30, "space": 0x31,
    "delete": 0x33, "backspace": 0x33, "escape": 0x35, "esc": 0x35,
    "command": 0x37, "cmd": 0x37, "super": 0x37,
    "shift": 0x38, "capslock": 0x39, "option": 0x3A, "alt": 0x3A,
    "control": 0x3B, "ctrl": 0x3B,
    "right_shift": 0x3C, "right_option": 0x3D, "right_control": 0x3E,
    "fn": 0x3F,
    "f1": 0x7A, "f2": 0x78, "f3": 0x63, "f4": 0x76,
    "f5": 0x60, "f6": 0x61, "f7": 0x62, "f8": 0x64,
    "f9": 0x65, "f10": 0x6D, "f11": 0x67, "f12": 0x6F,
    "left": 0x7B, "right": 0x7C, "down": 0x7D, "up": 0x7E,
    "home": 0x73, "end": 0x77, "page_up": 0x74, "pageup": 0x74,
    "page_down": 0x79, "pagedown": 0x79,
    "forward_delete": 0x75,
    # Letters
    "a": 0x00, "b": 0x0B, "c": 0x08, "d": 0x02, "e": 0x0E,
    "f": 0x03, "g": 0x05, "h": 0x04, "i": 0x22, "j": 0x26,
    "k": 0x28, "l": 0x25, "m": 0x2E, "n": 0x2D, "o": 0x1F,
    "p": 0x23, "q": 0x0C, "r": 0x0F, "s": 0x01, "t": 0x11,
    "u": 0x20, "v": 0x09, "w": 0x0D, "x": 0x07, "y": 0x10,
    "z": 0x06,
    # Numbers
    "0": 0x1D, "1": 0x12, "2": 0x13, "3": 0x14, "4": 0x15,
    "5": 0x17, "6": 0x16, "7": 0x1A, "8": 0x1C, "9": 0x19,
    # Symbols
    "-": 0x1B, "=": 0x18, "[": 0x21, "]": 0x1E, "\\": 0x2A,
    ";": 0x29, "'": 0x27, ",": 0x2B, ".": 0x2F, "/": 0x2C,
    "`": 0x32,
}

# Modifier name → CGEvent flag
_MODIFIER_FLAGS = {
    "command": 0x100000, "cmd": 0x100000, "super": 0x100000,
    "shift": 0x20000,
    "option": 0x80000, "alt": 0x80000,
    "control": 0x40000, "ctrl": 0x40000,
}


def _resolve_keycode(key: str) -> int:
    """Resolve a key name to its macOS virtual keycode."""
    code = _KEY_CODES.get(key.lower())
    if code is not None:
        return code
    raise ValueError(f"Unknown key: {key}")


def key_press(key_combo: str):
    """Press a key combination (xdotool-style, e.g. 'ctrl+shift+a', 'Return').

    Modifiers are separated by '+'. The last token is the main key.
    """
    from Quartz import (
        CGEventCreateKeyboardEvent, CGEventSetFlags,
    )

    parts = [p.strip() for p in key_combo.split("+")]
    modifiers = parts[:-1]
    main_key = parts[-1]

    # Build modifier flags
    flags = 0
    for mod in modifiers:
        flag = _MODIFIER_FLAGS.get(mod.lower())
        if flag is None:
            raise ValueError(f"Unknown modifier: {mod}")
        flags |= flag

    keycode = _resolve_keycode(main_key)

    # Key down
    down = CGEventCreateKeyboardEvent(None, keycode, True)
    if flags:
        CGEventSetFlags(down, flags)
    _post_event(down)
    time.sleep(0.02)

    # Key up
    up = CGEventCreateKeyboardEvent(None, keycode, False)
    if flags:
        CGEventSetFlags(up, flags)
    _post_event(up)
    time.sleep(0.05)


def type_text(text: str):
    """Type text string using keyboard events.

    For short text, types character by character.
    For longer text (>32 chars), uses clipboard paste for speed.
    """
    if len(text) > 32:
        _type_via_clipboard(text)
    else:
        _type_chars(text)


def _type_chars(text: str):
    """Type text character by character via CGEvent."""
    from Quartz import CGEventCreateKeyboardEvent, CGEventKeyboardSetUnicodeString
    import ctypes

    for ch in text:
        # Use Unicode string approach for arbitrary characters
        down = CGEventCreateKeyboardEvent(None, 0, True)
        CGEventKeyboardSetUnicodeString(down, len(ch), ch)
        _post_event(down)
        time.sleep(0.01)

        up = CGEventCreateKeyboardEvent(None, 0, False)
        CGEventKeyboardSetUnicodeString(up, len(ch), ch)
        _post_event(up)
        time.sleep(0.01)

    time.sleep(0.05)


def _type_via_clipboard(text: str):
    """Type text by pasting from clipboard (faster for long strings)."""
    # Save current clipboard
    try:
        old_clipboard = subprocess.run(
            ["pbpaste"], capture_output=True, text=True, timeout=2,
        ).stdout
    except Exception:
        old_clipboard = None

    try:
        # Copy text to clipboard
        proc = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
        proc.communicate(input=text.encode("utf-8"), timeout=2)

        # Cmd+V to paste
        time.sleep(0.05)
        key_press("cmd+v")
        time.sleep(0.1)
    finally:
        # Restore clipboard
        if old_clipboard is not None:
            try:
                proc = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
                proc.communicate(input=old_clipboard.encode("utf-8"), timeout=2)
            except Exception:
                pass
