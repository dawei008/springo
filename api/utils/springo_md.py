"""
Load SPRINGO.md reference documentation for injection into system prompts.
"""
import os
import logging

logger = logging.getLogger(__name__)

_springo_md_cache: str | None = None
_springo_md_mtime: float = 0

# SPRINGO.md lives in the project root (same level as api/)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def load_springo_md() -> str:
    """Load SPRINGO.md from project root, cached with mtime invalidation."""
    global _springo_md_cache, _springo_md_mtime

    path = os.path.join(_PROJECT_ROOT, "SPRINGO.md")
    try:
        current_mtime = os.path.getmtime(path)
    except OSError:
        return _springo_md_cache or ""

    if _springo_md_cache is not None and current_mtime == _springo_md_mtime:
        return _springo_md_cache

    try:
        with open(path, "r", encoding="utf-8") as f:
            _springo_md_cache = f.read().strip()
        _springo_md_mtime = current_mtime
    except FileNotFoundError:
        logger.warning(f"SPRINGO.md not found at {path}")
        _springo_md_cache = ""
    except Exception as e:
        logger.warning(f"Failed to read SPRINGO.md: {e}")
        _springo_md_cache = ""

    return _springo_md_cache


def reload_springo_md() -> str:
    """Force reload SPRINGO.md (e.g., after user edits it)."""
    global _springo_md_cache, _springo_md_mtime
    _springo_md_cache = None
    _springo_md_mtime = 0
    return load_springo_md()
