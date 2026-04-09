"""
Memory Archiver & Distiller
- archive_session: extracts key facts from ended sessions → daily log
- distill_longterm_memory: periodically distills daily logs → MEMORY.md

Called when user creates a new session or deletes one.
Uses a fast model (Haiku) for both extraction and distillation.
"""

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# Archive watermark state file (per-session)
ARCHIVE_STATE_FILE = ".archive_state.json"

# Memory types for categorized extraction
MEMORY_TYPES = ("user", "feedback", "project", "reference")

# Prompt for session journal extraction (with typed memory categorization)
_SESSION_EXTRACT_PROMPT = """You are a session journal writer. A user session has ended. Your job is to write a **detailed session journal** capturing what happened, and to extract **categorized memories** for future recall.

Rules:
- If the session contains only greetings or trivial chitchat, respond with exactly: NOTHING_TO_REMEMBER
- Otherwise, produce TWO sections:

## Session Journal

Write a detailed Markdown journal covering:
  - **What was done**: tasks attempted, tools used, commands run (include actual commands/code snippets)
  - **Key decisions**: why certain approaches were chosen over others
  - **Outcomes**: what worked, what failed, error messages encountered
  - **Open items**: unfinished tasks, next steps, blockers
- Use Markdown headers (###), bullet lists, and fenced code blocks for commands/code
- Include specific file paths, URLs, model names, config values — concrete details matter

## Categorized Memories

Extract durable facts into these 4 categories. Use the exact format below. Only include categories that have content.

### [user]
User's role, goals, expertise, preferences, and knowledge. Things that help tailor future interactions.
- Each fact as a bullet point

### [feedback]
User corrections ("don't do X"), confirmations ("yes, keep doing that"), and approach guidance.
For each item, include **Why:** (the reason) and **How to apply:** (when this applies).
- Correction or confirmation — **Why:** reason — **How to apply:** guidance

### [project]
Key decisions, architecture choices, ongoing work context, deadlines — things not derivable from code alone.
For each item, include **Why:** (motivation) and **How to apply:** (how it shapes future work).
- Decision or fact — **Why:** reason — **How to apply:** guidance

### [reference]
Pointers to external resources: URLs, dashboard links, ticket trackers, API endpoints, credentials, account info.
- Resource description → location/URL/value

**Important:**
- Do NOT save code patterns, file paths, or git history (derivable from code)
- Do NOT save ephemeral task details or debugging steps (one-time fixes)
- DO save user preferences, corrections, architectural decisions, and external references
- DO save account credentials, API keys, app IDs, secrets, tokens, and service configurations mentioned by the user or discovered during the session (e.g. "WeChat AppID: wx123...", "API key for service X: abc...")
- DO save account names, usernames, profile names on platforms (e.g. "WeChat Official Account: 大卫AI")
- Aim for 5-15 categorized memory items depending on session richness

Session messages:
{messages_text}"""


def _get_archive_state_path(session_id: str) -> str:
    sessions_dir = os.path.expanduser("~/.springo/sessions")
    return os.path.join(sessions_dir, session_id, ARCHIVE_STATE_FILE)


def _load_archive_watermark(session_id: str) -> int:
    """Load the last archived message index for a session. Returns -1 if never archived."""
    path = _get_archive_state_path(session_id)
    if not os.path.isfile(path):
        return -1
    try:
        with open(path, "r", encoding="utf-8") as f:
            state = json.load(f)
        return state.get("last_archived_index", -1)
    except Exception:
        return -1


def _save_archive_watermark(session_id: str, last_index: int):
    """Save the archive watermark after successful archiving."""
    path = _get_archive_state_path(session_id)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        state = {"last_archived_index": last_index, "updated_at": datetime.now().isoformat()}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"Failed to save archive watermark for {session_id}: {e}")


def _read_all_messages(session_id: str) -> List[Dict[str, Any]]:
    """Read all user/assistant messages from a session JSONL file."""
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

    return messages


def _build_messages_text(messages: List[Dict[str, Any]], max_chars: int = 128000) -> str:
    """Build a text representation of messages for the Haiku extraction prompt.

    max_chars=128K allows Haiku (~200K context) to see the full conversation.
    Note: this only affects the archive write path (Haiku input), NOT the read
    path where daily logs are injected into the main model's context (capped at 2000 chars).
    """
    text_parts = []
    total_chars = 0

    for msg in messages:
        snippet = msg["text"].strip()[:2000]
        line = f"[{msg['role']}]: {snippet}"
        if total_chars + len(line) > max_chars:
            break
        text_parts.append(line)
        total_chars += len(line)

    return "\n".join(text_parts)


async def archive_session(session_id: str, **_kwargs) -> Dict[str, Any]:
    """Extract key facts from a session and save to daily memory log.

    Uses watermark-based incremental archiving: only processes messages
    added since the last archive, ensuring no conversation content is missed
    even for long sessions archived across multiple triggers.

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

    # Read all messages and slice from watermark
    all_messages = _read_all_messages(session_id)
    if not all_messages:
        return {"archived": False, "reason": "no_messages", "session_id": session_id}

    watermark = _load_archive_watermark(session_id)
    new_messages = all_messages[watermark + 1:]
    if not new_messages:
        return {"archived": False, "reason": "no_new_messages", "session_id": session_id}

    new_watermark = len(all_messages) - 1

    messages_text = _build_messages_text(new_messages)
    if not messages_text:
        # Advance watermark even if no extractable text (e.g. all slash commands)
        _save_archive_watermark(session_id, new_watermark)
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
            "max_tokens": 4096,
            "temperature": 0.3,
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

        # Advance watermark regardless of whether facts were extracted
        _save_archive_watermark(session_id, new_watermark)

        if not response_text or "NOTHING_TO_REMEMBER" in response_text:
            logger.info(f"Session {session_id}: nothing worth remembering ({len(new_messages)} new messages, watermark {watermark} → {new_watermark})")
            return {"archived": False, "reason": "nothing_to_remember", "session_id": session_id,
                    "message_count": len(new_messages), "watermark": new_watermark}

        # Write extracted facts to daily memory log
        from mcp_tools.handlers.memory_tools import memory_write

        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        content_to_write = f"## Session archive ({now})\n\n{response_text.strip()}\n"
        write_result = memory_write(target="daily", content=content_to_write)

        if write_result.get("success"):
            facts_count = sum(1 for line in response_text.split("\n") if line.strip().startswith("-"))
            logger.info(f"Session {session_id} archived: {facts_count} facts, watermark {watermark} → {new_watermark}")

            # Trigger longterm memory distillation (throttled, fire-and-forget)
            try:
                distill_result = await distill_longterm_memory()
                if distill_result.get("distilled"):
                    logger.info(f"[Distill] MEMORY.md updated after session archive")
            except Exception as e:
                logger.debug(f"[Distill] Skipped after archive: {e}")

            return {
                "archived": True,
                "path": write_result.get("path"),
                "facts_count": facts_count,
                "message_count": len(new_messages),
                "watermark": new_watermark,
                "session_id": session_id,
            }
        else:
            logger.warning(f"Session {session_id} archive write failed: {write_result.get('error')}")
            return {"archived": False, "error": write_result.get("error"), "session_id": session_id}

    except Exception as e:
        logger.error(f"Failed to archive session {session_id}: {e}")
        return {"archived": False, "error": str(e), "session_id": session_id}


# ---------------------------------------------------------------------------
# Longterm Memory Distillation (daily logs → MEMORY.md)
# ---------------------------------------------------------------------------

# Minimum hours between distillation runs (throttle)
DISTILL_COOLDOWN_HOURS = 6

_DISTILL_PROMPT = """You are a memory curator. Below are daily memory logs from recent sessions and the current long-term memory file.

Your job: produce an updated MEMORY.md organized by **memory type** that captures all durable facts worth remembering across sessions.

Rules:
- Organize into exactly these 4 sections (omit empty sections):

  ## User
  User's role, expertise, goals, preferences, communication style.

  ## Feedback
  User corrections, confirmations, and approach guidance. Each item should include the rule, why it matters, and when to apply it. These are critical — never drop feedback items unless explicitly contradicted by newer feedback.

  ## Project
  Key architectural decisions, ongoing initiatives, deadlines, technical choices not derivable from code. Include why and how to apply.

  ## Reference
  External resources: URLs, dashboards, ticket trackers, API endpoints, credentials (API keys, app IDs, secrets, tokens), account names/usernames on platforms.

- Keep: user preferences, corrections/confirmations, project decisions, external references
- Keep: account credentials, API keys, app IDs/secrets, service configurations, platform usernames
- Remove: ephemeral task details, timestamps, session-specific debugging notes, one-off fixes
- Remove: code patterns, file paths, git history (derivable from current code)
- Merge new insights from daily logs into existing long-term memory
- Don't lose existing facts unless outdated or explicitly contradicted
- Feedback items have highest retention priority — never silently drop them
- Keep total output under 5000 characters — be concise but thorough
- Use Markdown bullet lists
- If daily logs contain nothing new worth adding, return the existing MEMORY.md unchanged
- Output ONLY the MEMORY.md content, no explanations

Existing MEMORY.md:
{existing_memory}

Recent daily logs:
{daily_logs}"""


async def distill_longterm_memory() -> Dict[str, Any]:
    """Distill recent daily logs into MEMORY.md.

    Reads daily logs from the retention window, calls a fast model to
    produce a curated MEMORY.md, and overwrites it.

    Throttled: skips if MEMORY.md was updated less than DISTILL_COOLDOWN_HOURS ago.

    Returns:
        Dict with distillation result: {distilled: bool, reason?: str, chars?: int}
    """
    from .memory_files import get_memory_file_manager

    mgr = get_memory_file_manager()
    if mgr is None:
        return {"distilled": False, "reason": "memory_file_manager_not_initialized"}

    # Throttle: check MEMORY.md mtime
    if os.path.isfile(mgr.memory_md_path):
        mtime = datetime.fromtimestamp(os.path.getmtime(mgr.memory_md_path))
        if datetime.now() - mtime < timedelta(hours=DISTILL_COOLDOWN_HOURS):
            logger.debug(f"[Distill] Skipped: MEMORY.md updated {mtime.isoformat()}, cooldown {DISTILL_COOLDOWN_HOURS}h")
            return {"distilled": False, "reason": "cooldown"}

    # Read existing MEMORY.md
    existing_memory = mgr.read_memory_md().strip()
    if not existing_memory:
        existing_memory = "(empty — no long-term memory yet)"

    # Read recent daily logs (retention_days window)
    daily_logs = mgr.read_recent_dailies(days=mgr.retention_days)
    if not daily_logs.strip():
        return {"distilled": False, "reason": "no_daily_logs"}

    # Truncate if too long
    if len(daily_logs) > 6000:
        daily_logs = daily_logs[:6000] + "\n\n... (truncated)"

    # Call fast model to distill
    try:
        from .bedrock import get_bedrock_service
        from .model_registry import get_model_info, get_bedrock_id
        from ..config import get_settings

        bedrock = get_bedrock_service()
        settings = get_settings()
        distill_model = settings.compact_model_id

        model_info = get_model_info(distill_model)
        api_format = "anthropic"
        if model_info:
            api_format = model_info.get("api_format", "anthropic")

        _FALLBACK = "claude-haiku-4-5-20251001"
        if api_format == "converse":
            distill_model = _FALLBACK
            api_format = "anthropic"

        model_id = distill_model
        if not model_id.startswith(("us.", "deepseek.", "minimax.", "moonshotai.", "moonshot.", "qwen.", "zai.")):
            model_id = get_bedrock_id(distill_model)

        prompt = _DISTILL_PROMPT.format(
            existing_memory=existing_memory,
            daily_logs=daily_logs,
        )

        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 2048,
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

        if not response_text or not response_text.strip():
            return {"distilled": False, "reason": "empty_response"}

        # Write distilled content to MEMORY.md (overwrite, hard cap 5000 chars)
        distilled = response_text.strip()[:5000]
        mgr.write_longterm(distilled)
        logger.info(f"[Distill] MEMORY.md updated ({len(response_text)} chars)")

        # Trigger AgentCore sync for the updated files
        try:
            from .memory_sync import get_sync_manager
            sync_mgr = get_sync_manager()
            if sync_mgr:
                sync_mgr.trigger_file_sync()
                logger.info("[Distill] Triggered AgentCore file sync after distillation")
        except Exception as e:
            logger.debug(f"[Distill] AgentCore sync trigger skipped: {e}")

        return {"distilled": True, "chars": len(response_text)}

    except Exception as e:
        logger.warning(f"[Distill] Failed: {e}")
        return {"distilled": False, "error": str(e)}
