"""
ACP Session Bridge
Maps ACP session IDs to Springo internal sessions.
Used by the ACP Server to maintain state across prompts.
"""

import logging
import time
import uuid
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class AcpSessionBridge:
    """Bridges ACP sessions <-> Springo session store."""

    def __init__(self):
        self._sessions: Dict[str, Dict[str, Any]] = {}

    def create_session(self, cwd: str = None, client_caps: Dict = None) -> str:
        """Create a new ACP session linked to Springo session store.

        Returns the ACP session_id.
        """
        session_id = str(uuid.uuid4())

        # Create corresponding entry in Springo session store
        springo_session_id = session_id  # Use same ID by default
        try:
            from api.services.session_store import get_session_store
            store = get_session_store()
            store.save_session(
                session_id=session_id,
                messages=[],
                metadata={"title": f"ACP Session {session_id[:8]}", "source": "acp"},
            )
        except Exception as e:
            logger.warning(f"Failed to create Springo session for ACP: {e}")

        self._sessions[session_id] = {
            "session_id": session_id,
            "springo_session_id": springo_session_id,
            "cwd": cwd or "/tmp",
            "client_caps": client_caps or {},
            "messages": [],
            "created": time.time(),
            "last_active": time.time(),
        }

        logger.info(f"Created ACP session {session_id[:8]}")
        return session_id

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get session state."""
        session = self._sessions.get(session_id)
        if session:
            session["last_active"] = time.time()
        return session

    def append_message(self, session_id: str, role: str, content: Any):
        """Append a message to the session history."""
        session = self._sessions.get(session_id)
        if not session:
            logger.warning(f"ACP session not found: {session_id}")
            return

        message = {"role": role, "content": content}
        session["messages"].append(message)
        session["last_active"] = time.time()

        # Also persist to Springo session store (full overwrite)
        springo_id = session.get("springo_session_id")
        if springo_id:
            try:
                from api.services.session_store import get_session_store
                store = get_session_store()
                store.save_session(springo_id, session["messages"])
            except Exception as e:
                logger.debug(f"Failed to persist ACP message to Springo store: {e}")

    def get_messages(self, session_id: str) -> List[Dict[str, Any]]:
        """Get all messages for a session."""
        session = self._sessions.get(session_id)
        if not session:
            return []
        return session["messages"]

    def get_tool_definitions(self, session_id: str) -> List[Dict[str, Any]]:
        """Get available tools for this session (built-in + MCP)."""
        try:
            from mcp_tools.core import get_tool_definitions
            return get_tool_definitions()
        except Exception as e:
            logger.warning(f"Failed to get tool definitions for ACP session: {e}")
            return []

    def delete_session(self, session_id: str):
        """Remove a session."""
        self._sessions.pop(session_id, None)

    def list_sessions(self) -> List[Dict[str, Any]]:
        """List all active ACP sessions."""
        return [
            {
                "session_id": s["session_id"],
                "cwd": s["cwd"],
                "messages": len(s["messages"]),
                "created": s["created"],
                "last_active": s["last_active"],
            }
            for s in self._sessions.values()
        ]

    def cleanup_stale(self, max_age_seconds: float = 3600):
        """Remove sessions older than max_age_seconds."""
        now = time.time()
        stale = [
            sid for sid, s in self._sessions.items()
            if now - s["last_active"] > max_age_seconds
        ]
        for sid in stale:
            self.delete_session(sid)
        if stale:
            logger.info(f"Cleaned up {len(stale)} stale ACP sessions")


# Singleton
_session_bridge: Optional[AcpSessionBridge] = None


def get_acp_session_bridge() -> AcpSessionBridge:
    global _session_bridge
    if _session_bridge is None:
        _session_bridge = AcpSessionBridge()
    return _session_bridge
