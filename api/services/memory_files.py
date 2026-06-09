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


def _memory_age_text(days_ago: int) -> str:
    """Human-readable age text for memory staleness indicators."""
    if days_ago == 0:
        return "today"
    elif days_ago == 1:
        return "yesterday"
    else:
        return f"{days_ago} days ago"


def _memory_staleness_caveat() -> str:
    """Return a caveat string for older memories."""
    return (
        "⚠️ **Staleness warning**: Memories older than today are point-in-time observations. "
        "Claims about code behavior, file paths, or configurations may be outdated. "
        "Verify against current code before asserting as fact or recommending to the user."
    )


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

    def read_recent_dailies(self, days: int = 2, with_staleness: bool = False) -> str:
        """Read today + yesterday (or N days) of daily logs, concatenated.

        Args:
            days: Number of days to look back.
            with_staleness: If True, add age indicator to each daily log header.
        """
        parts = []
        today = datetime.now()
        for i in range(days):
            date_str = (today - timedelta(days=i)).strftime("%Y-%m-%d")
            content = self.read_daily(date_str)
            if content.strip():
                if with_staleness:
                    age = _memory_age_text(i)
                    parts.append(f"## Daily Log: {date_str} ({age})\n\n{content.strip()}")
                else:
                    parts.append(f"## Daily Log: {date_str}\n\n{content.strip()}")
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

        Only MEMORY.md (long-term, organized by type) goes into the static
        cache prefix. Daily logs are kept out — they change every day, would
        bust the cache, and are reachable via memory_search RAG anyway.
        """
        parts = []

        memory_md = self.read_memory_md()
        if memory_md.strip():
            parts.append(f"## Long-term Memory (MEMORY.md)\n\n{memory_md.strip()}")

        if not parts:
            return ""

        # Staleness caveat
        staleness_note = _memory_staleness_caveat()

        return (
            "\n\n## Personal Memory\n"
            "The following is your persistent memory from previous sessions. "
            "Use this context to maintain continuity.\n\n"
            + staleness_note + "\n\n"
            + "\n\n".join(parts)
            + "\n\n**Memory is limited — if you want to remember something, WRITE IT TO A FILE. "
            "\"Mental notes\" don't survive session restarts. Files do. Text > Brain.**\n"
            "\n**Memory types** (MEMORY.md is organized by these categories):\n"
            "- **User**: role, expertise, preferences, communication style\n"
            "- **Feedback**: corrections (\"don't do X\") and confirmations (\"yes, keep doing that\") — highest retention priority\n"
            "- **Project**: architecture decisions, deadlines, ongoing work context\n"
            "- **Reference**: external URLs, dashboards, ticket trackers, API endpoints\n"
            "\n**Memory tools:**\n"
            "- `memory_search` — Search past conversations, decisions, or context.\n"
            "- `memory_get` — Read a specific memory file.\n"
            "- `memory_write(target=\"daily\")` — Append a note to today's daily log. Use for session observations, decisions, todos, running context.\n"
            "- `memory_write(target=\"daily\", memory_type=\"feedback\")` — Tag a daily entry with a memory type for better distillation.\n"
            "- `memory_write(target=\"longterm\")` — Append to MEMORY.md. Use for durable facts that should persist across all sessions.\n"
            "\n**What to save (by type):**\n"
            "- **[user]** User preferences for tools, communication style, workflow habits, expertise level\n"
            "- **[feedback]** Any time the user corrects your approach OR confirms a non-obvious approach worked. Include **Why** and **How to apply**.\n"
            "- **[project]** Key architectural decisions, deadlines, ongoing initiatives, technical choices\n"
            "- **[reference]** Credentials, API keys, URLs, server IPs, dashboard links, config values\n"
            "\n**What NOT to save:**\n"
            "- Code patterns, file paths, git history (derivable from current code)\n"
            "- Session-specific debugging steps or one-off fixes\n"
            "- Anything that duplicates existing memory entries\n"
            "- Speculative or unverified conclusions\n"
            "\n**When to proactively write memory:**\n"
            "- User says \"remember this\", \"note that\", \"don't forget\" → write immediately.\n"
            "- User corrects you (\"no, not that\", \"don't\", \"stop doing X\") → save as [feedback] with Why and How to apply.\n"
            "- User confirms a non-obvious approach (\"yes exactly\", \"perfect\") → save as [feedback] confirmation.\n"
            "- User provides credentials, API keys, or config values → save as [reference] immediately.\n"
            "- You discover an important user preference → save as [user].\n"
            "- A key decision is made → save as [project] with Why and How to apply.\n"
            "- When the user corrects you on something from memory, update or remove the incorrect entry immediately.\n"
            "\n**When to proactively search memory:**\n"
            "- User asks about something discussed in a previous session\n"
            "- User references \"之前\", \"上次\", \"earlier\", \"remember when\"\n"
            "- Before making assumptions about user preferences — check memory first\n"
            "\n**Before recommending from memory:**\n"
            "- If memory names a file path → check it still exists.\n"
            "- If memory names a function or flag → grep for it.\n"
            "- Memory says X exists ≠ X exists now. Verify before acting.\n"
            "\n**Rules:**\n"
            "- **NEVER** browse `~/.springo/sessions/` JSONL files — use memory tools instead.\n"
            "- **NEVER** use `list_directory`, `glob`, `read_file` to scan session directories.\n"
            "- If `memory_search` returns no results, tell the user honestly.\n"
        )


# ---------------------------------------------------------------------------
# Per-turn Dynamic Memory Retrieval
# ---------------------------------------------------------------------------

def find_relevant_memory_snippets(
    query: str,
    manager: "MemoryFileManager",
    max_snippets: int = 5,
    max_chars_per_snippet: int = 500,
    days: int = 7,
) -> str:
    """Find memory snippets most relevant to the current user message.

    Uses lightweight keyword matching across daily logs within the retention
    window. Returns formatted snippets sorted by relevance score.

    This is a fast, local alternative to vector search — suitable for
    injection into per-turn context without adding latency.

    Args:
        query: Current user message text.
        manager: MemoryFileManager instance.
        max_snippets: Maximum number of snippets to return.
        max_chars_per_snippet: Max characters per snippet.
        days: How many days of daily logs to search.

    Returns:
        Formatted string of relevant snippets, or empty string if none found.
    """
    if not query or not query.strip():
        return ""

    import re as _re

    # Tokenize query into meaningful terms (≥2 chars, skip common words)
    _stop_words = {
        "the", "is", "at", "in", "on", "to", "of", "and", "or", "a", "an",
        "it", "do", "be", "this", "that", "for", "with", "not", "are", "was",
        "but", "have", "has", "had", "can", "will", "just", "so", "if",
        "我", "你", "的", "了", "是", "在", "有", "和", "也", "就",
        "都", "不", "这", "那", "吗", "会", "要", "把", "被", "让",
    }
    raw_terms = _re.findall(r'[\w\u4e00-\u9fff]+', query.lower())
    terms = [t for t in raw_terms if len(t) >= 2 and t not in _stop_words]
    if not terms:
        return ""

    # Scan daily log files within date range
    today = datetime.now()
    candidates = []  # (score, age_days, date_str, snippet)

    for i in range(days):
        date_str = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        content = manager.read_daily(date_str)
        if not content.strip():
            continue

        # Split into sections (## headers or double newlines)
        sections = _re.split(r'\n(?=## )', content)

        for section in sections:
            section = section.strip()
            if not section or len(section) < 20:
                continue

            section_lower = section.lower()
            matched = sum(1 for t in terms if t in section_lower)
            if matched == 0:
                continue

            score = matched / len(terms)
            # Boost recent entries
            recency_bonus = max(0, (days - i) / days) * 0.2
            score += recency_bonus

            # Truncate snippet
            snippet = section[:max_chars_per_snippet]
            if len(section) > max_chars_per_snippet:
                snippet += "..."

            candidates.append((score, i, date_str, snippet))

    if not candidates:
        return ""

    # Sort by score descending, take top N
    candidates.sort(key=lambda x: -x[0])
    top = candidates[:max_snippets]

    # Format output
    parts = []
    for score, age_days, date_str, snippet in top:
        age_text = _memory_age_text(age_days)
        staleness = ""
        if age_days > 1:
            staleness = " ⚠️ may be outdated"
        parts.append(f"**[{date_str} ({age_text}{staleness})]** (relevance: {score:.0%})\n{snippet}")

    return "\n\n---\n\n".join(parts)


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
