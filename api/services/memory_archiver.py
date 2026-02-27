"""
Memory Archiver
Archives session conversations to memory/*.md files when a new session is created.

Reads recent messages from the old session JSONL, generates a summary slug,
and writes a Markdown archive file for near-term memory retrieval.
"""

import json
import logging
import os
import re
from datetime import datetime
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# Max messages to include in archive
DEFAULT_MESSAGE_COUNT = 15


def _read_recent_messages(session_id: str, message_count: int = DEFAULT_MESSAGE_COUNT) -> List[Dict[str, Any]]:
    """Read recent user/assistant messages from a session JSONL file."""
    sessions_dir = os.path.expanduser("~/.springo/sessions")
    session_dir = os.path.join(sessions_dir, session_id)
    jsonl_path = os.path.join(session_dir, f"{session_id}.jsonl")

    if not os.path.isfile(jsonl_path):
        logger.debug(f"Session file not found: {jsonl_path}")
        return []

    messages = []
    try:
        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                # Skip metadata entries
                if entry.get("type") == "metadata":
                    continue

                role = entry.get("role", "")
                if role not in ("user", "assistant"):
                    continue

                # Extract text content
                content = entry.get("content", "")
                if isinstance(content, list):
                    # Extract text blocks from content array
                    text_parts = []
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            text_parts.append(block.get("text", ""))
                    content = "\n".join(text_parts)

                if not content or content.startswith("/"):
                    continue

                messages.append({"role": role, "text": content})
    except Exception as e:
        logger.warning(f"Failed to read session {session_id}: {e}")
        return []

    # Return last N messages
    return messages[-message_count:]


def _generate_slug(messages: List[Dict[str, Any]]) -> str:
    """Generate a short descriptive slug from conversation messages.

    Uses simple heuristic: extract key nouns from first user message.
    Falls back to timestamp if no meaningful content.
    """
    # Find first substantive user message
    for msg in messages:
        if msg["role"] == "user" and len(msg["text"]) > 10:
            text = msg["text"][:200].lower()
            # Remove common words and extract key terms
            words = re.findall(r'[a-z\u4e00-\u9fff]+', text)
            stop_words = {"the", "a", "an", "is", "are", "was", "were", "to", "for",
                          "in", "on", "at", "of", "and", "or", "but", "not", "with",
                          "this", "that", "it", "be", "do", "have", "has", "had",
                          "can", "could", "would", "should", "will", "just", "please",
                          "help", "me", "my", "i", "you", "your", "we", "us",
                          "what", "how", "why", "when", "where", "which"}
            key_words = [w for w in words if w not in stop_words and len(w) > 2][:4]
            if key_words:
                return "-".join(key_words)

    # Fallback: use timestamp
    return datetime.now().strftime("%H%M")


def _format_archive(session_id: str, messages: List[Dict[str, Any]], slug: str) -> str:
    """Format messages into a Markdown archive file."""
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M:%S")

    parts = [
        f"# Session Archive: {date_str} {time_str}",
        "",
        f"- **Session ID**: {session_id}",
        f"- **Messages**: {len(messages)}",
        f"- **Topic**: {slug.replace('-', ' ')}",
        "",
        "## Conversation",
        "",
    ]

    for msg in messages:
        role_label = "**User**" if msg["role"] == "user" else "**Assistant**"
        text = msg["text"].strip()
        # Truncate very long messages
        if len(text) > 2000:
            text = text[:2000] + "\n\n... (truncated)"
        parts.append(f"{role_label}: {text}")
        parts.append("")

    return "\n".join(parts)


async def archive_session(session_id: str, message_count: int = DEFAULT_MESSAGE_COUNT) -> Dict[str, Any]:
    """Archive a session's recent messages to memory/*.md.

    Called when user creates a new session (fire-and-forget from frontend).

    Returns:
        Dict with archive result metadata.
    """
    from .memory_files import get_memory_file_manager
    from .memory_sync import load_memory_config

    config = load_memory_config()
    if not config.get("local_memory_enabled", True):
        return {"archived": False, "reason": "local_memory_disabled"}

    if not config.get("auto_archive_on_reset", True):
        return {"archived": False, "reason": "auto_archive_disabled"}

    mgr = get_memory_file_manager()
    if mgr is None:
        return {"archived": False, "reason": "memory_file_manager_not_initialized"}

    # Read recent messages
    messages = _read_recent_messages(session_id, message_count)
    if not messages:
        return {"archived": False, "reason": "no_messages", "session_id": session_id}

    # Generate slug and format content
    slug = _generate_slug(messages)
    content = _format_archive(session_id, messages, slug)

    # Write archive file
    # AgentCore sync is handled by the file sync worker (checkpoint-based),
    # which will detect the new .md file and sync it within file_sync_interval.
    try:
        path = mgr.write_session_archive(slug, content)
        rel_path = os.path.relpath(path, mgr.workspace_dir)
        logger.info(f"Session {session_id} archived to {rel_path} ({len(messages)} messages)")
        return {
            "archived": True,
            "path": rel_path,
            "slug": slug,
            "message_count": len(messages),
            "session_id": session_id,
        }
    except Exception as e:
        logger.error(f"Failed to archive session {session_id}: {e}")
        return {"archived": False, "error": str(e), "session_id": session_id}
