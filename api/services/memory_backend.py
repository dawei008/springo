"""
Memory Backend Abstraction Layer
记忆后端抽象层 — 支持多种记忆后端切换

Supported backends:
- agentcore: AWS Bedrock AgentCore Memory (default, production)
- local: Local-only JSONL (no cloud sync, for testing/offline)
"""

import logging
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class MemoryBackend(Protocol):
    """Abstract interface for memory backends.

    All memory backends must implement these 3 methods.
    SessionStore calls these — it never knows which backend is active.
    """

    def on_message(self, session_id: str, message: Dict, actor: str) -> bool:
        """Handle a single new message. Returns True if accepted."""
        ...

    def on_conversation(self, session_id: str, messages: List[Dict]) -> int:
        """Handle a batch of messages (e.g., after compaction). Returns count queued."""
        ...

    def shutdown(self) -> None:
        """Graceful shutdown."""
        ...


class AgentCoreBackend:
    """Wraps the existing MemorySyncManager as a MemoryBackend."""

    def __init__(self, sync_manager):
        self._mgr = sync_manager

    def on_message(self, session_id: str, message: Dict, actor: str) -> bool:
        return self._mgr.queue_message(session_id, message, actor)

    def on_conversation(self, session_id: str, messages: List[Dict]) -> int:
        return self._mgr.queue_conversation(session_id, messages)

    def shutdown(self) -> None:
        self._mgr.stop()

    @property
    def initialized(self) -> bool:
        return self._mgr._initialized

    def get_stats(self) -> Dict[str, Any]:
        return self._mgr.get_stats()


class LocalOnlyBackend:
    """No-op backend — messages are only stored in local JSONL.

    Use this for testing, offline mode, or when no cloud memory is needed.
    """

    def on_message(self, session_id: str, message: Dict, actor: str) -> bool:
        return True  # always "accepted" (stored locally by SessionStore)

    def on_conversation(self, session_id: str, messages: List[Dict]) -> int:
        return len(messages)  # all "queued" (no-op)

    def shutdown(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Singleton + factory
# ---------------------------------------------------------------------------
_active_backend: Optional[MemoryBackend] = None
_active_backend_type: str = "none"


def get_memory_backend() -> Optional[MemoryBackend]:
    """Get the currently active memory backend (or None)."""
    return _active_backend


def get_memory_backend_type() -> str:
    """Get the name of the currently active backend."""
    return _active_backend_type


def set_memory_backend(backend: Optional[MemoryBackend], backend_type: str = "custom") -> None:
    """Set the active memory backend (called during init or hot-swap)."""
    global _active_backend, _active_backend_type
    # Shutdown previous backend if switching
    if _active_backend is not None and _active_backend is not backend:
        try:
            _active_backend.shutdown()
        except Exception as e:
            logger.warning(f"Error shutting down previous memory backend: {e}")
    _active_backend = backend
    _active_backend_type = backend_type if backend else "none"
    logger.info(f"Memory backend set to: {_active_backend_type}")


def init_memory_backend(backend_type: str = None) -> Optional[MemoryBackend]:
    """Initialize memory backend based on config.

    Args:
        backend_type: Override backend type. If None, reads from config.

    Returns:
        The initialized backend, or None if disabled.
    """
    from .memory_sync import load_memory_config

    config = load_memory_config()

    if backend_type is None:
        backend_type = config.get("memory_backend", "agentcore")

    if not config.get("memory_enabled", True):
        logger.info("Memory disabled in config")
        set_memory_backend(None, "none")
        return None

    if backend_type == "local":
        backend = LocalOnlyBackend()
        set_memory_backend(backend, "local")
        logger.info("Memory backend: local (JSONL only, no cloud sync)")
        return backend

    if backend_type == "agentcore":
        # Use existing MemorySyncManager
        from .memory_sync import init_memory_sync, get_sync_manager
        success = init_memory_sync()
        if success:
            mgr = get_sync_manager()
            backend = AgentCoreBackend(mgr)
            set_memory_backend(backend, "agentcore")
            return backend
        else:
            logger.warning("AgentCore memory init failed, falling back to local")
            backend = LocalOnlyBackend()
            set_memory_backend(backend, "local")
            return backend

    logger.warning(f"Unknown memory backend type: {backend_type}, using local")
    backend = LocalOnlyBackend()
    set_memory_backend(backend, "local")
    return backend


def shutdown_memory_backend() -> None:
    """Shutdown the active memory backend."""
    global _active_backend, _active_backend_type
    if _active_backend:
        try:
            _active_backend.shutdown()
        except Exception as e:
            logger.warning(f"Error shutting down memory backend: {e}")
    _active_backend = None
    _active_backend_type = "none"
