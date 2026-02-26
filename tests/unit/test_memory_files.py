"""
Unit tests for MemoryFileManager (api/services/memory_files.py)

Tests cover:
- File creation and reading (MEMORY.md, daily logs, session archives)
- Content injection for system prompt
- File listing and metadata
- Cleanup of old files
- Security: path traversal prevention
"""
import os
import pytest
import tempfile
import shutil
from datetime import datetime, timedelta

from api.services.memory_files import MemoryFileManager


@pytest.fixture
def workspace(tmp_path):
    """Create a temporary workspace directory."""
    ws = str(tmp_path / "workspace")
    os.makedirs(ws, exist_ok=True)
    return ws


@pytest.fixture
def mgr(workspace):
    """Create a MemoryFileManager with a temporary workspace."""
    return MemoryFileManager(workspace_path=workspace, retention_days=7)


class TestMemoryFileManagerInit:
    """Test initialization and directory structure."""

    def test_creates_workspace_and_memory_dir(self, workspace):
        mgr = MemoryFileManager(workspace_path=workspace)
        assert os.path.isdir(mgr.workspace_dir)
        assert os.path.isdir(mgr.memory_dir)

    def test_memory_dir_is_subdir_of_workspace(self, mgr):
        assert mgr.memory_dir == os.path.join(mgr.workspace_dir, "memory")

    def test_default_retention_days(self, workspace):
        mgr = MemoryFileManager(workspace_path=workspace)
        assert mgr.retention_days == 7

    def test_custom_retention_days(self, workspace):
        mgr = MemoryFileManager(workspace_path=workspace, retention_days=30)
        assert mgr.retention_days == 30


class TestMemoryMd:
    """Test MEMORY.md (long-term curated memory) operations."""

    def test_memory_md_path(self, mgr):
        assert mgr.memory_md_path == os.path.join(mgr.workspace_dir, "MEMORY.md")

    def test_read_nonexistent_returns_empty(self, mgr):
        assert mgr.read_memory_md() == ""

    def test_write_and_read(self, mgr):
        content = "# My Memory\n\nImportant fact: sky is blue."
        mgr.write_longterm(content)
        assert mgr.read_memory_md() == content

    def test_write_overwrites(self, mgr):
        mgr.write_longterm("version 1")
        mgr.write_longterm("version 2")
        assert mgr.read_memory_md() == "version 2"


class TestDailyLog:
    """Test daily log (memory/YYYY-MM-DD.md) operations."""

    def test_append_creates_file(self, mgr):
        path = mgr.append_daily("Test entry", date="2026-01-15")
        assert os.path.isfile(path)
        assert path.endswith("2026-01-15.md")

    def test_append_adds_content(self, mgr):
        mgr.append_daily("Entry 1", date="2026-01-15")
        mgr.append_daily("Entry 2", date="2026-01-15")
        content = mgr.read_daily(date="2026-01-15")
        assert "Entry 1" in content
        assert "Entry 2" in content

    def test_read_nonexistent_returns_empty(self, mgr):
        assert mgr.read_daily(date="1999-01-01") == ""

    def test_read_recent_dailies(self, mgr):
        today = datetime.now().strftime("%Y-%m-%d")
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        mgr.append_daily("Today's note", date=today)
        mgr.append_daily("Yesterday's note", date=yesterday)

        recent = mgr.read_recent_dailies(days=2)
        assert "Today's note" in recent
        assert "Yesterday's note" in recent

    def test_read_recent_dailies_skips_empty(self, mgr):
        today = datetime.now().strftime("%Y-%m-%d")
        mgr.append_daily("Only today", date=today)

        recent = mgr.read_recent_dailies(days=2)
        assert "Only today" in recent
        # Should not have yesterday section if file doesn't exist
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        assert yesterday not in recent


class TestSessionArchive:
    """Test session archive (memory/YYYY-MM-DD-<slug>.md) operations."""

    def test_write_archive(self, mgr):
        content = "# Session Archive\nSome conversation..."
        path = mgr.write_session_archive("test-topic", content, date="2026-02-20")
        assert os.path.isfile(path)
        assert "2026-02-20-test-topic.md" in path

    def test_archive_content_matches(self, mgr):
        content = "# Archive Content"
        mgr.write_session_archive("my-slug", content, date="2026-02-20")
        # Read it back directly
        fpath = os.path.join(mgr.memory_dir, "2026-02-20-my-slug.md")
        with open(fpath, "r") as f:
            assert f.read() == content

    def test_slug_sanitization(self, mgr):
        """Special characters in slug should be replaced with dashes."""
        path = mgr.write_session_archive("hello world/foo@bar", "content", date="2026-02-20")
        filename = os.path.basename(path)
        assert "/" not in filename
        assert "@" not in filename
        assert filename.startswith("2026-02-20-")

    def test_slug_length_limit(self, mgr):
        """Very long slugs should be truncated."""
        long_slug = "a" * 200
        path = mgr.write_session_archive(long_slug, "content", date="2026-02-20")
        filename = os.path.basename(path)
        # Date prefix (10) + dash (1) + truncated slug (60) + .md (3) = 74
        assert len(filename) <= 74


class TestReadFile:
    """Test safe file reading with path restrictions."""

    def test_read_existing_file(self, mgr):
        mgr.write_longterm("hello world")
        result = mgr.read_file("MEMORY.md")
        assert result["text"] == "hello world"
        assert result["path"] == "MEMORY.md"

    def test_read_nonexistent_returns_empty(self, mgr):
        result = mgr.read_file("nonexistent.md")
        assert result["text"] == ""

    def test_read_with_line_range(self, mgr):
        mgr.write_longterm("line1\nline2\nline3\nline4\nline5")
        result = mgr.read_file("MEMORY.md", from_line=2, lines=2)
        assert "line2" in result["text"]
        assert "line3" in result["text"]
        assert "line1" not in result["text"]

    def test_path_traversal_blocked(self, mgr):
        result = mgr.read_file("../../../etc/passwd")
        assert "error" in result

    def test_non_md_blocked(self, mgr):
        result = mgr.read_file("secret.json")
        assert "error" in result

    def test_empty_path_blocked(self, mgr):
        result = mgr.read_file("")
        assert "error" in result


class TestListFiles:
    """Test file listing with metadata."""

    def test_empty_workspace(self, mgr):
        files = mgr.list_files()
        assert files == []

    def test_lists_memory_md(self, mgr):
        mgr.write_longterm("content")
        files = mgr.list_files()
        assert len(files) == 1
        assert files[0]["path"] == "MEMORY.md"
        assert files[0]["type"] == "longterm"
        assert files[0]["size"] > 0

    def test_lists_daily_and_archive(self, mgr):
        mgr.append_daily("daily content", date="2026-02-20")
        mgr.write_session_archive("topic", "archive content", date="2026-02-20")
        files = mgr.list_files()
        paths = [f["path"] for f in files]
        assert any("2026-02-20.md" in p for p in paths)
        assert any("2026-02-20-topic.md" in p for p in paths)

    def test_file_types_correct(self, mgr):
        mgr.write_longterm("x")
        mgr.append_daily("y", date="2026-02-20")
        mgr.write_session_archive("z", "w", date="2026-02-20")
        files = mgr.list_files()
        type_map = {f["path"]: f["type"] for f in files}
        assert type_map["MEMORY.md"] == "longterm"
        assert type_map["memory/2026-02-20.md"] == "daily"
        assert type_map["memory/2026-02-20-z.md"] == "archive"


class TestCleanup:
    """Test old file cleanup based on retention days."""

    def test_removes_old_files(self, workspace):
        mgr = MemoryFileManager(workspace_path=workspace, retention_days=3)
        # Create a file "from 10 days ago"
        old_date = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")
        mgr.append_daily("old stuff", date=old_date)
        assert mgr.read_daily(date=old_date) != ""

        removed = mgr.cleanup_old_files()
        assert len(removed) == 1
        assert mgr.read_daily(date=old_date) == ""

    def test_keeps_recent_files(self, workspace):
        mgr = MemoryFileManager(workspace_path=workspace, retention_days=3)
        today = datetime.now().strftime("%Y-%m-%d")
        mgr.append_daily("fresh stuff", date=today)

        removed = mgr.cleanup_old_files()
        assert len(removed) == 0
        assert mgr.read_daily(date=today) != ""

    def test_does_not_remove_memory_md(self, mgr):
        mgr.write_longterm("permanent")
        # Create an old daily
        old_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        mgr.append_daily("old", date=old_date)

        mgr.cleanup_old_files()
        # MEMORY.md is in workspace root, not memory/ dir, so unaffected
        assert mgr.read_memory_md() == "permanent"


class TestContextForPrompt:
    """Test system prompt memory context injection."""

    def test_empty_returns_empty(self, mgr):
        assert mgr.get_context_for_prompt() == ""

    def test_includes_memory_md(self, mgr):
        mgr.write_longterm("User prefers dark mode.")
        context = mgr.get_context_for_prompt()
        assert "User prefers dark mode." in context
        assert "MEMORY.md" in context

    def test_includes_recent_dailies(self, mgr):
        today = datetime.now().strftime("%Y-%m-%d")
        mgr.append_daily("Fixed bug #123", date=today)
        context = mgr.get_context_for_prompt()
        assert "Fixed bug #123" in context

    def test_includes_both(self, mgr):
        mgr.write_longterm("Long-term fact")
        today = datetime.now().strftime("%Y-%m-%d")
        mgr.append_daily("Recent note", date=today)
        context = mgr.get_context_for_prompt()
        assert "Long-term fact" in context
        assert "Recent note" in context
        assert "Personal Memory" in context
