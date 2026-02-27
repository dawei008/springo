"""
Memory Archiver
Extracts key facts from session conversations and saves to daily memory log.

Called when user creates a new session or deletes one.
Uses a fast model (Haiku) to extract important facts, decisions, and preferences
instead of dumping raw conversation text.
"""

import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# Max messages to include in extraction
DEFAULT_MESSAGE_COUNT = 15

# Prompt for fact extraction from session conversations
_SESSION_EXTRACT_PROMPT = """You are a memory extraction assistant. A user session has ended. Your job is to extract any **important facts, decisions, user preferences, or project context** that should be remembered for future sessions.

Rules:
- Only extract genuinely important information (decisions, preferences, technical choices, key findings)
- Skip routine chitchat, greetings, and ephemeral task details
- If there is nothing worth remembering, respond with exactly: NOTHING_TO_REMEMBER
- Otherwise, respond with a concise Markdown list of facts to remember (max 10 items)
- Format each item as: `- [category] fact` where category is one of: decision, preference, finding, context, todo
- Keep each item under 100 characters

Session messages:
{messages_text}"""


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


def _build_messages_text(messages: List[Dict[str, Any]], max_chars: int = 8000) -> str:
    """Build a text representation of messages for the extraction prompt."""
    text_parts = []
    total_chars = 0

    for msg in messages:
        snippet = msg["text"].strip()[:500]
        line = f"[{msg['role']}]: {snippet}"
        if total_chars + len(line) > max_chars:
            break
        text_parts.append(line)
        total_chars += len(line)

    return "\n".join(text_parts)


async def archive_session(session_id: str, message_count: int = DEFAULT_MESSAGE_COUNT) -> Dict[str, Any]:
    """Extract key facts from a session and save to daily memory log.

    Called when user creates a new session or deletes one (fire-and-forget from frontend).
    Uses a fast model to extract important facts instead of dumping raw conversation.

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

    messages_text = _build_messages_text(messages)
    if not messages_text:
        return {"archived": False, "reason": "no_text_content", "session_id": session_id}

    # Call fast model to extract facts
    try:
        from .bedrock import get_bedrock_service
        from .model_registry import get_model_info, get_bedrock_id
        from ..config import get_settings

        bedrock = get_bedrock_service()
        settings = get_settings()
        flush_model = settings.compact_model_id

        # Resolve model
        model_info = get_model_info(flush_model)
        api_format = "anthropic"
        if model_info:
            api_format = model_info.get("api_format", "anthropic")

        _FALLBACK = "claude-haiku-4-5-20251001"
        if api_format == "converse":
            flush_model = _FALLBACK
            api_format = "anthropic"

        model_id = flush_model
        if not model_id.startswith(("us.", "deepseek.", "minimax.", "moonshotai.", "moonshot.", "qwen.", "zai.")):
            model_id = get_bedrock_id(flush_model)

        prompt = _SESSION_EXTRACT_PROMPT.format(messages_text=messages_text)
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 1024,
            "temperature": 0.2,
            "messages": [{"role": "user", "content": prompt}],
        }

        result = await bedrock.invoke_model(
            model_id=model_id,
            body=body,
            api_format=api_format,
        )

        # Extract response text
        response_text = ""
        if result and isinstance(result, dict):
            content_blocks = result.get("content", [])
            if content_blocks and isinstance(content_blocks, list):
                for block in content_blocks:
                    if isinstance(block, dict) and block.get("type") == "text":
                        response_text = block["text"]
                        break

        if not response_text or "NOTHING_TO_REMEMBER" in response_text:
            logger.info(f"Session {session_id}: nothing worth remembering ({len(messages)} messages)")
            return {"archived": False, "reason": "nothing_to_remember", "session_id": session_id, "message_count": len(messages)}

        # Write extracted facts to daily memory log
        from mcp_tools.handlers.memory_tools import memory_write

        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        content_to_write = f"## Session archive ({now})\n\n{response_text.strip()}\n"
        write_result = memory_write(target="daily", content=content_to_write)

        if write_result.get("success"):
            facts_count = sum(1 for line in response_text.split("\n") if line.strip().startswith("-"))
            logger.info(f"Session {session_id} archived: {facts_count} facts to {write_result.get('path')}")
            return {
                "archived": True,
                "path": write_result.get("path"),
                "facts_count": facts_count,
                "message_count": len(messages),
                "session_id": session_id,
            }
        else:
            logger.warning(f"Session {session_id} archive write failed: {write_result.get('error')}")
            return {"archived": False, "error": write_result.get("error"), "session_id": session_id}

    except Exception as e:
        logger.error(f"Failed to archive session {session_id}: {e}")
        return {"archived": False, "error": str(e), "session_id": session_id}
