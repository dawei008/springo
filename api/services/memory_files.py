"""
Memory Files Manager
管理 ~/.springo/workspace/ 下的 Markdown 记忆文件

文件布局:
  ~/.springo/workspace/MEMORY.md          — 长期精炼记忆
  ~/.springo/workspace/memory/YYYY-MM-DD.md           — 每日日志
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Defaults
DEFAULT_WORKSPACE_PATH = "~/.springo/workspace"
DEFAULT_RETENTION_DAYS = 7


class MemoryFileManager:
    """Manages Markdown memory files in the workspace directory."""

    def __init__(self, workspace_path: str = DEFAULT_WORKSPACE_PATH, retention_days: int = DEFAULT_RETENTION_DAYS):
        self.workspace_dir = os.path.expanduser(workspace_path)
        self.memory_dir = os.path.join(self.workspace_dir, "memory")
        self.retention_days = retention_days
        os.makedirs(self.memory_dir, exist_ok=True)
        logger.info(f"MemoryFileManager initialized: workspace={self.workspace_dir}, retention={retention_days}d")

    # ---- Write operations ----

    @property
    def memory_md_path(self) -> str:
        return os.path.join(self.workspace_dir, "MEMORY.md")

    def _daily_path(self, date: str = None) -> str:
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        return os.path.join(self.memory_dir, f"{date}.md")

    def append_daily(self, content: str, date: str = None) -> str:
        """Append content to today's (or specified date's) daily log."""
        path = self._daily_path(date)
        with open(path, "a", encoding="utf-8") as f:
            f.write(content.rstrip("\n") + "\n\n")
        logger.debug(f"Appended to daily log: {path}")
        return path

    def write_longterm(self, content: str) -> str:
        """Write/overwrite MEMORY.md (long-term curated memory)."""
        path = self.memory_md_path
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info(f"MEMORY.md updated ({len(content)} chars)")
        return path

    # ---- Read operations ----

    def read_memory_md(self) -> str:
        """Read MEMORY.md content. Returns empty string if not found."""
        path = self.memory_md_path
        if not os.path.isfile(path):
            return ""
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            logger.warning(f"Failed to read MEMORY.md: {e}")
            return ""

    def read_daily(self, date: str = None) -> str:
        """Read a daily log file. Returns empty string if not found."""
        path = self._daily_path(date)
        if not os.path.isfile(path):
            return ""
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            logger.warning(f"Failed to read daily log {path}: {e}")
            return ""

    def read_recent_dailies(self, days: int = 2) -> str:
        """Read today + yesterday (or N days) of daily logs, concatenated."""
        parts = []
        today = datetime.now()
        for i in range(days):
            date = (today - timedelta(days=i)).strftime("%Y-%m-%d")
            content = self.read_daily(date)
            if content.strip():
                parts.append(f"## Daily Log: {date}\n\n{content.strip()}")
        return "\n\n".join(parts)

    def read_file(self, rel_path: str, from_line: int = None, lines: int = None) -> Dict:
        """Read a memory file by relative path (within workspace). Safe: only .md files."""
        rel_path = rel_path.strip()
        if not rel_path or ".." in rel_path:
            return {"error": "Invalid path", "text": "", "path": rel_path}

        abs_path = os.path.realpath(os.path.join(self.workspace_dir, rel_path))
        # Security: must be under workspace and must be .md
        if not abs_path.startswith(os.path.realpath(self.workspace_dir)) or not abs_path.endswith(".md"):
            return {"error": "Path not allowed", "text": "", "path": rel_path}

        if not os.path.isfile(abs_path):
            return {"text": "", "path": rel_path}

        try:
            with open(abs_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            return {"error": str(e), "text": "", "path": rel_path}

        if from_line is not None or lines is not None:
            all_lines = content.split("\n")
            start = max(1, from_line or 1)
            count = max(1, lines or len(all_lines))
            content = "\n".join(all_lines[start - 1 : start - 1 + count])

        return {"text": content, "path": rel_path}

    def list_files(self) -> List[Dict]:
        """List all memory files with metadata."""
        files = []
        # MEMORY.md
        mem_path = self.memory_md_path
        if os.path.isfile(mem_path):
            stat = os.stat(mem_path)
            files.append({
                "path": "MEMORY.md",
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "type": "longterm",
            })
        # memory/*.md
        if os.path.isdir(self.memory_dir):
            for name in sorted(os.listdir(self.memory_dir), reverse=True):
                if not name.endswith(".md"):
                    continue
                fpath = os.path.join(self.memory_dir, name)
                if not os.path.isfile(fpath):
                    continue
                stat = os.stat(fpath)
                files.append({
                    "path": f"memory/{name}",
                    "size": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "type": "daily",
                })
        return files

    # ---- Cleanup ----

    def cleanup_old_files(self) -> List[str]:
        """Remove memory files older than retention_days. Returns list of removed files."""
        cutoff = datetime.now() - timedelta(days=self.retention_days)
        cutoff_str = cutoff.strftime("%Y-%m-%d")
        removed = []
        if not os.path.isdir(self.memory_dir):
            return removed
        for name in os.listdir(self.memory_dir):
            if not name.endswith(".md"):
                continue
            # Extract date prefix (YYYY-MM-DD)
            date_part = name[:10]
            if len(date_part) == 10 and date_part < cutoff_str:
                fpath = os.path.join(self.memory_dir, name)
                try:
                    os.remove(fpath)
                    removed.append(name)
                    logger.info(f"Cleaned up old memory file: {name}")
                except Exception as e:
                    logger.warning(f"Failed to remove {name}: {e}")
        return removed

    # ---- System prompt injection ----

    def get_context_for_prompt(self) -> str:
        """Build memory context to inject into system prompt.

        Returns MEMORY.md + recent 2 days of daily logs, formatted for injection.
        Returns empty string if no memory files exist.
        """
        parts = []

        # MEMORY.md
        memory_md = self.read_memory_md()
        if memory_md.strip():
            parts.append(f"## Long-term Memory (MEMORY.md)\n\n{memory_md.strip()}")

        # Recent daily logs (today + yesterday), capped to limit token cost
        recent = self.read_recent_dailies(days=2)
        if recent.strip():
            trimmed = recent.strip()
            if len(trimmed) > 2000:
                trimmed = "... (earlier entries truncated)\n\n" + trimmed[-2000:]
            parts.append(f"## Recent Memory Notes\n\n{trimmed}")

        if not parts:
            return ""

        return (
            "\n\n## Personal Memory\n"
            "The following is your persistent memory from previous sessions. "
            "Use this context to maintain continuity.\n\n"
            + "\n\n".join(parts)
            + "\n\n**Memory is limited — if you want to remember something, WRITE IT TO A FILE. "
            "\"Mental notes\" don't survive session restarts. Files do. Text > Brain.**\n"
            "\n**Memory tools:**\n"
            "- `memory_search` — Search past conversations, decisions, or context.\n"
            "- `memory_get` — Read a specific memory file.\n"
            "- `memory_write(target=\"daily\")` — Append a note to today's daily log. Use for session observations, decisions, todos, running context.\n"
            "- `memory_write(target=\"longterm\")` — Append to MEMORY.md. Use for durable facts that should persist across all sessions: user preferences, project architecture, coding conventions.\n"
            "\n**What to save:**\n"
            "- Stable patterns and conventions confirmed across interactions (coding style, naming, workflows)\n"
            "- Key architectural decisions, important file paths, and project structure\n"
            "- User preferences for tools, communication style, and workflow habits\n"
            "- Solutions to recurring problems and debugging insights\n"
            "- Credentials, API keys, URLs, server IPs, and config values the user provides\n"
            "- Important commands, deployment steps, or environment setup that was figured out\n"
            "\n**What NOT to save:**\n"
            "- Session-specific context (current task details, in-progress work, temporary state)\n"
            "- Information that might be incomplete — verify before writing\n"
            "- Anything that duplicates existing memory entries\n"
            "- Speculative or unverified conclusions\n"
            "- Routine chitchat or ephemeral task details\n"
            "\n**When to proactively write memory:**\n"
            "- User says \"remember this\", \"note that\", \"don't forget\" → write immediately, no need to wait.\n"
            "- User provides credentials, API keys, server addresses, or config values → `memory_write(target=\"longterm\")` immediately.\n"
            "- You discover an important user preference, coding style, or project convention → `memory_write(target=\"longterm\")`.\n"
            "- You make a significant decision, find a key solution, or complete a major task → `memory_write(target=\"daily\")`.\n"
            "- You learn something that would be useful in future sessions → choose daily (transient) or longterm (durable).\n"
            "- When the user corrects you on something from memory, update or remove the incorrect entry immediately.\n"
            "\n**When to proactively search memory:**\n"
            "- User asks about something discussed in a previous session (keys, configs, decisions, URLs, etc.)\n"
            "- User references \"之前\", \"上次\", \"earlier\", \"remember when\", or implies prior context\n"
            "- You need credentials, URLs, server IPs, or project-specific details not in current context\n"
            "- Before making assumptions about user preferences — check memory first\n"
            "\n**Rules:**\n"
            "- **NEVER** browse `~/.springo/sessions/` JSONL files — use memory tools instead.\n"
            "- **NEVER** use `list_directory`, `glob`, `read_file` to scan session directories.\n"
            "- If `memory_search` returns no results, tell the user honestly.\n"
        )


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
_manager: Optional[MemoryFileManager] = None


def get_memory_file_manager() -> Optional[MemoryFileManager]:
    return _manager


def init_memory_file_manager(workspace_path: str = None, retention_days: int = None) -> MemoryFileManager:
    """Initialize the singleton MemoryFileManager from config."""
    global _manager
    from .memory_sync import load_memory_config

    config = load_memory_config()
    wp = workspace_path or config.get("workspace_path", DEFAULT_WORKSPACE_PATH)
    rd = retention_days or config.get("retention_days", DEFAULT_RETENTION_DAYS)

    _manager = MemoryFileManager(workspace_path=wp, retention_days=rd)
    # Cleanup old files on startup
    removed = _manager.cleanup_old_files()
    if removed:
        logger.info(f"Cleaned up {len(removed)} old memory files on startup")
    return _manager
